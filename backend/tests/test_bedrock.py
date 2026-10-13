"""Offline infrastructure contracts: never invoke AWS or business services."""

import json
import logging
from datetime import datetime, timezone
from enum import Enum
from unittest.mock import Mock

import pytest
from app.ai.bedrock_client import BedrockClient
from app.ai.exceptions import (
    BedrockDisabledError,
    BedrockResponseError,
    BedrockThrottledError,
    BedrockTimeoutError,
    BedrockUnavailableError,
    BedrockValidationError,
)
from app.ai.prompts import compilation_input
from app.core.config import Settings
from app.core.logging import StructuredFormatter
from app.core.observability import request_id
from botocore.exceptions import (
    ClientError,
    EndpointConnectionError,
    NoCredentialsError,
    ReadTimeoutError,
)
from pydantic import BaseModel, ConfigDict, ValidationError


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: int


class Choice(str, Enum):
    YES = "yes"


class Alternate(BaseModel):
    choice: Choice
    at: datetime


def response(text='{"answer": 42}', **kwargs):
    return {
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
        "stopReason": "end_turn",
        "usage": {"inputTokens": 3, "outputTokens": 5, "totalTokens": 8},
        "metrics": {"latencyMs": 7},
        "ResponseMetadata": {"RequestId": "aws-safe-id"},
        **kwargs,
    }


def settings(**changes):
    return Settings(
        _env_file=None,
        database_target="local",
        local_database_url="postgresql+psycopg://localhost/test",
        bedrock_enabled=True,
        aws_region="us-east-2",
        bedrock_model_id="test-model",
        **changes,
    )


def client(*replies, **changes):
    runtime = Mock()
    runtime.converse.side_effect = list(replies)
    sleep = Mock()
    return (
        BedrockClient(settings(**changes), runtime=runtime, sleep=sleep),
        runtime,
        sleep,
    )


def call(adapter, **kwargs):
    return adapter.converse_json(
        system_prompt="safe system",
        user_content="safe input",
        output_model=Output,
        operation_name="test_json",
        **kwargs,
    )


def aws_error(code):
    return ClientError(
        {"Error": {"Code": code, "Message": "SECRET provider payload"}}, "Converse"
    )


def test_text_and_request_settings():
    adapter, runtime, _ = client(response("hello"))
    assert (
        adapter.converse_text(
            system_prompt="system", user_content="input", operation_name="text"
        )
        == "hello"
    )
    request = runtime.converse.call_args.kwargs
    assert request["modelId"] == "test-model"
    assert request["inferenceConfig"] == {"maxTokens": 1000, "temperature": 0.1}
    assert request["messages"] == [{"role": "user", "content": [{"text": "input"}]}]


@pytest.mark.parametrize(
    "payload",
    [
        '{"answer":42}',
        ' \n{"answer":42}\n ',
        '```json\n{"answer":42}\n```',
        '```\n{"answer":42}\n```',
    ],
)
def test_typed_json_and_incidental_formatting(payload):
    adapter, runtime, _ = client(response(payload))
    result = call(adapter)
    assert isinstance(result, Output) and result.answer == 42
    assert runtime.converse.call_count == 1


@pytest.mark.parametrize(
    "bad",
    [
        "not json",
        "{'answer':42}",
        '{"answer":"42"}',
        '{"answer":true}',
        '{"answer":42,"extra":1}',
        '{"answer":NaN}',
        '{"answer":1,"answer":42}',
        'Here is JSON: {"answer":42}',
        "{}",
    ],
)
def test_invalid_json_or_schema_repair_fails_once(bad):
    adapter, runtime, _ = client(response(bad), response(bad))
    with pytest.raises(BedrockValidationError, match="structured validation"):
        call(adapter)
    assert runtime.converse.call_count == 2


def test_repair_success_no_raw_invalid_response_in_feedback():
    adapter, runtime, _ = client(response("SECRET invalid answer"), response())
    assert call(adapter).answer == 42
    messages = runtime.converse.call_args.kwargs["messages"]
    assert "SECRET" not in json.dumps(messages)
    assert "Repair the response" in messages[-1]["content"][0]["text"]


