"""
Amazon Bedrock Client Integration.
Combines boto3 Converse API invoking, strip_markdown_code_fences, structured JSON validation,
concurrency call gating, telemetry tracking, and repair loops.
"""

import json
import logging
import os
import re
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Dict, Optional, Protocol, Self, TypeVar

# Load root .env so AWS_BEARER_TOKEN_BEDROCK and all Bedrock settings are available
try:
    from dotenv import load_dotenv
    _root_env = Path(__file__).resolve().parents[4] / ".env"
    if _root_env.exists():
        load_dotenv(_root_env, override=False)  # override=False keeps .env.local values where set
except ImportError:
    pass  # dotenv not installed; rely on env vars already set by the shell

import boto3
from botocore.config import Config
from botocore.exceptions import (
    BotoCoreError,
    ClientError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)
from pydantic import BaseModel, ValidationError

from app.ai.exceptions import (
    BedrockClientError,
    BedrockDisabledError,
    BedrockError,
    BedrockResponseError,
    BedrockThrottledError,
    BedrockTimeoutError,
    BedrockUnavailableError,
    BedrockValidationError,
    InvalidModelResponse,
)
from app.ai.telemetry import CallTelemetry, safe_label
from app.core.config import Settings, get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)
_gate_lock = threading.Lock()
_gates: dict[int, threading.BoundedSemaphore] = {}


def call_gate(limit: int) -> threading.BoundedSemaphore:
    with _gate_lock:
        return _gates.setdefault(limit, threading.BoundedSemaphore(limit))


def strip_markdown_code_fences(text: str) -> str:
    """
    Utility function to remove ```json ... ``` code fences or leading/trailing whitespace.
    Handles responses wrapped in markdown code blocks.
    """
    text = text.strip()
    match = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text


class RuntimeClient(Protocol):
    def converse(self, **kwargs: Any) -> dict[str, Any]: ...
    def close(self) -> None: ...


def _map_error(error: BotoCoreError | ClientError) -> tuple[BedrockError, bool]:
    if isinstance(error, (ReadTimeoutError, ConnectTimeoutError)):
        return BedrockTimeoutError(), True
    if isinstance(error, EndpointConnectionError):
        return BedrockUnavailableError(), True
    if isinstance(error, ClientError):
        code = error.response.get("Error", {}).get("Code")
        if code in ("ThrottlingException", "TooManyRequestsException"):
            return BedrockThrottledError(), True
        if code == "ModelTimeoutException":
            return BedrockTimeoutError(), True
        if code in (
            "ServiceUnavailableException",
            "InternalServerException",
            "ModelNotReadyException",
        ):
            return BedrockUnavailableError(), True
    return BedrockUnavailableError(), False


def _text(response: dict[str, Any]) -> str:
    try:
        if response.get("stopReason") != "end_turn":
            raise BedrockResponseError()
        message = response["output"]["message"]
        if message["role"] != "assistant":
            raise BedrockResponseError()
        blocks = message["content"]
        if not isinstance(blocks, list) or not all(
            isinstance(b, dict) and set(b) == {"text"} and isinstance(b["text"], str)
            for b in blocks
        ):
            raise BedrockResponseError()
        text = "".join(block["text"] for block in blocks).strip()
        if not text or len(text.encode()) > 262144:
            raise BedrockResponseError()
        return text
    except (KeyError, TypeError, AttributeError):
        raise BedrockResponseError() from None


