"""Environment-backed settings with one explicit database target."""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[2] / ".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
        hide_input_in_errors=True,
    )

    app_name: str = "CountOn"
    environment: Literal["development", "test", "production"] = "development"
    database_target: Literal["local", "supabase"]
    local_database_url: str | None = Field(default=None, repr=False)
    supabase_database_url: str | None = Field(default=None, repr=False)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"])
    rate_limit_enabled: bool = True
    rate_limit_backend: Literal["memory"] = "memory"
    rate_limit_requests: int = Field(default=300, ge=1, le=100000)
    rate_limit_writes: int = Field(default=100, ge=1, le=100000)
    rate_limit_window_seconds: int = Field(default=60, ge=1, le=3600)
    rate_limit_max_keys: int = Field(default=10000, ge=1, le=1000000)
    http_connect_timeout: float = Field(default=3, gt=0, le=60)
    http_read_timeout: float = Field(default=10, gt=0, le=120)
    http_max_retries: int = Field(default=2, ge=0, le=5)
    http_backoff_seconds: float = Field(default=0.1, ge=0, le=5)
    database_connect_timeout: int = Field(default=5, ge=1, le=60)
    database_statement_timeout_ms: int = Field(default=5000, ge=100, le=120000)
    database_pool_timeout: int = Field(default=5, ge=1, le=60)
    supabase_url: str | None = None
    supabase_jwks_url: str | None = None
    supabase_publishable_key: str | None = Field(default=None, repr=False)
    supabase_secret_key: SecretStr | None = Field(default=None, repr=False)
    counton_demo_user_id: UUID | None = None
    counton_demo_email: str = "demo@counton.app"
    counton_demo_password: SecretStr | None = Field(default=None, repr=False)

    @field_validator("counton_demo_user_id", mode="before")
    @classmethod
    def empty_demo_uuid(cls, value):
        return None if value == "" else value

    @model_validator(mode="after")
    def validate_selected_database(self) -> "Settings":
        selected = self.local_database_url if self.database_target == "local" else self.supabase_database_url
        name = f"{self.database_target.upper()}_DATABASE_URL"
        if not selected:
            raise ValueError(f"{name} is required for DATABASE_TARGET={self.database_target}")
        try:
            url = make_url(selected)
        except Exception:
            raise ValueError(f"{name} is not a valid PostgreSQL URL") from None
        if url.drivername != "postgresql+psycopg" or not url.host or not url.database:
            raise ValueError(f"{name} must use postgresql+psycopg:// with a host and database")
        for origin in self.allowed_origins:
            parsed = urlsplit(origin)
            if (parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.path
                    or parsed.query or parsed.fragment or parsed.username or parsed.password):
                raise ValueError("ALLOWED_ORIGINS must contain explicit HTTP(S) origins without paths or credentials")
        if self.rate_limit_writes > self.rate_limit_requests:
            raise ValueError("RATE_LIMIT_WRITES must not exceed RATE_LIMIT_REQUESTS")
        if self.supabase_url:
            parsed = urlsplit(self.supabase_url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
                raise ValueError("SUPABASE_URL must be an HTTPS project origin")
            if self.supabase_jwks_url and self.supabase_jwks_url != self.supabase_url.rstrip("/") + "/auth/v1/.well-known/jwks.json":
                raise ValueError("SUPABASE_JWKS_URL must match the configured project's Auth JWKS endpoint")
        if self.environment == "production":
            if self.database_target != "supabase" or not self.supabase_url or not self.supabase_publishable_key:
                raise ValueError("Production requires Supabase database and Auth URL/publishable key")
            if "allowed_origins" not in self.model_fields_set or not self.allowed_origins or any(urlsplit(o).scheme != "https" or urlsplit(o).hostname in ("localhost", "127.0.0.1", "::1") for o in self.allowed_origins):
                raise ValueError("Production requires explicit HTTPS ALLOWED_ORIGINS")
            if url.query.get("sslmode") not in ("require", "verify-ca", "verify-full"):
                raise ValueError("Production requires SSLMODE=require or certificate verification in SUPABASE_DATABASE_URL")
            if not self.rate_limit_enabled:
                raise ValueError("Production rate limiting must be enabled")
        return self

    @property
    def database_url(self) -> str:
        selected = self.local_database_url if self.database_target == "local" else self.supabase_database_url
        # The validator rejects missing URLs before any engine is constructed.
        assert selected is not None
        return selected


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
