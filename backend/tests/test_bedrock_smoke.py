"""
Bedrock Smoke Test and Unit Tests for AWS Bedrock integration.
"""

import pytest
from unittest.mock import patch, MagicMock

from app.ai.bedrock_client import BedrockClient, strip_markdown_code_fences
from app.ai.compiler import compile_expectation
from app.ai.exceptions import BedrockClientError, InvalidModelResponse, ExpectationCompilationError


def test_markdown_code_fence_stripping():
    # Markdown with json tag
    raw = "```json\n{\"claim\": \"test\"}\n```"
    assert strip_markdown_code_fences(raw) == '{"claim": "test"}'

    # Markdown without json tag
    raw2 = "```\n{\"claim\": \"test2\"}\n```"
    assert strip_markdown_code_fences(raw2) == '{"claim": "test2"}'

    # Plain JSON
    plain = '{"claim": "plain"}'
    assert strip_markdown_code_fences(plain) == plain


def test_bedrock_client_config():
    client = BedrockClient(model_id="custom-model", region_name="us-east-1")
    assert client.model_id == "custom-model"
    assert client.region_name == "us-east-1"


@patch("boto3.client")
def test_bedrock_client_invoke_success(mock_boto_client):
    mock_runtime = MagicMock()
    mock_boto_client.return_value = mock_runtime

    mock_runtime.converse.return_value = {
        "output": {
            "message": {
                "content": [
                    {
                        "text": '```json\n{"status": "ok", "result": 123}\n```'
                    }
                ]
            }
        }
    }

    client = BedrockClient(model_id="amazon.nova-2-lite-v1:0", region_name="ap-northeast-1")
    res = client.invoke(system_prompt="sys", user_message="usr")
    assert res == {"status": "ok", "result": 123}


@patch("boto3.client")
def test_bedrock_client_empty_response(mock_boto_client):
    mock_runtime = MagicMock()
    mock_boto_client.return_value = mock_runtime
    mock_runtime.converse.return_value = {"output": {"message": {"content": []}}}

    client = BedrockClient()
    with pytest.raises(InvalidModelResponse):
        client.invoke("sys", "usr")


@patch("boto3.client")
def test_bedrock_client_invalid_json(mock_boto_client):
    mock_runtime = MagicMock()
    mock_boto_client.return_value = mock_runtime
    mock_runtime.converse.return_value = {
        "output": {
            "message": {
                "content": [{"text": "Not valid JSON at all"}]
            }
        }
    }

    client = BedrockClient()
    with pytest.raises(InvalidModelResponse):
        client.invoke("sys", "usr")


@patch("boto3.client")
def test_bedrock_client_api_error(mock_boto_client):
    mock_runtime = MagicMock()
    mock_boto_client.return_value = mock_runtime
    mock_runtime.converse.side_effect = Exception("ThrottlingException: Rate exceeded")

    client = BedrockClient()
    with pytest.raises(BedrockClientError) as exc_info:
        client.invoke("sys", "usr")
    assert "Rate exceeded" in str(exc_info.value)
