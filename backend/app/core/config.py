"""Environment-backed settings with one explicit database target."""

from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


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
    amazon_auth_enabled: bool = False
    amazon_client_id: str | None = Field(default=None, min_length=1, max_length=100)

    bedrock_enabled: bool = False
    aws_region: str = Field(default="us-east-2", min_length=1)
    bedrock_model_id: str = Field(default="openai.gpt-oss-120b-1:0", min_length=1)
    bedrock_max_tokens: int = Field(default=1000, ge=1, le=65536)
    bedrock_temperature: float = Field(default=0.1, ge=0, le=1)
    bedrock_request_timeout_seconds: int = Field(default=30, gt=0, le=120)
    bedrock_max_retries: int = Field(default=2, ge=0, le=5)
    bedrock_native_structured_output: bool = False
    bedrock_operation_timeout_seconds: int = Field(default=45, ge=1, le=120)
    bedrock_compiler_model_id: str | None = Field(default=None, min_length=1, max_length=256)
    bedrock_investigator_model_id: str | None = Field(default=None, min_length=1, max_length=256)
    bedrock_max_concurrent_calls: int = Field(default=4, ge=1, le=32)
    bedrock_max_total_tokens: int = Field(default=8192, ge=1, le=131072)
    max_request_bytes: int = Field(default=131072, ge=32768, le=1048576)
    agent_execution_timeout_seconds: int = Field(default=45, ge=1, le=120)
    conversation_store_backend: Literal['memory', 'postgres'] = 'memory'
    conversation_encryption_key: SecretStr | None = Field(default=None, repr=False)
    oauth_allowed_client_ids: list[str] = Field(default_factory=list, max_length=20)
    alexa_oauth_client_id: str | None = Field(default=None, pattern=r'^[A-Za-z0-9_-]{1,128}$')
    alexa_require_confirmation: bool = False
    operations_metrics_token: SecretStr | None = Field(default=None, repr=False, min_length=43)
    investigator_max_evidence: int = Field(default=6, ge=1, le=12)
    investigator_max_prompt_bytes: int = Field(default=12000, ge=2048, le=64000)
    counton_clarification_signing_key: SecretStr | None = Field(default=None, repr=False)
    clarification_max_turns: int = Field(default=6, ge=1, le=12)
    clarification_ttl_seconds: int = Field(default=900, ge=60, le=3600)
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
    mcp_host: str = "127.0.0.1"
    mcp_port: int = Field(default=8003, ge=1, le=65535)
    mcp_public_url: str | None = None
    mcp_allowed_origins: list[str] = Field(default_factory=list)
    alexa_skill_id: str | None = Field(default=None, pattern=r"^amzn1\.ask\.skill\.[A-Za-z0-9-]+$")
    counton_demo_user_id: UUID | None = None
    counton_demo_email: str = "demo@counton.app"
    counton_demo_password: SecretStr | None = Field(default=None, repr=False)
    monitoring_enabled: bool = False
    notification_email_provider: Literal["resend", "smtp"] = "resend"
    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = Field(default=None, repr=False)
    smtp_password: SecretStr | None = Field(default=None, repr=False)
    smtp_from_email: str | None = Field(default=None, pattern=r'^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$', max_length=254)
    smtp_use_tls: bool = True
    notification_email_enabled: bool = False
    notification_email_api_key: SecretStr | None = Field(default=None, repr=False)
    notification_email_from: str | None = Field(default=None, pattern=r'^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$', max_length=254)
    frontend_public_url: str | None = None
    monitoring_poll_seconds: int = Field(default=5, ge=1, le=300)
    monitoring_lease_seconds: int = Field(default=300, ge=120, le=3600)
    monitoring_backoff_seconds: int = Field(default=30, ge=1, le=3600)
    microsoft_graph_enabled: bool = False
    google_integrations_enabled: bool = False
    google_client_id: str | None = Field(default=None, max_length=255)
    google_client_secret: SecretStr | None = Field(default=None, repr=False)
    google_redirect_uri: str | None = None
    provider_sync_enabled: bool = False
    provider_sync_interval_seconds: int = Field(default=900, ge=60, le=86400)
    provider_retention_days: int = Field(default=30, ge=1, le=90)
    provider_webhook_url: str | None = None
    gmail_pubsub_topic: str | None = Field(default=None, pattern=r'^projects/[a-z0-9-]+/topics/[A-Za-z0-9._~-]+$')
    gmail_pubsub_audience: str | None = None
    gmail_pubsub_service_account: str | None = Field(default=None, pattern=r'^[A-Za-z0-9._-]+@[A-Za-z0-9.-]+\.gserviceaccount\.com$')
    microsoft_client_id: UUID | None = None
    microsoft_client_secret: SecretStr | None = Field(default=None, repr=False)
    microsoft_tenant_id: str = Field(default='common', pattern=r'^(common|organizations|consumers|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$')
    microsoft_redirect_uri: str | None = None
    integration_token_encryption_key: SecretStr | None = Field(default=None, repr=False)

    @field_validator('microsoft_client_secret', 'google_client_secret', 'integration_token_encryption_key', mode='before')
    @classmethod
    def empty_provider_secret(cls, value: object) -> object:
        return None if value == '' else value

    @model_validator(mode='after')
    def validate_provider_settings(self) -> 'Settings':
        import base64
        if self.frontend_public_url:
            url = urlsplit(self.frontend_public_url)
            if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment or url.path not in ('', '/'):
                raise ValueError('FRONTEND_PUBLIC_URL must be a credential-free HTTPS origin')
        if self.notification_email_enabled and self.notification_email_provider == "smtp":
            self.notification_email_from = self.notification_email_from or self.smtp_from_email
            if not all((self.smtp_host, self.smtp_username, self.smtp_password, self.smtp_use_tls)):
                raise ValueError("SMTP delivery requires host, credentials and TLS")
        credentials_ready = self.notification_email_provider == "smtp" or self.notification_email_api_key
        if self.notification_email_enabled and not all((credentials_ready, self.notification_email_from, self.frontend_public_url, self.integration_token_encryption_key)):
            raise ValueError('Email delivery requires its API key, verified sender, frontend origin and encryption key')
        if self.integration_token_encryption_key:
            try:
                key = base64.b64decode(self.integration_token_encryption_key.get_secret_value(), altchars=b'-_', validate=True)
                if len(key) != 32:
                    raise ValueError()
            except ValueError:
                raise ValueError('INTEGRATION_TOKEN_ENCRYPTION_KEY must encode exactly 32 random bytes') from None
        for callback_uri in (self.microsoft_redirect_uri, self.google_redirect_uri, self.provider_webhook_url, self.gmail_pubsub_audience):
            if not callback_uri:
                continue
            uri = urlsplit(callback_uri)
            local = uri.hostname in ('localhost', '127.0.0.1', '::1')
            if (not uri.hostname or uri.username or uri.password or uri.query or uri.fragment
                or any(c.isspace() for c in callback_uri)
                or not (uri.scheme == 'https' or (local and self.environment != 'production' and uri.scheme == 'http'))):
                raise ValueError('MICROSOFT_REDIRECT_URI requires a credential-free HTTPS callback, or development loopback HTTP')
            try:
                if uri.port == 0: raise ValueError()
            except ValueError:
                raise ValueError('MICROSOFT_REDIRECT_URI has an invalid port') from None
        if self.microsoft_graph_enabled and not all((self.microsoft_client_id, self.microsoft_client_secret,
                                                    self.microsoft_redirect_uri, self.integration_token_encryption_key)):
            raise ValueError('Microsoft Graph requires client, redirect and encryption configuration')
        if self.google_integrations_enabled and not all((self.google_client_id, self.google_client_secret, self.google_redirect_uri, self.integration_token_encryption_key)):
            raise ValueError('Google integrations require client, redirect and encryption configuration')
        if any((self.gmail_pubsub_topic, self.gmail_pubsub_audience, self.gmail_pubsub_service_account)) and not all((self.gmail_pubsub_topic, self.gmail_pubsub_audience, self.gmail_pubsub_service_account, self.provider_webhook_url)):
            raise ValueError('Gmail push requires topic, audience, service account and webhook configuration')
        return self

    @field_validator("counton_demo_user_id", mode="before")
    @classmethod
    def empty_demo_uuid(cls, value: object) -> object:
        return None if value == "" else value

    @model_validator(mode="after")
    def validate_selected_database(self) -> "Settings":
        selected = self.local_database_url if self.database_target == "local" else self.supabase_database_url
        name = f"{self.database_target.upper()}_DATABASE_URL"
        if not selected:
            raise ValueError(f"{name} is required for DATABASE_TARGET={self.database_target}")
        try:
            url = make_url(selected)
        except (ArgumentError, ValueError):
            raise ValueError(f"{name} is not a valid PostgreSQL URL") from None
        if url.drivername != "postgresql+psycopg" or not url.host or not url.database:
            raise ValueError(f"{name} must use postgresql+psycopg:// with a host and database")
        for origin in self.allowed_origins:
            parsed = urlsplit(origin)
            try:
                port = parsed.port
            except ValueError:
                raise ValueError("ALLOWED_ORIGINS contains an invalid port") from None
            if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.path
                    or parsed.query or parsed.fragment or parsed.username or parsed.password
                    or port == 0 or "*" in parsed.netloc or any(char.isspace() for char in origin)
                    or "?" in origin or "#" in origin):
                raise ValueError("ALLOWED_ORIGINS must contain explicit HTTP(S) origins without paths or credentials")
            self.validate_mcp_host(parsed.hostname)
        if self.rate_limit_writes > self.rate_limit_requests:
            raise ValueError("RATE_LIMIT_WRITES must not exceed RATE_LIMIT_REQUESTS")
        if self.supabase_url:
            parsed = urlsplit(self.supabase_url)
            try:
                port = parsed.port
            except ValueError:
                raise ValueError("SUPABASE_URL contains an invalid port") from None
            if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.path not in ("", "/")
                or port == 0 or "*" in parsed.netloc or any(char.isspace() for char in self.supabase_url)
                or "?" in self.supabase_url or "#" in self.supabase_url):
                raise ValueError("SUPABASE_URL must be an HTTPS project origin")
            self.validate_mcp_host(parsed.hostname)
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

    @field_validator("mcp_host")
    @classmethod
    def validate_mcp_host(cls, value: str) -> str:
        import ipaddress
        import re
        try:
            ipaddress.ip_address(value)
        except ValueError:
            if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]*[A-Za-z0-9])?", value):
                raise ValueError("MCP_HOST must be a bind IP address or hostname")
        return value

    @model_validator(mode="after")
    def validate_mcp_configuration(self) -> "Settings":
        if self.conversation_encryption_key:
            import base64
            try:
                if len(base64.b64decode(self.conversation_encryption_key.get_secret_value(), altchars=b'-_', validate=True)) != 32:
                    raise ValueError()
            except ValueError:
                raise ValueError('CONVERSATION_ENCRYPTION_KEY must encode 32 random bytes') from None
        if self.conversation_store_backend == 'postgres' and not self.conversation_encryption_key:
            raise ValueError('PostgreSQL conversation storage requires CONVERSATION_ENCRYPTION_KEY')
        import re
        if any(not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', client) for client in self.oauth_allowed_client_ids):
            raise ValueError('OAuth client IDs must be explicit identifiers')
        if self.alexa_oauth_client_id and self.alexa_oauth_client_id not in self.oauth_allowed_client_ids:
            raise ValueError('ALEXA_OAUTH_CLIENT_ID must be in OAUTH_ALLOWED_CLIENT_IDS')
        if self.environment == 'production' and self.alexa_skill_id and (
            not self.alexa_oauth_client_id or self.conversation_store_backend != 'postgres'
            or not self.alexa_require_confirmation or not self.mcp_public_url
        ):
            raise ValueError('Production Alexa requires linked client, durable conversations, confirmation and MCP_PUBLIC_URL')
        if self.mcp_public_url:
            url = urlsplit(self.mcp_public_url)
            try:
                port = url.port
            except ValueError:
                raise ValueError("MCP_PUBLIC_URL has an invalid port") from None
            if (not url.hostname or url.username or url.password or url.query or url.fragment
                    or url.path != "/mcp" or url.scheme not in ("http", "https")
                    or port == 0 or "*" in url.netloc):
                raise ValueError("MCP_PUBLIC_URL must be a credential-free canonical HTTP(S) URL ending in /mcp")
            self.validate_mcp_host(url.hostname)
            if any(char.isspace() for char in self.mcp_public_url) or '?' in self.mcp_public_url or '#' in self.mcp_public_url:
                raise ValueError("MCP_PUBLIC_URL must be canonical without whitespace, query or fragment")
            local = url.hostname in ("localhost", "127.0.0.1", "::1")
            if url.scheme != "https" and not local:
                raise ValueError("Remote MCP_PUBLIC_URL requires HTTPS")
            if self.environment == "production" and (url.scheme != "https" or local):
                raise ValueError("Production MCP_PUBLIC_URL requires a remote HTTPS host")
        for value in self.mcp_allowed_origins:
            origin = urlsplit(value)
            try:
                port = origin.port
            except ValueError:
                raise ValueError("MCP_ALLOWED_ORIGINS contains an invalid port") from None
            if (origin.scheme not in ("http", "https") or not origin.hostname or origin.path
                    or origin.username or origin.password or origin.query or origin.fragment
                    or "*" in origin.netloc or port == 0):
                raise ValueError("MCP_ALLOWED_ORIGINS must contain explicit HTTP(S) origins")
            self.validate_mcp_host(origin.hostname)
            if any(char.isspace() for char in value) or '?' in value or '#' in value:
                raise ValueError("MCP_ALLOWED_ORIGINS must contain canonical origins")
            if self.environment == "production" and (origin.scheme != "https" or origin.hostname in ("localhost", "127.0.0.1", "::1")):
                raise ValueError("Production MCP_ALLOWED_ORIGINS requires remote HTTPS origins")
        if self.environment == 'production' and self.conversation_store_backend != 'postgres':
            raise ValueError('Production requires PostgreSQL conversation storage')
        return self

    @property
    def database_url(self) -> str:
        selected = self.local_database_url if self.database_target == "local" else self.supabase_database_url
        # The validator rejects missing URLs before any engine is constructed.
        assert selected is not None
        return selected


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]  # Required selector is read by BaseSettings from env.


settings = get_settings()
