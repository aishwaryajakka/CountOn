"""Explicit targeting, cwd-independent settings, and acceptance safety."""

import os
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from app.core.config import Settings

LOCAL = "postgresql+psycopg://local_user@localhost/local_database"
SUPABASE = "postgresql+psycopg://remote_user@db.example.supabase.co/postgres"


@pytest.fixture(autouse=True)
def clear_database_overrides(monkeypatch):
    for name in ("DATABASE_URL", "DATABASE_TARGET", "LOCAL_DATABASE_URL", "SUPABASE_DATABASE_URL"):
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
                            env=environment, capture_output=True, text=True, timeout=10)
    assert result.returncode == 1
    assert result.stdout.strip() == message
    assert result.stderr == ""
