"""Lazy synchronous Converse adapter. No database, services or MCP mutations."""

import json
import re
import time
from collections.abc import Callable, Mapping
from typing import Any, Protocol, Self, TypeVar

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
    BedrockDisabledError,
    BedrockError,
    BedrockResponseError,
    BedrockThrottledError,
    BedrockTimeoutError,
    BedrockUnavailableError,
    BedrockValidationError,
)
from app.ai.telemetry import CallTelemetry, safe_label
from app.core.config import Settings, get_settings

T = TypeVar("T", bound=BaseModel)


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
    # Credentials, access denied, bad model/config and unknown errors aren't retried.
    return BedrockUnavailableError(), False


def _text(response: dict[str, Any]) -> str:
    try:
        if response.get("stopReason") != "end_turn":
            raise BedrockResponseError()
        message = response["output"]["message"]
        if message["role"] != "assistant":
            raise BedrockResponseError()
        blocks = message["content"]
        # No tool execution, reasoning blocks, citations, or partially truncated output.
        if not isinstance(blocks, list) or not all(
            isinstance(b, dict) and set(b) == {"text"} and isinstance(b["text"], str)
            for b in blocks
        ):
            raise BedrockResponseError()
        text = "".join(block["text"] for block in blocks).strip()
        if not text:
            raise BedrockResponseError()
        return text
    except (KeyError, TypeError, AttributeError):
        raise BedrockResponseError() from None


def _validate(text: str, output_model: type[T]) -> T:
    # Accept only a whole JSON document, optionally wrapped in a single code fence.
    # Never extract a substring from arbitrary prose or accept Python literals.
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
        # JSON-mode strict validation preserves valid JSON representations of dates,
        # UUIDs and enums, while refusing numeric/string coercion.
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


class BedrockClient:
    """Use from sync handlers/services, or offload in an async handler's threadpool.

    Metadata permits only a trusted prompt_version label; never forward metadata
    to AWS or logs wholesale. Client lifetime is caller-owned; close after use.
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        runtime: RuntimeClient | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings or get_settings()
        self._runtime = runtime
        self._sleep = sleep

    def _get_runtime(self) -> RuntimeClient:
        if not self.settings.bedrock_enabled:
            raise BedrockDisabledError()
        if not self.settings.aws_region or not self.settings.bedrock_model_id:
            raise BedrockUnavailableError()
        if self._runtime is None:
            try:
                self._runtime = boto3.client(
                    "bedrock-runtime",
                    region_name=self.settings.aws_region,
                    config=Config(
                        connect_timeout=self.settings.bedrock_request_timeout_seconds,
                        read_timeout=self.settings.bedrock_request_timeout_seconds,
                        # One retry owner: disable SDK retries to avoid multiplication.
                        retries={"mode": "standard", "total_max_attempts": 1},
                    ),
                )
            except (BotoCoreError, ClientError):
                raise BedrockUnavailableError() from None
        return self._runtime

    def _invoke(self, request: dict[str, Any], telemetry: CallTelemetry) -> str:
        runtime = self._get_runtime()
        for attempt in range(self.settings.bedrock_max_retries + 1):
            try:
                response = runtime.converse(**request)
            except (BotoCoreError, ClientError) as error:
                if isinstance(error, ClientError):
                    telemetry.aws_request_id = safe_label(
                        error.response.get("ResponseMetadata", {}).get("RequestId")
                    )
                mapped, retryable = _map_error(error)
                if not retryable or attempt == self.settings.bedrock_max_retries:
                    raise mapped from None
                telemetry.retry_count += 1
                self._sleep(min(5.0, self.settings.http_backoff_seconds * (2**attempt)))
            else:
                try:
                    telemetry.observe(response)
                except (AttributeError, TypeError):
                    raise BedrockResponseError() from None
                return _text(response)
        raise BedrockUnavailableError()

    def _request(
        self, system_prompt: str, user_content: str, temperature: float | None = None
    ) -> dict[str, Any]:
        if temperature is not None and not 0 <= temperature <= 1:
            raise ValueError("temperature must be between zero and one")
        return {
            "modelId": self.settings.bedrock_model_id,
            "system": [{"text": system_prompt}],
            "messages": [{"role": "user", "content": [{"text": user_content}]}],
            "inferenceConfig": {
                "maxTokens": self.settings.bedrock_max_tokens,
                "temperature": self.settings.bedrock_temperature
                if temperature is None
                else temperature,
            },
        }

    def _telemetry(
        self, operation_name: str, metadata: Mapping[str, str] | None
    ) -> CallTelemetry:
        # Operation/version are developer-controlled labels, not utterances/user IDs.
        if safe_label(operation_name) is None:
            raise ValueError("operation_name must be a short operational label")
        model = self.settings.bedrock_model_id
        # Prevent credential URLs or control characters from configuration entering logs.
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
            result = self._invoke(self._request(system_prompt, user_content), telemetry)
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
                system_prompt
                + "\nReturn ONLY JSON conforming to this schema: "
                + schema,
                user_content,
                temperature,
            )
            if self.settings.bedrock_native_structured_output:
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
                    # Keep original selected context, but do not echo invalid model
                    # text, Pydantic input values/locations or exception payloads.
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
        if self._runtime is not None:
            self._runtime.close()
            self._runtime = None

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
