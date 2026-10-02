"""Settings are file-backed, cwd-independent, and never embed credentials."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_settings_use_backend_env_local(monkeypatch, tmp_path):
    from app.core import config
    monkeypatch.chdir(tmp_path)
    expected = Path(config.__file__).resolve().parents[2] / ".env.local"
    assert Settings.model_config["env_file"] == expected
    assert expected.is_absolute()


def test_explicit_environment_overrides_env_local(monkeypatch, tmp_path):
    env_file = tmp_path / ".env.local"
    env_file.write_text("DATABASE_URL=postgresql+psycopg://file_user@localhost/file_database\n")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://environment_user@localhost/environment_database")
    settings = Settings(_env_file=env_file)
    assert settings.database_url == "postgresql+psycopg://environment_user@localhost/environment_database"


def test_database_url_is_required_without_file_or_environment(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError) as error:
        Settings(_env_file=None)
    assert any(item["loc"] == ("database_url",) for item in error.value.errors())
