"""AWS preflight uses mocked credentials/STS and never calls the model."""

from unittest.mock import Mock

import pytest
from botocore.exceptions import (
    ClientError,
    CredentialRetrievalError,
    LoginRefreshRequired,
)

from db.scripts import aws_preflight
from tests.test_bedrock_smoke import settings


def session(provider="login"):
    result = Mock(profile_name="default")
    result.get_credentials.return_value.method = provider
    result.get_credentials.return_value.get_frozen_credentials.return_value = Mock(access_key="private-access-key", secret_key="private-secret")
    return result


def test_local_resolution_is_not_claimed_as_model_access(capsys):
    sdk = session()
    assert aws_preflight.run(settings(bedrock_enabled=False), session=sdk) == 0
    sdk.client.assert_not_called()
    assert "NOT VERIFIED" in capsys.readouterr().out


def test_sts_identity_never_printed_and_timeouts_are_bounded(capsys):
    sdk = session()
    sdk.client.return_value.get_caller_identity.return_value = {"Account": "private-account", "Arn": "private-user"}
    assert aws_preflight.run(settings(), session=sdk, verify_identity=True) == 0
    assert sdk.client.call_args.args == ("sts",)
    config = sdk.client.call_args.kwargs["config"]
    assert config.connect_timeout == 5 and config.read_timeout == 5
    assert config.retries["total_max_attempts"] == 1
    assert "private" not in capsys.readouterr().out
    sdk.client.return_value.close.assert_called_once()


def test_expired_login_has_correct_refresh_not_sso(capsys):
    sdk = session()
    sdk.get_credentials.return_value.get_frozen_credentials.side_effect = LoginRefreshRequired()
    assert aws_preflight.run(settings(), session=sdk) == 1
    output = capsys.readouterr().out
    assert "LoginRefreshRequired" in output
    assert "aws login --profile default" in output
    assert "aws sso login" not in output
    sdk.client.assert_not_called()


def test_credential_process_error_does_not_echo_command_or_output(capsys):
    sdk = session()
    sdk.get_credentials.side_effect = CredentialRetrievalError(provider="custom-process", error_msg="private-secret Authorization")
    assert aws_preflight.run(settings(), session=sdk) == 1
    output = capsys.readouterr().out
    assert "credential_process" in output
    assert "private-secret" not in output and "Authorization" not in output


@pytest.mark.parametrize("code,expected", [("ExpiredToken", "ExpiredToken"), ("private-secret", "UNKNOWN_AWS_ERROR"), (["private-secret"], "UNKNOWN_AWS_ERROR")])
def test_identity_errors_only_print_allowlisted_code(code, expected, capsys):
    sdk = session()
    sdk.client.return_value.get_caller_identity.side_effect = ClientError({"Error": {"Code": code, "Message": "private-secret"}}, "GetCallerIdentity")
    assert aws_preflight.run(settings(), session=sdk, verify_identity=True) == 1
    text = capsys.readouterr().out
    assert expected in text and "private-secret" not in text


def test_missing_credentials_does_not_call_sts(capsys):
    sdk = session()
    sdk.get_credentials.return_value = None
    assert aws_preflight.run(settings(), session=sdk, verify_identity=True) == 1
    sdk.client.assert_not_called()
    assert "FAIL" in capsys.readouterr().out
