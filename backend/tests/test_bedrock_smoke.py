"""Standalone probe safety: mocked boto3 only, no inference in the test suite."""

from unittest.mock import Mock

import pytest
from app.core.config import Settings
from botocore.exceptions import ClientError, NoCredentialsError
from db.scripts import bedrock_smoke as smoke


def settings(**changes):
    return Settings(
        _env_file=None,
        database_target="local",
        local_database_url="postgresql+psycopg://localhost/test",
        bedrock_enabled=changes.pop("bedrock_enabled", True),
        **changes,
    )


def response(text='{"status":"ok","purpose":"counton"}', **changes):
    return {
        "stopReason": "end_turn",
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
        **changes,
    }


def test_success_settings_and_provider_chain(monkeypatch, capsys):
    runtime = Mock()
    runtime.converse.return_value = response()
    factory = Mock(return_value=runtime)
    monkeypatch.setattr(smoke.boto3, "client", factory)
    assert smoke.run(settings()) == 0
    assert set(factory.call_args.kwargs) == {"region_name", "config"}
    assert factory.call_args.args == ("bedrock-runtime",)
    assert factory.call_args.kwargs["region_name"] == "us-east-2"
    assert runtime.converse.call_args.kwargs["modelId"] == "openai.gpt-oss-120b-1:0"
    assert (
        '"status":"ok","purpose":"counton"'
        in runtime.converse.call_args.kwargs["messages"][0]["content"][0]["text"]
    )
    assert "PASS Bedrock reachable" in capsys.readouterr().out
    runtime.close.assert_called_once()


def test_disabled_does_not_create_sdk_client(monkeypatch, capsys):
    factory = Mock()
    monkeypatch.setattr(smoke.boto3, "client", factory)
    assert smoke.run(settings(bedrock_enabled=False)) == 1
    factory.assert_not_called()
    assert "disabled" in capsys.readouterr().out


@pytest.mark.parametrize(
    "code,expected",
    [
        ("AccessDeniedException", "AccessDeniedException"),
        ("ExpiredTokenException", "ExpiredTokenException"),
        ("private-provider-secret", "UNKNOWN_AWS_ERROR"),
    ],
)
def test_aws_failure_code_only(monkeypatch, capsys, code, expected):
    runtime = Mock()
    runtime.converse.side_effect = ClientError(
        {
            "Error": {
                "Code": code,
                "Message": "AWS_SECRET_ACCESS_KEY private-provider-secret Authorization: secret",
            }
        },
        "Converse",
    )
    monkeypatch.setattr(smoke.boto3, "client", Mock(return_value=runtime))
    assert smoke.run(settings()) == 1
    text = capsys.readouterr().out
    assert f"AWS error code: {expected}" in text
    assert (
        "private-provider-secret" not in text
        and "Authorization" not in text
        and "AWS_SECRET_ACCESS_KEY" not in text
    )


def test_credentials_unavailable_no_exception_payload(monkeypatch, capsys):
    monkeypatch.setattr(smoke.boto3, "client", Mock(side_effect=NoCredentialsError()))
    assert smoke.run(settings()) == 1
    text = capsys.readouterr().out
    assert "SDK error: NoCredentialsError" in text
    assert "AWS error code: none returned" in text


@pytest.mark.parametrize(
    "text",
    [
        "bad json",
        '{"status":"bad","purpose":"counton"}',
        '{"status":"ok","purpose":"other"}',
        '{"status":"ok","purpose":"counton","token":"private"}',
        '{"status":"bad","status":"ok","purpose":"counton"}',
    ],
)
def test_invalid_output_rejected_without_printing_it(monkeypatch, capsys, text):
    runtime = Mock()
    runtime.converse.return_value = response(text)
    monkeypatch.setattr(smoke.boto3, "client", Mock(return_value=runtime))
    assert smoke.run(settings()) == 1
    assert text not in capsys.readouterr().out


def test_private_reasoning_is_not_response_or_output(monkeypatch, capsys):
    output = response()
    output["output"]["message"]["content"].insert(
        0, {"reasoningContent": {"reasoningText": {"text": "private-reasoning"}}}
    )
    runtime = Mock()
    runtime.converse.return_value = output
    monkeypatch.setattr(smoke.boto3, "client", Mock(return_value=runtime))
    assert smoke.run(settings()) == 0
    assert "private-reasoning" not in capsys.readouterr().out


@pytest.mark.parametrize("stop", ["max_tokens", "tool_use", "guardrail_intervened"])
def test_incomplete_response_rejected(stop):
    with pytest.raises(smoke.UnusableResponse):
        smoke.validate_response(response(stopReason=stop))


def test_cli_no_live_flag_does_not_load_configuration(monkeypatch, capsys):
    factory = Mock()
    monkeypatch.setattr(smoke, "get_settings", factory)
    monkeypatch.setattr("sys.argv", ["bedrock_smoke.py"])
    assert smoke.main() == 0
    factory.assert_not_called()
    assert "SKIPPED" in capsys.readouterr().out