def test_generic_json_mode_dates_and_enum_strict():
    adapter, _, _ = client(response('{"choice":"yes","at":"2026-10-08T00:00:00Z"}'))
    result = adapter.converse_json(
        system_prompt="s",
        user_content="u",
        output_model=Alternate,
        operation_name="alternate",
    )
    assert (
        isinstance(result, Alternate)
        and result.choice is Choice.YES
        and result.at.tzinfo is not None
    )
    adapter, _, _ = client(
        response('{"choice":"YES","at":"2026-10-08T00:00:00Z"}'), response("{}")
    )
    with pytest.raises(BedrockValidationError):
        adapter.converse_json(
            system_prompt="s",
            user_content="u",
            output_model=Alternate,
            operation_name="alternate",
        )


@pytest.mark.parametrize(
    "error,expected,retryable",
    [
        (ReadTimeoutError(endpoint_url="SECRET"), BedrockTimeoutError, True),
        (EndpointConnectionError(endpoint_url="SECRET"), BedrockUnavailableError, True),
        (aws_error("ModelTimeoutException"), BedrockTimeoutError, True),
        (aws_error("ThrottlingException"), BedrockThrottledError, True),
        (aws_error("ServiceUnavailableException"), BedrockUnavailableError, True),
        (aws_error("InternalServerException"), BedrockUnavailableError, True),
        (aws_error("AccessDeniedException"), BedrockUnavailableError, False),
        (aws_error("ValidationException"), BedrockUnavailableError, False),
        (aws_error("UnknownException"), BedrockUnavailableError, False),
        (NoCredentialsError(), BedrockUnavailableError, False),
    ],
)
def test_safe_aws_mapping_bounded_retries(error, expected, retryable):
    adapter, runtime, sleep = client(error, error, error)
    with pytest.raises(expected) as exc:
        call(adapter)
    assert "SECRET" not in str(exc.value)
    assert runtime.converse.call_count == (3 if retryable else 1)
    assert sleep.call_count == (2 if retryable else 0)
    if retryable:
        assert [item.args[0] for item in sleep.call_args_list] == [0.1, 0.2]


def test_transient_recovery_and_retry_zero():
    adapter, runtime, _ = client(aws_error("ThrottlingException"), response())
    assert call(adapter).answer == 42 and runtime.converse.call_count == 2
    adapter, runtime, sleep = client(
        aws_error("ThrottlingException"), bedrock_max_retries=0
    )
    with pytest.raises(BedrockThrottledError):
        call(adapter)
    assert runtime.converse.call_count == 1 and not sleep.called


@pytest.mark.parametrize(
    "reply",
    [
        {},
        response(""),
        response(stopReason="max_tokens"),
        response(output={"message": {"role": "user", "content": []}}),
        response(
            output={"message": {"role": "assistant", "content": [{"toolUse": {}}]}}
        ),
        response(usage=None),
    ],
)
def test_missing_or_unusable_content_not_repaired(reply):
    adapter, runtime, _ = client(reply)
    with pytest.raises(BedrockResponseError):
        call(adapter)
    assert runtime.converse.call_count == 1


def test_disabled_lazy_no_aws_boot(monkeypatch):
    factory = Mock(side_effect=AssertionError("AWS must not be touched"))
    monkeypatch.setattr("app.ai.bedrock_client.boto3.client", factory)
    disabled = settings().model_copy(update={"bedrock_enabled": False})
    adapter = BedrockClient(disabled)
    with pytest.raises(BedrockDisabledError):
        call(adapter)
    assert not factory.called


def test_lazy_factory_credential_chain_and_sdk_retry_config(monkeypatch):
    runtime = Mock()
    runtime.converse.return_value = response()
    factory = Mock(return_value=runtime)
    monkeypatch.setattr("app.ai.bedrock_client.boto3.client", factory)
    with BedrockClient(settings()) as adapter:
        assert not factory.called
        assert call(adapter).answer == 42
    assert runtime.close.call_count == 1
    kwargs = factory.call_args.kwargs
    assert set(kwargs) == {"region_name", "config"}
    assert kwargs["config"].retries["total_max_attempts"] == 1
    assert kwargs["config"].read_timeout == 30


def test_missing_config_and_creation_failure(monkeypatch):
    adapter = BedrockClient(settings().model_copy(update={"bedrock_model_id": None}))
    with pytest.raises(BedrockUnavailableError):
        call(adapter)
    monkeypatch.setattr(
        "app.ai.bedrock_client.boto3.client", Mock(side_effect=NoCredentialsError())
    )
    with pytest.raises(BedrockUnavailableError):
        call(BedrockClient(settings()))


