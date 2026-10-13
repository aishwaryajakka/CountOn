"""Opt-in harmless Bedrock inference; no database, MCP or frontend operations."""

import argparse
import json
import logging
import re
import sys
from pathlib import Path
from typing import Literal

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from pydantic import BaseModel, ConfigDict, ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from app.core.config import Settings, get_settings

# Service error identifiers only: never echo provider messages or arbitrary codes.
AWS_ERROR_CODES = {
    "AccessDeniedException",
    "ValidationException",
    "ResourceNotFoundException",
    "ThrottlingException",
    "ServiceUnavailableException",
    "InternalServerException",
    "ModelTimeoutException",
    "ModelNotReadyException",
    "ModelErrorException",
    "ServiceQuotaExceededException",
    "UnrecognizedClientException",
    "InvalidClientTokenId",
    "ExpiredTokenException",
    "ExpiredToken",
    "SignatureDoesNotMatch",
    "IncompleteSignature",
    "RequestExpired",
}


class SmokeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    status: Literal["ok"]
    purpose: Literal["counton"]


class UnusableResponse(Exception):
    pass


def validate_response(response: object) -> SmokeOutput:
    try:
        if not isinstance(response, dict) or response.get("stopReason") != "end_turn":
            raise UnusableResponse()
        message = response["output"]["message"]
        blocks = message["content"]
        if message["role"] != "assistant" or not isinstance(blocks, list):
            raise UnusableResponse()
        texts = []
        for block in blocks:
            if not isinstance(block, dict):
                raise UnusableResponse()
            if set(block) == {"text"} and isinstance(block["text"], str):
                texts.append(block["text"])
            elif set(block) != {"reasoningContent"}:
                # Reasoning-capable models can include a separate private block.
                # Ignore it; never print it or treat it as the JSON answer.
                raise UnusableResponse()
        payload = "".join(texts).strip()
        fenced = re.fullmatch(r"```(?:json)?\s*\n(.*?)\n```", payload, re.DOTALL)
        payload = fenced.group(1) if fenced else payload

        def pairs(items):
            result = {}
            for key, value in items:
                if key in result:
                    raise UnusableResponse()
                result[key] = value
            return result

        return SmokeOutput.model_validate(json.loads(payload, object_pairs_hook=pairs))
    except (KeyError, TypeError, ValueError, ValidationError, RecursionError):
        raise UnusableResponse() from None


def run(settings: Settings) -> int:
    if not settings.bedrock_enabled:
        print("FAIL Bedrock disabled (BEDROCK_ENABLED=false); no invocation attempted")
        return 1
    model = settings.bedrock_model_id
    if not re.fullmatch(r"[A-Za-z0-9.:/_-]{1,256}", model) or "://" in model:
        print("FAIL invalid model configuration; value omitted")
        return 1
    print(f"Model: {model}")
    runtime = None
    try:
        # No explicit credential arguments: boto3 uses its normal provider chain.
        runtime = boto3.client(
            "bedrock-runtime",
            region_name=settings.aws_region,
            config=Config(
                connect_timeout=settings.bedrock_request_timeout_seconds,
                read_timeout=settings.bedrock_request_timeout_seconds,
                retries={
                    "mode": "standard",
                    "total_max_attempts": 1 + settings.bedrock_max_retries,
                },
            ),
        )
        response = runtime.converse(
            modelId=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "text": 'Return only this JSON object, without commentary: {"status":"ok","purpose":"counton"}'
                        }
                    ],
                }
            ],
            inferenceConfig={
                "maxTokens": settings.bedrock_max_tokens,
                "temperature": settings.bedrock_temperature,
            },
        )
        validate_response(response)
    except ClientError as error:
        code = error.response.get("Error", {}).get("Code")
        safe_code = (
            code
            if isinstance(code, str) and code in AWS_ERROR_CODES
            else "UNKNOWN_AWS_ERROR"
        )
        print("FAIL Bedrock invocation")
        print(f"AWS error code: {safe_code}")
        return 1
    except BotoCoreError as error:
        # Public exception class only, never its credential-bearing message.
        name = type(error).__name__
        print("FAIL Bedrock invocation")
        print("AWS error code: none returned")
        print(
            f"SDK error: {name if re.fullmatch(r'[A-Za-z]{1,64}', name) else 'BotoCoreError'}"
        )
        return 1
    except UnusableResponse:
        print("FAIL model response was not the requested usable JSON")
        print("AWS error code: none returned")
        return 1
    except Exception:  # noqa: BLE001 — suppress any credential-bearing exception payload
        print("FAIL smoke could not complete; private details suppressed")
        return 1
    finally:
        if runtime is not None:
            try:
                runtime.close()
            except Exception:  # noqa: BLE001, S110 — cleanup must not expose provider data
                pass
    print("PASS Bedrock reachable; response validated")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live",
        action="store_true",
        help="Explicitly authorize a billed harmless inference",
    )
    args = parser.parse_args()
    if not args.live:
        print("SKIPPED: pass --live and set BEDROCK_ENABLED=true to run")
        return 0
    # Suppress SDK/HTTP debug output, even if a parent process enabled logging.
    logging.disable(logging.CRITICAL)
    try:
        settings = get_settings()
    except Exception:  # noqa: BLE001 — settings errors may contain private values
        print("FAIL backend configuration is invalid; private details suppressed")
        return 1
    return run(settings)


if __name__ == "__main__":
    raise SystemExit(main())
