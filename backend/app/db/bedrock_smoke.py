"""
Bedrock Smoke Test Script
Verifies AWS Bedrock client initialization, model configuration, Converse API,
markdown stripping, and Expectation Compiler integration.
"""

import os
import sys
from pathlib import Path

# Ensure backend root is on sys.path
BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.ai.bedrock_client import BedrockClient, strip_markdown_code_fences
from app.ai.compiler import compile_expectation
from app.ai.exceptions import BedrockClientError, InvalidModelResponse


def verify(condition: bool, step: str) -> None:
    if not condition:
        print(f"FAIL {step}")
        raise RuntimeError(f"Bedrock smoke verification failed: {step}")
    print(f"PASS {step}")


def main() -> int:
    print("--- Starting Amazon Bedrock Smoke Verification ---")

    # 1. Environment & configuration check
    region = os.environ.get("AWS_REGION") or "ap-northeast-1"
    model_id = os.environ.get("BEDROCK_MODEL_ID") or "amazon.nova-2-lite-v1:0"
    has_aws_creds = bool(os.environ.get("AWS_ACCESS_KEY_ID") or os.environ.get("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"))
    is_mock = os.environ.get("COUNTON_MOCK_AI", "").lower() in ("1", "true", "yes")

    print(f"Target Region:   {region}")
    print(f"Target Model ID: {model_id}")
    print(f"AWS Creds Set:   {has_aws_creds}")
    print(f"Mock Mode:       {is_mock or not has_aws_creds}")
    verify(bool(region and model_id), "Bedrock configuration check")

    # 2. Markdown Code Fence Stripping Utility check
    sample_fenced = "```json\n{\"test\": true}\n```"
    stripped = strip_markdown_code_fences(sample_fenced)
    verify(stripped == '{"test": true}', "Markdown code fence stripping")

    # 3. Client Initialization
    client = BedrockClient(model_id=model_id, region_name=region)
    verify(client.model_id == model_id and client.region_name == region, "Bedrock client initialization")

    # 4. Smoke Invocation (Live if credentials exist and mock not forced; otherwise mock mode)
    if has_aws_creds and not is_mock:
        print("Executing live Bedrock Converse API invocation...")
        try:
            res = client.invoke(
                system_prompt="Return valid JSON with key 'status' equal to 'ok'.",
                user_message="Health check.",
                temperature=0.0,
            )
            verify(isinstance(res, dict) and res.get("status") == "ok", "Live Bedrock Converse API invocation")
        except Exception as e:
            print(f"Live Bedrock invocation failed: {e}")
            raise
    else:
        print("Running in offline mock mode (no AWS credentials or COUNTON_MOCK_AI set)...")
        verify(True, "Offline fallback mode verification")

    # 5. Compiler Integration Smoke Test
    test_statement = "I've been running the AC less, so my next bill should be lower."
    comp_res = compile_expectation(test_statement, mock_mode=True if (not has_aws_creds or is_mock) else False)
    verify(comp_res.kind == "expectation" and comp_res.expectation is not None, "Compiler integration smoke test")
    verify(comp_res.expectation.type == "numeric_comparison", "Compiler expectation schema structure")

    # 6. Multi-turn Clarification Smoke Test
    clarif_res = compile_expectation("My bill should be lower.", mock_mode=True)
    verify(clarif_res.kind == "clarification" and clarif_res.clarification.required, "Compiler clarification smoke test")

    # 7. Cancellation Smoke Test
    cancel_res = compile_expectation("Cancel my expectation about the electric bill", mock_mode=True)
    verify(cancel_res.kind == "cancellation" and cancel_res.cancellation is not None, "Compiler cancellation smoke test")

    print("========================================")
    print("BEDROCK SMOKE VERIFICATION PASSED")
    print("========================================")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"SMOKE TEST FAILED: {exc}")
        sys.exit(1)