def test_native_schema_and_installed_sdk_support():
    from botocore.session import Session

    shape = (
        Session()
        .get_service_model("bedrock-runtime")
        .operation_model("Converse")
        .input_shape
    )
    assert "outputConfig" in shape.members
    adapter, runtime, _ = client(response(), bedrock_native_structured_output=True)
    call(adapter)
    config = runtime.converse.call_args.kwargs["outputConfig"]["textFormat"]
    assert config["type"] == "json_schema"
    assert (
        json.loads(config["structure"]["jsonSchema"]["schema"])
        == Output.model_json_schema()
    )


def test_safe_structured_telemetry_usage_and_correlation(caplog):
    adapter, _, _ = client(
        aws_error("ThrottlingException"), response("invalid"), response()
    )
    token = request_id.set("correlation-id")
    try:
        with caplog.at_level(logging.INFO, logger="app.ai.bedrock"):
            call(
                adapter,
                metadata={
                    "prompt_version": "v1",
                    "Authorization": "SECRET",
                    "user_prompt": "SECRET",
                },
            )
        record = caplog.records[-1]
        payload = json.loads(StructuredFormatter().format(record))
        assert payload["request_id"] == "correlation-id"
        assert payload["aws_request_id"] == "aws-safe-id"
        assert payload["retry_count"] == 1 and payload["repair_count"] == 1
        assert (
            payload["validation_result"] == "repaired"
            and payload["result_status"] == "success"
        )
        assert (
            payload["input_tokens"] == 6
            and payload["output_tokens"] == 10
            and payload["total_tokens"] == 16
        )
        assert payload["duration_ms"] >= 0 and payload["model_latency_ms"] == 14
        assert payload["prompt_version"] == "v1"
        assert "SECRET" not in json.dumps(payload)
    finally:
        request_id.reset(token)


def test_failure_logs_exclude_prompts_tokens_and_sdk_payloads(caplog):
    adapter, _, _ = client(aws_error("AccessDeniedException"))
    with (
        caplog.at_level(logging.WARNING, logger="app.ai.bedrock"),
        pytest.raises(BedrockUnavailableError),
    ):
        adapter.converse_text(
            system_prompt="SECRET JWT",
            user_content="SECRET database URL",
            operation_name="failure",
            metadata={"prompt_version": "SECRET.bad.token"},
        )
    payload = json.loads(StructuredFormatter().format(caplog.records[-1]))
    assert payload["result_status"] == "failure" and payload["prompt_version"] is None
    assert "SECRET" not in json.dumps(payload) and not caplog.records[-1].exc_info


def test_compilation_context_minimization_and_awareness():
    result = json.loads(
        compilation_input(
            text="grocery limit",
            timezone="America/Chicago",
            reference_time=datetime(2026, 10, 8, tzinfo=timezone.utc),
        )
    )
    assert set(result) == {"text", "timezone", "reference_time"}
    assert result["reference_time"].endswith("-05:00")
    with pytest.raises(ValueError):
        compilation_input(
            text="x",
            timezone="UTC",
            reference_time=datetime(2026, 10, 8, tzinfo=None),  # noqa: DTZ001 - deliberately naive input
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("bedrock_max_retries", 6),
        ("bedrock_temperature", 2),
        ("bedrock_max_tokens", 0),
        ("bedrock_request_timeout_seconds", 0),
    ],
)
def test_configuration_bounds(field, value):
    with pytest.raises(ValidationError):
        settings(**{field: value})


def test_total_retry_budget_including_single_repair():
    throttle = aws_error("ThrottlingException")
    adapter, runtime, sleep = client(
        throttle, throttle, response("invalid"), throttle, throttle, response()
    )
    assert call(adapter).answer == 42
    assert runtime.converse.call_count == 6 and sleep.call_count == 4


def test_failed_aws_request_id_is_safe_telemetry(caplog):
    error = ClientError(
        {
            "Error": {"Code": "AccessDeniedException", "Message": "SECRET"},
            "ResponseMetadata": {"RequestId": "aws-failed-id"},
        },
        "Converse",
    )
    adapter, _, _ = client(error)
    with (
        caplog.at_level(logging.WARNING, logger="app.ai.bedrock"),
        pytest.raises(BedrockUnavailableError),
    ):
        call(adapter)
    assert caplog.records[-1].aws_request_id == "aws-failed-id"