def _validate(text: str, output_model: type[T]) -> T:
    fenced = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n```", text.strip(), flags=re.DOTALL)
    payload = fenced.group(1) if fenced else text.strip()

    def object_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    def invalid_constant(value: str) -> None:
        raise ValueError("non-finite JSON number")

    try:
        decoded = json.loads(
            payload, object_pairs_hook=object_pairs, parse_constant=invalid_constant
        )
        return output_model.model_validate_json(
            json.dumps(decoded, allow_nan=False), strict=True
        )
    except ValidationError as error:
        codes = tuple(
            item["type"]
            for item in error.errors(
                include_input=False, include_context=False, include_url=False
            )
        )
        raise BedrockValidationError(codes) from None
    except (ValueError, RecursionError):
        raise BedrockValidationError() from None


def _bearer_token() -> str | None:
    """Return AWS_BEARER_TOKEN_BEDROCK from env if present."""
    return os.environ.get("AWS_BEARER_TOKEN_BEDROCK") or None


def _make_boto3_session() -> boto3.Session:
    """
    Build a boto3 Session.
    If AWS_BEARER_TOKEN_BEDROCK is set we inject it via the environment variable
    that botocore's token provider picks up automatically (AWS_BEARER_TOKEN_BEDROCK),
    which is the official way to pass an ABSK-format API key to the Bedrock runtime.
    """
    token = _bearer_token()
    if token:
        # botocore >= 1.29 reads AWS_BEARER_TOKEN_BEDROCK automatically for Bedrock endpoints.
        # Set it explicitly here so any session created in this process picks it up.
        os.environ.setdefault("AWS_BEARER_TOKEN_BEDROCK", token)
    return boto3.Session()


class BedrockClient:
    """
    Amazon Bedrock client with dual support for:
    1. Direct dictionary converse via invoke()
    2. Strictly-validated Pydantic models with repair loops via converse_json() / converse_text()

    Authentication priority (highest to lowest):
      1. AWS_BEARER_TOKEN_BEDROCK env var (ABSK-format Bedrock API key)
      2. AWS SSO / IAM credentials resolved by boto3 (default credential chain)
    """

    def __init__(
        self,
        model_id: Optional[str] = None,
        region_name: Optional[str] = None,
        settings: Settings | None = None,
        *,
        runtime: RuntimeClient | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.settings = settings or get_settings()
        self.model_id = (
            model_id
            or os.environ.get("BEDROCK_MODEL_ID")
            or getattr(self.settings, "bedrock_model_id", "openai.gpt-oss-120b-1:0")
        )
        self.region_name = (
            region_name
            or os.environ.get("AWS_REGION")
            or getattr(self.settings, "aws_region", "ap-northeast-1")
        )
        # Read timeout / retry settings from env or settings
        self._connect_timeout = int(
            os.environ.get("BEDROCK_REQUEST_TIMEOUT_SECONDS")
            or getattr(self.settings, "bedrock_request_timeout_seconds", 30)
        )
        self._max_retries = int(
            os.environ.get("BEDROCK_MAX_RETRIES")
            or getattr(self.settings, "bedrock_max_retries", 2)
        )
        self._max_tokens = int(
            os.environ.get("BEDROCK_MAX_TOKENS")
            or getattr(self.settings, "bedrock_max_tokens", 1000)
        )
        self._temperature = float(
            os.environ.get("BEDROCK_TEMPERATURE")
            or getattr(self.settings, "bedrock_temperature", 0.1)
        )
        self._client = None
        self._runtime = runtime
        self._sleep = sleep
        logger.info(
            "BedrockClient initialised | model=%s region=%s bearer_token=%s",
            self.model_id,
            self.region_name,
            "present" if _bearer_token() else "absent (using IAM/SSO)",
        )

    def _get_client(self):
        """Lazy instantiation of boto3 bedrock-runtime client using the best available credentials."""
        if self._client is None:
            try:
                session = _make_boto3_session()
                self._client = session.client(
                    "bedrock-runtime",
                    region_name=self.region_name,
                    config=Config(
                        connect_timeout=self._connect_timeout,
                        read_timeout=self._connect_timeout,
                        retries={"mode": "standard", "total_max_attempts": self._max_retries + 1},
                    ),
                )
            except Exception as e:
                raise BedrockClientError(
                    f"Failed to initialize AWS Bedrock client in region '{self.region_name}': {str(e)}"
                ) from e
        return self._client

    def _get_runtime(self) -> RuntimeClient:
        if self._runtime is not None:
            return self._runtime
        try:
            session = _make_boto3_session()
            self._runtime = session.client(
                "bedrock-runtime",
                region_name=self.region_name,
                config=Config(
                    connect_timeout=self._connect_timeout,
                    read_timeout=self._connect_timeout,
                    retries={"mode": "standard", "total_max_attempts": 1},
                ),
            )
        except (BotoCoreError, ClientError):
            raise BedrockUnavailableError() from None
        return self._runtime
    def _is_mantle_model(self) -> bool:
        """
        Returns True when the model should be called via the bedrock-mantle
        OpenAI-compatible endpoint (e.g. openai.* models) instead of the
        native bedrock-runtime converse() path.
        Can also be forced via BEDROCK_USE_MANTLE=true env var.
        """
        force = os.environ.get("BEDROCK_USE_MANTLE", "").lower() in ("1", "true", "yes")
        return force or self.model_id.startswith("openai.")

    def _mantle_base_url(self) -> str:
        return f"https://bedrock-mantle.{self.region_name}.api.aws/v1"

    def _invoke_mantle(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Call the bedrock-mantle OpenAI-compatible /v1/chat/completions endpoint.
        Uses AWS_BEARER_TOKEN_BEDROCK as the Authorization Bearer token.
        Returns the parsed JSON dict extracted from the model response.
        """
        import requests as _requests  # local import to avoid hard dep at module level

        token = _bearer_token()
        if not token:
            raise BedrockClientError(
                "AWS_BEARER_TOKEN_BEDROCK is required for bedrock-mantle (openai.*) models "
                "but was not found in the environment."
            )

        url = f"{self._mantle_base_url()}/chat/completions"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": temperature,
            "max_tokens": self._max_tokens,
        }

        attempt = 0
        while True:
            try:
                resp = _requests.post(
                    url,
                    headers=headers,
                    json=payload,
                    timeout=self._connect_timeout,
                )
                if resp.status_code == 429:
                    if attempt < self._max_retries:
                        attempt += 1
                        self._sleep(min(5.0, 0.5 * (2 ** attempt)))
                        continue
                    raise BedrockThrottledError()
                if resp.status_code in (502, 503, 504):
                    if attempt < self._max_retries:
                        attempt += 1
                        self._sleep(min(5.0, 0.5 * (2 ** attempt)))
                        continue
                    raise BedrockUnavailableError()
                if not resp.ok:
                    raise BedrockClientError(
                        f"bedrock-mantle returned HTTP {resp.status_code}: {resp.text[:300]}"
                    )
            except BedrockError:
                raise
            except Exception as exc:
                raise BedrockClientError(
                    f"bedrock-mantle request failed: {exc}"
                ) from exc

            try:
                data = resp.json()
                raw_text = data["choices"][0]["message"]["content"]
            except (KeyError, IndexError, ValueError) as exc:
                raise InvalidModelResponse(
                    f"Unexpected bedrock-mantle response shape: {resp.text[:300]}"
                ) from exc

            clean_text = strip_markdown_code_fences(raw_text)
            try:
                return json.loads(clean_text)
            except json.JSONDecodeError as exc:
                raise InvalidModelResponse(
                    f"bedrock-mantle response is not valid JSON: {exc}. "
                    f"Response was: '{raw_text[:200]}'"
                ) from exc


    def invoke(
        self,
        system_prompt: str,
        user_message: str,
        temperature: float = 0.0,
    ) -> Dict[str, Any]:
        """
        Sends a request to Amazon Bedrock and returns parsed JSON.

        Routing:
        - openai.* model IDs (or BEDROCK_USE_MANTLE=true): uses the bedrock-mantle
          OpenAI-compatible /v1/chat/completions endpoint with Bearer token auth.
        - All other models: uses boto3 bedrock-runtime converse() with IAM/SSO auth.
        """
        if self._is_mantle_model():
            logger.debug("invoke() routing to bedrock-mantle for model %s", self.model_id)
            return self._invoke_mantle(system_prompt, user_message, temperature)

        # --- native bedrock-runtime converse() path (unchanged) ---
        client = self._get_client()

        try:
            response = client.converse(
                modelId=self.model_id,
                messages=[
                    {
                        "role": "user",
                        "content": [{"text": user_message}],
                    }
                ],
                system=[
                    {"text": system_prompt}
                ],
                inferenceConfig={
                    "temperature": temperature,
                    "maxTokens": 1000,
                },
            )

            output_content = response.get("output", {}).get("message", {}).get("content", [])
            if not output_content or "text" not in output_content[0]:
                raise InvalidModelResponse("Bedrock response returned empty or missing text content.")

            raw_text = output_content[0]["text"]
            clean_text = strip_markdown_code_fences(raw_text)

            try:
                parsed_json = json.loads(clean_text)
                return parsed_json
            except json.JSONDecodeError as json_err:
                raise InvalidModelResponse(
                    f"Bedrock response is not valid JSON: {str(json_err)}. Response was: '{raw_text[:200]}...'"
                ) from json_err

        except (InvalidModelResponse, BedrockClientError):
            raise
        except Exception as e:
            raise BedrockClientError(f"Bedrock Converse API call failed: {str(e)}") from e

    def model_for(self, operation_name: str | None) -> str:
        if operation_name in ("expectation_compile", "clarification_continue"):
            return (
                getattr(self.settings, "bedrock_compiler_model_id", None)
                or self.model_id
            )
        if operation_name == "mismatch_investigator":
            return (
                getattr(self.settings, "bedrock_investigator_model_id", None)
                or self.model_id
            )
        return self.model_id

    def _telemetry(
        self, operation_name: str, metadata: Mapping[str, str] | None
    ) -> CallTelemetry:
        if safe_label(operation_name) is None:
            raise ValueError("operation_name must be a short operational label")
        model = self.model_for(operation_name)
        safe_model = (
            model
            if model
            and re.fullmatch(r"[A-Za-z0-9.:/_-]{1,256}", model)
            and "://" not in model
            else None
        )
        return CallTelemetry(
            operation_name,
            safe_model,
            safe_label((metadata or {}).get("prompt_version")),
            time.monotonic(),
        )

    def _request(
        self,
        system_prompt: str,
        user_content: str,
        temperature: float | None = None,
        *,
        operation_name: str | None = None,
    ) -> dict[str, Any]:
        if len(system_prompt.encode()) > 131072 or len(user_content.encode()) > 65536:
            raise BedrockValidationError()
        if temperature is not None and not 0 <= temperature <= 1:
            raise ValueError("temperature must be between zero and one")
        return {
            "modelId": self.model_for(operation_name),
            "system": [{"text": system_prompt}],
            "messages": [{"role": "user", "content": [{"text": user_content}]}],
            "inferenceConfig": {
                "maxTokens": getattr(self.settings, "bedrock_max_tokens", 1000),
                "temperature": (
                    getattr(self.settings, "bedrock_temperature", 0.1)
                    if temperature is None
                    else temperature
                ),
            },
        }

    def _invoke(self, request: dict[str, Any], telemetry: CallTelemetry) -> str:
        runtime = self._get_runtime()
        max_retries = getattr(self.settings, "bedrock_max_retries", 2)
        max_total_tokens = getattr(self.settings, "bedrock_max_total_tokens", 8192)
        op_timeout = getattr(self.settings, "bedrock_operation_timeout_seconds", 45)
        max_concurrency = getattr(self.settings, "bedrock_max_concurrent_calls", 4)
        backoff = getattr(self.settings, "http_backoff_seconds", 0.1)

        for attempt in range(max_retries + 1):
            remaining_tokens = max_total_tokens - telemetry.total_tokens
            if remaining_tokens <= 0:
                raise BedrockValidationError(("token_budget_exceeded",))
            request["inferenceConfig"]["maxTokens"] = min(
                request["inferenceConfig"]["maxTokens"], remaining_tokens
            )
            if time.monotonic() - telemetry.started >= op_timeout:
                raise BedrockTimeoutError()
            try:
                gate = call_gate(max_concurrency)
                remaining = op_timeout - (time.monotonic() - telemetry.started)
                if not gate.acquire(timeout=max(0, remaining)):
                    raise BedrockTimeoutError()
                try:
                    if time.monotonic() - telemetry.started >= op_timeout:
                        raise BedrockTimeoutError()
                    response = runtime.converse(**request)
                finally:
                    gate.release()
            except (BotoCoreError, ClientError) as error:
                if isinstance(error, ClientError):
                    telemetry.aws_request_id = safe_label(
                        error.response.get("ResponseMetadata", {}).get("RequestId")
                    )
                mapped, retryable = _map_error(error)
                if not retryable or attempt == max_retries:
                    raise mapped from None
                telemetry.retry_count += 1
                delay = min(5.0, backoff * (2**attempt))
                if time.monotonic() - telemetry.started + delay >= op_timeout:
                    raise BedrockTimeoutError() from None
                self._sleep(delay)
            else:
                try:
                    telemetry.observe(response)
                except (AttributeError, TypeError):
                    raise BedrockResponseError() from None
                if telemetry.total_tokens > max_total_tokens:
                    raise BedrockValidationError(("token_budget_exceeded",))
                if time.monotonic() - telemetry.started >= op_timeout:
                    raise BedrockTimeoutError()
                return _text(response)
        raise BedrockUnavailableError()

    def converse_text(
        self,
        *,
        system_prompt: str,
        user_content: str,
        operation_name: str,
        metadata: Mapping[str, str] | None = None,
    ) -> str:
        telemetry = self._telemetry(operation_name, metadata)
        success = False
        try:
            result = self._invoke(
                self._request(system_prompt, user_content, operation_name=operation_name),
                telemetry,
            )
            success = True
            return result
        finally:
            telemetry.finish(success)

    def converse_json(
        self,
        *,
        system_prompt: str,
        user_content: str,
        output_model: type[T],
        operation_name: str,
        metadata: Mapping[str, str] | None = None,
        temperature: float | None = None,
    ) -> T:
        telemetry = self._telemetry(operation_name, metadata)
        telemetry.validation_result = "pending"
        success = False
        try:
            schema = json.dumps(output_model.model_json_schema())
            request = self._request(
                system_prompt + "\nReturn ONLY JSON conforming to this schema: " + schema,
                user_content,
                temperature,
                operation_name=operation_name,
            )
            if getattr(self.settings, "bedrock_native_structured_output", False):
                request["outputConfig"] = {
                    "textFormat": {
                        "type": "json_schema",
                        "structure": {
                            "jsonSchema": {"schema": schema, "name": "counton_output"}
                        },
                    }
                }
            for repair in range(2):
                text = self._invoke(request, telemetry)
                try:
                    result = _validate(text, output_model)
                except BedrockValidationError as error:
                    telemetry.validation_result = "invalid"
                    if repair:
                        raise
                    telemetry.repair_count = 1
                    request["messages"].append(
                        {
                            "role": "assistant",
                            "content": [
                                {
                                    "text": "The previous structured response could not be validated."
                                }
                            ],
                        }
                    )
                    request["messages"].append(
                        {
                            "role": "user",
                            "content": [
                                {
                                    "text": "Repair the response: return one valid JSON document matching the supplied schema with exact field types. No prose, duplicate keys or non-finite numbers. Validation error types: "
                                    + error.feedback
                                }
                            ],
                        }
                    )
                else:
                    telemetry.validation_result = "repaired" if repair else "valid"
                    success = True
                    return result
            raise BedrockValidationError()
        finally:
            telemetry.finish(success)

    def close(self) -> None:
        if self._runtime is not None and hasattr(self._runtime, "close"):
            self._runtime.close()
            self._runtime = None
        if self._client is not None and hasattr(self._client, "close"):
            self._client.close()
            self._client = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
