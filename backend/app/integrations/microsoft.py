"""Delegated Graph connector: PKCE, encrypted rotating tokens and narrow email rules."""

import base64
import hashlib
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from urllib.parse import urlencode, urlsplit
from uuid import UUID

import httpx
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ResourceNotFoundError
from app.db.models import Expectation, MonitoringJob
from app.db.models.integration import (
    IntegrationConnection,
    IntegrationCredential,
    ProviderOAuthState,
)
from app.integrations.provider import ProviderError
from app.schemas.evidence import EvidenceCreate
from app.schemas.monitoring import OutlookRule

GRAPH = "https://graph.microsoft.com/v1.0"
SCOPES = ("offline_access", "User.Read", "Mail.ReadBasic")


class MicrosoftOAuth:
    def __init__(
        self, settings: Settings, *, transport: httpx.BaseTransport | None = None
    ):
        self.settings = settings
        self.transport = transport

    def configured(self) -> None:
        if (
            not self.settings.microsoft_graph_enabled
            or not self.settings.integration_token_encryption_key
        ):
            raise ProviderError("PROVIDER_DISABLED", retryable=False)

    def encrypt(self, value: dict, connection_id: UUID) -> str:
        self.configured()
        assert self.settings.integration_token_encryption_key
        key = base64.urlsafe_b64decode(
            self.settings.integration_token_encryption_key.get_secret_value()
        )
        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(key).encrypt(
            nonce, json.dumps(value).encode(), str(connection_id).encode()
        )
        return base64.urlsafe_b64encode(nonce + ciphertext).decode()

    def decrypt(self, value: str, connection_id: UUID) -> dict:
        self.configured()
        assert self.settings.integration_token_encryption_key
        try:
            key = base64.urlsafe_b64decode(
                self.settings.integration_token_encryption_key.get_secret_value()
            )
            payload = base64.urlsafe_b64decode(value)
            parsed = json.loads(
                AESGCM(key).decrypt(
                    payload[:12], payload[12:], str(connection_id).encode()
                )
            )
            if not isinstance(parsed, dict):
                raise TypeError()
            return parsed
        except (ValueError, InvalidTag, TypeError):
            raise ProviderError("CREDENTIAL_UNAVAILABLE", retryable=False) from None

    def request(self, method: str, url: str, **kwargs) -> dict:
        # Only static authority/Graph URLs or independently validated Graph links.
        self.configured()
        parsed = urlsplit(url)
        allowed = (
            method == "POST"
            and parsed.netloc == "login.microsoftonline.com"
            and parsed.path == f"/{self.settings.microsoft_tenant_id}/oauth2/v2.0/token"
            and not parsed.query
        ) or (
            method == "GET"
            and parsed.netloc == "graph.microsoft.com"
            and parsed.path in ("/v1.0/me", "/v1.0/me/mailFolders/inbox/messages")
        )
        if (
            not allowed
            or parsed.scheme != "https"
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise ProviderError("PERMISSION_DENIED", retryable=False)
        try:
            with (
                httpx.Client(
                    transport=self.transport,
                    timeout=httpx.Timeout(10, connect=3, pool=3),
                    follow_redirects=False,
                    trust_env=False,
                ) as client,
                client.stream(method, url, **kwargs) as response,
            ):
                status = response.status_code
                if status in (429, 503):
                    raw = response.headers.get("Retry-After", "0")
                    delay = int(raw) if raw.isdigit() else 0
                    raise ProviderError("PROVIDER_THROTTLED", retry_after=delay)
                if status == 401:
                    raise ProviderError("AUTH_REQUIRED", retryable=False)
                if status == 403:
                    raise ProviderError("PERMISSION_DENIED", retryable=False)
                if status >= 500:
                    raise ProviderError("PROVIDER_UNAVAILABLE")
                if status != 200:
                    raise ProviderError(
                        "OAUTH_REJECTED" if method == "POST" else "PROVIDER_REJECTED",
                        retryable=False,
                    )
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 1_048_576:
                        raise ProviderError("PROVIDER_RESPONSE_INVALID")
                data = json.loads(body)
                if not isinstance(data, dict):
                    raise TypeError()
                return data
        except (httpx.HTTPError, ValueError, TypeError):
            raise ProviderError("PROVIDER_UNAVAILABLE") from None

    def connection(
        self, db: Session, connection_id: UUID, user_id: UUID, *, lock: bool = False
    ) -> IntegrationConnection:
        query = select(IntegrationConnection).where(
            IntegrationConnection.id == connection_id,
            IntegrationConnection.user_id == user_id,
        )
        item = db.scalar(
            (query.with_for_update() if lock else query).execution_options(
                populate_existing=True
            )
        )
        if item is None:
            raise ResourceNotFoundError(
                "INTEGRATION_NOT_FOUND", "Integration not found"
            )
        if item.provider != "microsoft" or item.connection_type != "email":
            raise ProviderError("PERMISSION_DENIED", retryable=False)
        return item

    def begin(
        self,
        db: Session,
        connection_id: UUID,
        user_id: UUID,
        *,
        now: datetime | None = None,
    ) -> str:
        self.configured()
        current = now or datetime.now(timezone.utc)
        connection = self.connection(db, connection_id, user_id, lock=True)
        state = secrets.token_urlsafe(32)
        connection.oauth_generation = hashlib.sha256(state.encode()).hexdigest()
        verifier = secrets.token_urlsafe(48)
        db.execute(
            delete(ProviderOAuthState).where(
                ProviderOAuthState.user_id == user_id,
                (ProviderOAuthState.connection_id == connection_id)
                | (ProviderOAuthState.expires_at <= current),
            )
        )
        db.add(
            ProviderOAuthState(
                state_digest=hashlib.sha256(state.encode()).hexdigest(),
                connection_id=connection_id,
                user_id=user_id,
                encrypted_verifier=self.encrypt({"verifier": verifier}, connection_id),
                expires_at=current + timedelta(minutes=10),
            )
        )
        db.commit()
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        return (
            f"https://login.microsoftonline.com/{self.settings.microsoft_tenant_id}/oauth2/v2.0/authorize?"
            + urlencode(
                {
                    "client_id": str(self.settings.microsoft_client_id),
                    "response_type": "code",
                    "redirect_uri": self.settings.microsoft_redirect_uri,
                    "scope": " ".join(SCOPES),
                    "state": state,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                    "response_mode": "form_post",
                }
            )
        )

    def grant(self, data: dict, *, previous_refresh: str | None = None) -> dict:
        assert self.settings.microsoft_client_secret
        response = self.request(
            "POST",
            f"https://login.microsoftonline.com/{self.settings.microsoft_tenant_id}/oauth2/v2.0/token",
            data={
                **data,
                "client_id": str(self.settings.microsoft_client_id),
                "client_secret": self.settings.microsoft_client_secret.get_secret_value(),
                "scope": " ".join(SCOPES),
            },
        )
        access = response.get("access_token")
        refresh = response.get("refresh_token") or previous_refresh
        expires = response.get("expires_in")
        granted = response.get("scope")
        if not isinstance(granted, str):
            raise ProviderError("PERMISSION_DENIED", retryable=False)
        scopes = {
            part.removeprefix("https://graph.microsoft.com/").lower()
            for part in granted.split()
        }
        if not {"mail.readbasic", "user.read"} <= scopes or not scopes <= {
            s.lower() for s in SCOPES
        }:
            raise ProviderError("PERMISSION_DENIED", retryable=False)
        if (
            not isinstance(access, str)
            or not access
            or len(access) > 24000
            or not isinstance(refresh, str)
            or not refresh
            or len(refresh) > 24000
            or type(expires) is not int
            or not 60 <= expires <= 86400
            or not isinstance(response.get("token_type"), str)
            or response["token_type"].lower() != "bearer"
        ):
            raise ProviderError("PROVIDER_RESPONSE_INVALID", retryable=False)
        return {"access_token": access, "refresh_token": refresh, "expires_in": expires}

    def complete(
        self,
        db: Session,
        connection_id: UUID,
        user_id: UUID,
        state: str,
        code: str,
        *,
        now: datetime | None = None,
    ) -> IntegrationConnection:
        self.configured()
        current = now or datetime.now(timezone.utc)
        connection = self.connection(db, connection_id, user_id, lock=True)
        pending = db.scalar(
            select(ProviderOAuthState)
            .where(
                ProviderOAuthState.state_digest
                == hashlib.sha256(state.encode()).hexdigest(),
                ProviderOAuthState.connection_id == connection_id,
                ProviderOAuthState.user_id == user_id,
            )
            .with_for_update()
        )
        if (
            pending is None
            or pending.expires_at <= current
            or connection.oauth_generation != pending.state_digest
        ):
            raise ProviderError("OAUTH_STATE_INVALID", retryable=False)
        verifier = self.decrypt(pending.encrypted_verifier, connection_id).get(
            "verifier"
        )
        # Consume before exchanging; retries require a new flow, not replayed codes.
        db.delete(pending)
        db.commit()
        try:
            tokens = self.grant(
                {
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": self.settings.microsoft_redirect_uri,
                    "code_verifier": verifier,
                }
            )
            identity = self.request(
                "GET",
                GRAPH + "/me?$select=id",
                headers={"Authorization": "Bearer " + tokens["access_token"]},
            )
            account = identity.get("id")
            if not isinstance(account, str) or not account or len(account) > 255:
                raise ProviderError("PROVIDER_RESPONSE_INVALID", retryable=False)
            # Re-lock after exchange: disconnect/delete during I/O cannot be lost.
            connection = self.connection(db, connection_id, user_id, lock=True)
            if (
                connection.oauth_generation
                != hashlib.sha256(state.encode()).hexdigest()
            ):
                raise ProviderError("OAUTH_STATE_INVALID", retryable=False)
            stored = db.get(IntegrationCredential, connection_id)
            if stored is None:
                stored = IntegrationCredential(
                    connection_id=connection_id, user_id=user_id
                )
                db.add(stored)
            stored.encrypted_tokens = self.encrypt(tokens, connection_id)
            stored.expires_at = current + timedelta(seconds=tokens["expires_in"])
            connection.external_account_id = account
            connection.status = "connected"
            connection.scopes = list(SCOPES)
            connection.connected_at, connection.revoked_at, connection.failure_status = current, None, None
            connection.__dict__["_credential_state"] = "configured"
            db.commit()
            return connection
        except Exception:
            db.rollback()
            raise

    def access_token(
        self, db: Session, connection_id: UUID, user_id: UUID, now: datetime
    ) -> str:
        self.configured()
        connection = self.connection(db, connection_id, user_id, lock=True)
        if (
            connection.status != "connected"
            or "Mail.ReadBasic" not in connection.scopes
            or not connection.external_account_id
        ):
            raise ProviderError("AUTH_REQUIRED", retryable=False)
        stored = db.scalar(
            select(IntegrationCredential)
            .where(
                IntegrationCredential.connection_id == connection_id,
                IntegrationCredential.user_id == user_id,
            )
            .with_for_update()
        )
        if stored is None:
            raise ProviderError("AUTH_REQUIRED", retryable=False)
        tokens = self.decrypt(stored.encrypted_tokens, connection_id)
        if any(
            not isinstance(tokens.get(field), str) or not tokens[field]
            for field in ("access_token", "refresh_token")
        ):
            raise ProviderError("CREDENTIAL_UNAVAILABLE", retryable=False)
        if stored.expires_at <= now + timedelta(seconds=60):
            try:
                refreshed = self.grant(
                    {
                        "grant_type": "refresh_token",
                        "refresh_token": tokens["refresh_token"],
                    },
                    previous_refresh=tokens["refresh_token"],
                )
            except ProviderError as error:
                if not error.retryable:
                    db.delete(stored)
                    connection.status = "error"
                    connection.failure_status = error.code
                    db.commit()
                raise
            stored.encrypted_tokens = self.encrypt(refreshed, connection_id)
            stored.expires_at = now + timedelta(seconds=refreshed["expires_in"])
            tokens = refreshed
        db.commit()  # Serialized refresh rotation is durable before any mailbox read.
        access = tokens.get("access_token")
        if not isinstance(access, str):
            raise ProviderError("CREDENTIAL_UNAVAILABLE", retryable=False)
        return access

    def disconnect(self, db: Session, connection_id: UUID, user_id: UUID) -> None:
        connection = self.connection(db, connection_id, user_id, lock=True)
        db.execute(
            delete(IntegrationCredential).where(
                IntegrationCredential.connection_id == connection_id,
                IntegrationCredential.user_id == user_id,
            )
        )
        db.execute(
            delete(ProviderOAuthState).where(
                ProviderOAuthState.connection_id == connection_id,
                ProviderOAuthState.user_id == user_id,
            )
        )
        from app.db.models.provider_sync import ProviderSyncState
        db.execute(delete(ProviderSyncState).where(ProviderSyncState.connection_id == connection_id, ProviderSyncState.user_id == user_id))
        connection.status = "disconnected"
        connection.revoked_at = datetime.now(timezone.utc)
        connection.failure_status = None
        connection.oauth_generation = None
        connection.scopes = []
        connection.__dict__["_credential_state"] = "not_configured"
        db.commit()


class OutlookProvider:
    """Exact sender + deterministic subject totals; never parse bodies or attachments."""

    def __init__(
        self, settings: Settings, *, transport: httpx.BaseTransport | None = None
    ):
        self.oauth = MicrosoftOAuth(settings, transport=transport)

    def fetch(
        self, db: Session, job: MonitoringJob, expectation: Expectation, now: datetime
    ) -> list[EvidenceCreate]:
        assert job.connection_id is not None
        if job.user_id != expectation.user_id or job.expectation_id != expectation.id:
            raise ProviderError("PERMISSION_DENIED", retryable=False)
        rule = OutlookRule.model_validate(job.provider_config)
        token = self.oauth.access_token(db, job.connection_id, job.user_id, now)
        connection = self.oauth.connection(db, job.connection_id, job.user_id)
        identity = self.oauth.request(
            "GET",
            GRAPH + "/me?$select=id",
            headers={"Authorization": "Bearer " + token},
        )
        if identity.get("id") != connection.external_account_id:
            raise ProviderError("PERMISSION_DENIED", retryable=False)
        start = max(
            expectation.created_at,
            job.window_start_at or expectation.created_at,
            now - timedelta(seconds=job.max_evidence_age_seconds),
        )
        path = GRAPH + "/me/mailFolders/inbox/messages"
        url = (
            path
            + "?"
            + urlencode(
                {
                    "$select": "id,subject,from,sender,receivedDateTime",
                    "$top": "100",
                    "$filter": f"receivedDateTime ge {start.isoformat()} and receivedDateTime le {now.isoformat()}",
                    "$orderby": "receivedDateTime desc",
                }
            )
        )
        matched = []
        pattern = re.compile(
            r"^"
            + re.escape(rule.subject_prefix)
            + r": "
            + rule.currency
            + r" ([0-9]{1,9}(?:\.[0-9]{2})?)$"
        )
        for _ in range(5):
            parsed = urlsplit(url)
            if (
                parsed.scheme != "https"
                or parsed.netloc != "graph.microsoft.com"
                or parsed.path != urlsplit(path).path
                or parsed.username
                or parsed.password
                or parsed.fragment
            ):
                raise ProviderError("PROVIDER_RESPONSE_INVALID", retryable=False)
            data = self.oauth.request(
                "GET",
                url,
                headers={
                    "Authorization": "Bearer " + token,
                    "Prefer": 'IdType="ImmutableId"',
                },
            )
            rows = data.get("value")
            if not isinstance(rows, list) or len(rows) > 100:
                raise ProviderError("PROVIDER_RESPONSE_INVALID")
            for row in rows:
                if not isinstance(row, dict):
                    raise ProviderError("PROVIDER_RESPONSE_INVALID")
                try:
                    sender = row["sender"]["emailAddress"]["address"]
                    origin = row["from"]["emailAddress"]["address"]
                    if not isinstance(sender, str) or not isinstance(origin, str):
                        continue
                    if (
                        sender.lower() != rule.sender.lower()
                        or origin.lower() != rule.sender.lower()
                    ):
                        continue
                    subject = row.get("subject")
                    match = (
                        pattern.fullmatch(subject)
                        if isinstance(subject, str) and len(subject) <= 256
                        else None
                    )
                    if match is None:
                        continue
                    observed = datetime.fromisoformat(
                        row["receivedDateTime"].replace("Z", "+00:00")
                    )
                    external = row["id"]
                    if (
                        not isinstance(external, str)
                        or not external
                        or len(external) > 4096
                    ):
                        continue
                    if observed.tzinfo is None or not start <= observed <= now:
                        continue
                except (KeyError, TypeError, ValueError, AttributeError):
                    continue  # Malformed/unmatched mail never establishes a fact.
                event_id = hashlib.sha256(
                    (str(job.connection_id) + ":" + external).encode()
                ).hexdigest()
                matched.append(
                    EvidenceCreate(
                        source="outlook_email",
                        metric=expectation.metric,
                        value={"amount": float(Decimal(match.group(1)))},
                        unit=rule.currency,
                        observed_at=observed,
                        confidence=0.9,
                        external_event_id=event_id,
                        raw_data={
                            "provider": "microsoft_graph",
                            "connection_id": str(job.connection_id),
                            "account_id": connection.external_account_id,
                            "event_id": event_id,
                            "permission": "Mail.ReadBasic",
                            "access": "delegated_own_mailbox",
                            "parser": "subject_total_v1",
                            "sender_rule_matched": True,
                            "received_at": observed.isoformat(),
                            "sender_authenticated": False,
                        },
                    )
                )
            next_url = data.get("@odata.nextLink")
            if not next_url:
                return matched
            if not isinstance(next_url, str):
                raise ProviderError("PROVIDER_RESPONSE_INVALID")
            url = next_url
        # Never evaluate a partial page set or pretend that truncated mail is complete.
        raise ProviderError("INCOMPLETE_SYNC")
