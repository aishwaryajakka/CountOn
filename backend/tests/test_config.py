"""Explicit targeting, cwd-independent settings, and acceptance safety."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings

LOCAL = "postgresql+psycopg://local_user@localhost/local_database"
SUPABASE = "postgresql+psycopg://remote_user@db.example.supabase.co/postgres"


@pytest.mark.parametrize('origin', [
    'https://*', 'https://host.test:0', 'https://host.test:65536',
    'https://host.test:invalid', 'https://host .test', 'https://host.test?',
    'https://host.test#', 'https://user:private-password@host.test',
])
@pytest.mark.parametrize('field', ['allowed_origins', 'supabase_url'])
def test_auth_and_cors_origins_fail_closed(field, origin):
    value = [origin] if field == 'allowed_origins' else origin
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, database_target='local', local_database_url=LOCAL, **{field: value})
    assert 'private-password' not in str(error.value)
    assert 'input_value' not in str(error.value)


def test_valid_explicit_origin_ports_and_ipv6():
    settings = Settings(_env_file=None, database_target='local', local_database_url=LOCAL,
                        allowed_origins=['https://ui.test:8443', 'http://[::1]:3000'],
                        supabase_url='https://auth.test:8443')
    assert settings.allowed_origins == ['https://ui.test:8443', 'http://[::1]:3000']


@pytest.fixture(autouse=True)
def clear_database_overrides(monkeypatch):
    for name in ("DATABASE_URL", "DATABASE_TARGET", "LOCAL_DATABASE_URL", "SUPABASE_DATABASE_URL",
                 "BEDROCK_ENABLED", "AWS_REGION", "BEDROCK_MODEL_ID", "BEDROCK_MAX_TOKENS",
                 "BEDROCK_TEMPERATURE", "BEDROCK_REQUEST_TIMEOUT_SECONDS", "BEDROCK_MAX_RETRIES",
                 "MONITORING_ENABLED", "MONITORING_POLL_SECONDS", "MONITORING_LEASE_SECONDS",
                 "MONITORING_BACKOFF_SECONDS", "MICROSOFT_GRAPH_ENABLED", "MICROSOFT_CLIENT_ID",
                 "MICROSOFT_CLIENT_SECRET", "MICROSOFT_TENANT_ID", "MICROSOFT_REDIRECT_URI",
                 "INTEGRATION_TOKEN_ENCRYPTION_KEY"):
        monkeypatch.delenv(name, raising=False)


def test_settings_use_backend_env_local(monkeypatch, tmp_path):
    from app.core import config
    monkeypatch.chdir(tmp_path)
    expected = Path(config.__file__).resolve().parents[2] / ".env.local"
    assert Settings.model_config["env_file"] == expected
    assert expected.is_absolute()


def test_explicit_environment_overrides_env_local(monkeypatch, tmp_path):
    env_file = tmp_path / ".env.local"
    env_file.write_text(f"DATABASE_TARGET=local\nLOCAL_DATABASE_URL={LOCAL}\n")
    override = "postgresql+psycopg://environment_user@localhost/environment_database"
    monkeypatch.setenv("LOCAL_DATABASE_URL", override)
    assert Settings(_env_file=env_file).database_url == override


@pytest.mark.parametrize("target,expected", [("local", LOCAL), ("supabase", SUPABASE)])
def test_database_target_selects_exact_url(target, expected):
    settings = Settings(_env_file=None, database_target=target, local_database_url=LOCAL, supabase_database_url=SUPABASE)
    assert settings.database_url == expected


def test_invalid_database_target_fails_clearly():
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, database_target="foo", local_database_url=LOCAL, supabase_database_url=SUPABASE)
    assert "database_target" in str(error.value)
    assert "local" in str(error.value) and "supabase" in str(error.value)


@pytest.mark.parametrize("target,field", [("local", "LOCAL_DATABASE_URL"), ("supabase", "SUPABASE_DATABASE_URL")])
def test_selected_url_is_required_without_fallback(target, field):
    kwargs = {"supabase_database_url": SUPABASE} if target == "local" else {"local_database_url": LOCAL}
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, database_target=target, **kwargs)
    assert field in str(error.value)


def test_selector_is_required():
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, local_database_url=LOCAL, supabase_database_url=SUPABASE)
    assert "database_target" in str(error.value)


def test_legacy_database_url_does_not_override_selector(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", LOCAL)
    assert Settings(_env_file=None, database_target="supabase", supabase_database_url=SUPABASE).database_url == SUPABASE


def test_invalid_url_error_hides_credentials():
    secret = "private_password"
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, database_target="supabase", supabase_database_url=f"mysql://user:{secret}@host/postgres")
    assert secret not in str(error.value)
    assert "mysql://" not in str(error.value)


@pytest.mark.parametrize("script,target,message", [
    ("local_acceptance.py", "supabase", "Refusing to run local acceptance test because DATABASE_TARGET is not local."),
    ("supabase_acceptance.py", "local", "Refusing to run Supabase acceptance test because DATABASE_TARGET is not supabase."),
])
def test_acceptance_refuses_wrong_target_before_connecting(script, target, message):
    backend = Path(__file__).resolve().parents[1]
    environment = dict(os.environ, DATABASE_TARGET=target, LOCAL_DATABASE_URL=LOCAL, SUPABASE_DATABASE_URL=SUPABASE)
    result = subprocess.run([sys.executable, str(backend / "db/scripts" / script)],
                            env=environment, capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 1
    assert result.stdout.strip() == message
    assert result.stderr == ""


def test_bedrock_defaults():
    settings = Settings(_env_file=None, database_target="local", local_database_url=LOCAL)
    assert settings.bedrock_enabled is False
    assert settings.aws_region == "us-east-2"
    assert settings.bedrock_model_id == "openai.gpt-oss-120b-1:0"
    assert settings.bedrock_max_tokens == 1000
    assert settings.bedrock_temperature == 0.1
    assert settings.bedrock_request_timeout_seconds == 30
    assert type(settings.bedrock_request_timeout_seconds) is int
    assert settings.bedrock_max_retries == 2


def test_alexa_default_is_disabled_and_skill_id_is_environment_backed(monkeypatch):
    monkeypatch.delenv("ALEXA_SKILL_ID", raising=False)
    settings = Settings(_env_file=None, database_target="local", local_database_url=LOCAL)
    assert settings.alexa_skill_id is None
    monkeypatch.setenv("ALEXA_SKILL_ID", "amzn1.ask.skill.test-counton")
    settings = Settings(_env_file=None, database_target="local", local_database_url=LOCAL)
    assert settings.alexa_skill_id == "amzn1.ask.skill.test-counton"


@pytest.mark.parametrize("value", ["", "not-a-skill-id", "https://example.com", "amzn1.ask.skill.bad?secret"])
def test_alexa_skill_id_validation_hides_input(monkeypatch, value):
    monkeypatch.setenv("ALEXA_SKILL_ID", value)
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, database_target="local", local_database_url=LOCAL)
    assert "input_value" not in str(error.value)


@pytest.mark.parametrize("value,expected", [("true", True), ("false", False), ("1", True), ("0", False)])
def test_bedrock_enabled_environment_parsing(monkeypatch, value, expected):
    monkeypatch.setenv("BEDROCK_ENABLED", value)
    settings = Settings(_env_file=None, database_target="local", local_database_url=LOCAL)
    assert settings.bedrock_enabled is expected


def test_bedrock_environment_overrides(monkeypatch):
    for name, value in {
        "AWS_REGION": "us-west-2",
        "BEDROCK_MODEL_ID": "custom-model-id",
        "BEDROCK_MAX_TOKENS": "2048",
        "BEDROCK_TEMPERATURE": "0.25",
        "BEDROCK_REQUEST_TIMEOUT_SECONDS": "45",
        "BEDROCK_MAX_RETRIES": "3",
    }.items():
        monkeypatch.setenv(name, value)
    settings = Settings(_env_file=None, database_target="local", local_database_url=LOCAL)
    assert settings.aws_region == "us-west-2"
    assert settings.bedrock_model_id == "custom-model-id"
    assert settings.bedrock_max_tokens == 2048
    assert settings.bedrock_temperature == 0.25
    assert settings.bedrock_request_timeout_seconds == 45
    assert settings.bedrock_max_retries == 3


@pytest.mark.parametrize("name,value", [
    ("BEDROCK_ENABLED", "invalid"), ("AWS_REGION", ""), ("BEDROCK_MODEL_ID", ""),
    ("BEDROCK_MAX_TOKENS", "0"), ("BEDROCK_TEMPERATURE", "1.1"),
    ("BEDROCK_REQUEST_TIMEOUT_SECONDS", "30.5"), ("BEDROCK_MAX_RETRIES", "-1"),
])
def test_bedrock_invalid_environment_settings_rejected(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_target="local", local_database_url=LOCAL)


def test_bedrock_sample_loads_with_existing_env_loader(tmp_path):
    sample = Path(__file__).resolve().parents[1] / "bedrock.env.sample"
    env_file = tmp_path / ".env.local"
    env_file.write_text(f"DATABASE_TARGET=local\nLOCAL_DATABASE_URL={LOCAL}\n" + sample.read_text())
    settings = Settings(_env_file=env_file)
    assert settings.bedrock_enabled is False
    assert settings.aws_region == "us-east-2"
    assert settings.bedrock_model_id == "openai.gpt-oss-120b-1:0"
    assert settings.bedrock_request_timeout_seconds == 30



def test_monitoring_sample_defaults_and_safe_settings_repr():
    from base64 import urlsafe_b64encode
    sample = Path(__file__).resolve().parents[1] / "monitoring.env.sample"
    settings = Settings(_env_file=sample, database_target="local", local_database_url=LOCAL)
    assert settings.monitoring_enabled is False
    assert settings.microsoft_graph_enabled is False
    assert (settings.monitoring_poll_seconds, settings.monitoring_lease_seconds,
            settings.monitoring_backoff_seconds) == (5, 300, 30)
    secret = "private-test-client-secret"
    settings = Settings(_env_file=None, database_target="local", local_database_url=LOCAL,
                        microsoft_graph_enabled=True,
                        microsoft_client_id="00000000-0000-0000-0000-000000000001",
                        microsoft_client_secret=secret,
                        microsoft_redirect_uri="https://api.test/callback",
                        integration_token_encryption_key=urlsafe_b64encode(b"t" * 32).decode())
    assert secret not in repr(settings)
    assert "integration_token_encryption_key=" not in repr(settings)


@pytest.mark.parametrize("name,value", [
    ("MONITORING_LEASE_SECONDS", "1"), ("MONITORING_POLL_SECONDS", "0"),
    ("MONITORING_BACKOFF_SECONDS", "-1"), ("MICROSOFT_GRAPH_ENABLED", "true"),
    ("MICROSOFT_TENANT_ID", "------------------------------------"),
    ("INTEGRATION_TOKEN_ENCRYPTION_KEY", "private-invalid-encryption-key"),
    ("MICROSOFT_REDIRECT_URI", "https://api.test:invalid/callback"),
    ("MICROSOFT_REDIRECT_URI", "https://user:private-password@api.test/callback"),
    ("MICROSOFT_REDIRECT_URI", "https://api.test/callback?token=private-test-token"),
])
def test_monitoring_configuration_fails_closed_without_exposing_values(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None, database_target="local", local_database_url=LOCAL)
    assert "input_value" not in str(error.value)
    assert "private-" not in str(error.value)


def test_provider_callback_loopback_only_in_development(monkeypatch):
    monkeypatch.setenv("MICROSOFT_REDIRECT_URI", "http://localhost:8000/callback")
    assert Settings(_env_file=None, database_target="local", local_database_url=LOCAL,
                    environment="development").microsoft_redirect_uri
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_target="local", local_database_url=LOCAL,
                 environment="production")
    monkeypatch.setenv("MICROSOFT_REDIRECT_URI", "http://api.test/callback")
    with pytest.raises(ValidationError):
        Settings(_env_file=None, database_target="local", local_database_url=LOCAL)


def test_monitoring_enabled_environment_parsing(monkeypatch):
    monkeypatch.setenv("MONITORING_ENABLED", "true")
    assert Settings(_env_file=None, database_target="local", local_database_url=LOCAL).monitoring_enabled
