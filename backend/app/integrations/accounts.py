"""Official delegated account OAuth; reuses existing AES-GCM/token/state tables."""

import base64
import hashlib
import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlencode, urlsplit
from uuid import UUID

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import ResourceNotFoundError
from app.db.models.integration import (
    IntegrationConnection,
    IntegrationCredential,
    ProviderOAuthState,
)
from app.integrations.microsoft import MicrosoftOAuth
from app.integrations.provider import ProviderError

GMAIL_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"


class ProviderHTTP:
    """Fixed provider authorities, bounded bodies/timeouts, no redirects/proxy secrets."""

    def __init__(self, transport=None):
        self.transport = transport

    def request(self, method: str, url: str, **kwargs) -> dict:
        parsed = urlsplit(url)
        path = parsed.path
        allowed = (
            parsed.netloc == "oauth2.googleapis.com"
            and method == "POST"
            and path in ("/token", "/revoke")
            or parsed.netloc == "openidconnect.googleapis.com"
            and method == "GET"
            and path == "/v1/userinfo"
            or parsed.netloc == "login.microsoftonline.com"
            and method == "POST"
            and re.fullmatch(
                r"/(?:common|organizations|consumers|[0-9a-fA-F-]{36})/oauth2/v2.0/token",
                path,
            )
            or parsed.netloc == "gmail.googleapis.com"
            and (
                method == "GET"
                and re.fullmatch(
                    r"/gmail/v1/users/me/(?:profile|history|messages(?:/[A-Za-z0-9_-]+)?)",
                    path,
                )
                or method == "POST"
                and path in ("/gmail/v1/users/me/watch", "/gmail/v1/users/me/stop")
            )
            or parsed.netloc == "www.googleapis.com"
            and (
                method == "GET"
                and re.fullmatch(
                    r"/calendar/v3/(?:users/me/calendarList|calendars/[^/]+/events)",
                    path,
                )
                or method == "POST"
                and (
                    re.fullmatch(r"/calendar/v3/calendars/[^/]+/events/watch", path)
                    or path == "/calendar/v3/channels/stop"
                )
            )
            or parsed.netloc == "graph.microsoft.com"
            and (
                method == "GET"
                and re.fullmatch(
                    r"/v1.0/me(?:/calendar|/calendarView/delta|/calendars|/mailFolders/inbox/messages(?:/delta|/[^/]+(?:/attachments)?)?|/calendars/[^/]+/calendarView)?",
                    path,
                )
                or method == "POST"
                and path == "/v1.0/subscriptions"
                or method in ("PATCH", "DELETE")
                and re.fullmatch(r"/v1.0/subscriptions/[A-Za-z0-9-]+", path)
            )
        )
        if (
            not allowed
            or parsed.scheme != "https"
            or parsed.username
            or parsed.password
            or parsed.fragment
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
                raw = bytearray()
                for chunk in response.iter_bytes():
                    raw.extend(chunk)
                    if len(raw) > 2_097_152:
                        raise ProviderError(
                            "PROVIDER_RESPONSE_INVALID", retryable=False
                        )
                if response.status_code in (429, 503):
                    value = response.headers.get("Retry-After", "0")
                    try:
                        delay = (
                            int(value)
                            if value.isdigit()
                            else int(
                                (
                                    parsedate_to_datetime(value)
                                    - datetime.now(timezone.utc)
                                ).total_seconds()
                            )
                        )
                    except (ValueError, TypeError, OverflowError):
                        delay = 0
                    raise ProviderError("PROVIDER_THROTTLED", retry_after=delay)
                if response.status_code == 401:
                    raise ProviderError("AUTH_REQUIRED", retryable=False)
                if response.status_code == 403:
                    raise ProviderError("PERMISSION_DENIED", retryable=False)
                if (
                    response.status_code == 410
                    or response.status_code == 404
                    and path.endswith(("/history", "/delta"))
                ):
                    raise ProviderError("SYNC_CURSOR_EXPIRED")
                if response.status_code == 404:
                    raise ProviderError("SOURCE_NOT_FOUND", retryable=False)
                if response.status_code >= 500:
                    raise ProviderError("PROVIDER_UNAVAILABLE")
                if response.status_code not in (200, 201, 202, 204):
                    if path.endswith("/token") and raw:
                        try:
                            if json.loads(raw).get("error") == "invalid_grant":
                                raise ProviderError("AUTH_REQUIRED", retryable=False)
                        except (ValueError, AttributeError):
                            pass
                    raise ProviderError("PROVIDER_REJECTED", retryable=False)
                data = json.loads(raw) if raw else {}
                if not isinstance(data, dict):
                    raise TypeError()
                return data
        except (httpx.HTTPError, ValueError, TypeError):
            raise ProviderError("PROVIDER_UNAVAILABLE") from None


class AccountOAuth(MicrosoftOAuth):
    """Extends the existing credential lifecycle, not Supabase user authentication."""

    def __init__(self, settings: Settings, provider: str, kind: str, *, transport=None):
        super().__init__(settings, transport=transport)
        if provider not in ("google", "microsoft") or kind not in ("email", "calendar"):
            raise ProviderError("PERMISSION_DENIED", retryable=False)
        self.provider, self.kind = provider, kind
        self.http = ProviderHTTP(transport)

    @property
    def scopes(self) -> tuple[str, ...]:
        if self.provider == "google":
            return (
                (GMAIL_SCOPE,) if self.kind == "email" else ("openid", CALENDAR_SCOPE)
            )
        return (
            "offline_access",
            "User.Read",
            "Mail.Read" if self.kind == "email" else "Calendars.Read",
        )

    @property
    def redirect(self) -> str:
        return str(
            self.settings.google_redirect_uri
            if self.provider == "google"
            else self.settings.microsoft_redirect_uri
        )

    def configured(self):
        enabled = (
            self.settings.google_integrations_enabled
            if self.provider == "google"
            else self.settings.microsoft_graph_enabled
        )
        if not enabled or not self.settings.integration_token_encryption_key:
            raise ProviderError("PROVIDER_DISABLED", retryable=False)

    def connection(self, db, connection_id, user_id, *, lock=False):
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
        if (item.provider, item.connection_type) != (self.provider, self.kind):
            raise ProviderError("PERMISSION_DENIED", retryable=False)
        return item

    def begin(
        self, db: Session, connection_id: UUID, user_id: UUID, *, now=None
    ) -> str:
        self.configured()
        now = now or datetime.now(timezone.utc)
        item = self.connection(db, connection_id, user_id, lock=True)
        state, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(48)
        digest = hashlib.sha256(state.encode()).hexdigest()
        item.oauth_generation = digest
        db.execute(
            delete(ProviderOAuthState).where(
                ProviderOAuthState.connection_id == item.id
            )
        )
        db.add(
            ProviderOAuthState(
                state_digest=digest,
                connection_id=item.id,
                user_id=user_id,
                encrypted_verifier=self.encrypt(
                    {"verifier": verifier, "connector": "accounts"}, item.id
                ),
                expires_at=now + timedelta(minutes=10),
            )
        )
        db.commit()
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .decode()
            .rstrip("=")
        )
        parameters = {
            "client_id": str(
                self.settings.google_client_id
                if self.provider == "google"
                else self.settings.microsoft_client_id
            ),
            "response_type": "code",
            "redirect_uri": self.redirect,
            "scope": " ".join(self.scopes),
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        if self.provider == "google":
            parameters.update(
                access_type="offline", prompt="consent", include_granted_scopes="false"
            )
            authority = "https://accounts.google.com/o/oauth2/v2/auth"
        else:
            parameters["response_mode"] = "form_post"
            authority = f"https://login.microsoftonline.com/{self.settings.microsoft_tenant_id}/oauth2/v2.0/authorize"
        return authority + "?" + urlencode(parameters)

    def grant(self, data: dict, *, previous_refresh=None) -> dict:
        self.configured()
        if self.provider == "google":
            url = "https://oauth2.googleapis.com/token"
            client_id, secret = (
                self.settings.google_client_id,
                self.settings.google_client_secret,
            )
        else:
            url = f"https://login.microsoftonline.com/{self.settings.microsoft_tenant_id}/oauth2/v2.0/token"
            client_id, secret = (
                str(self.settings.microsoft_client_id),
                self.settings.microsoft_client_secret,
            )
        if secret is None:
            raise ProviderError("PROVIDER_DISABLED", retryable=False)
        response = self.http.request(
            "POST",
            url,
            data={
                **data,
                "client_id": str(client_id),
                "client_secret": secret.get_secret_value(),
            },
        )
        scope = response.get("scope")
        granted = (
            set(scope.split())
            if isinstance(scope, str)
            else (
                set(self.scopes) if data.get("grant_type") == "refresh_token" else set()
            )
        )
        normalized = {
            s.removeprefix("https://graph.microsoft.com/").lower()
            if self.provider == "microsoft"
            else s
            for s in granted
        }
        requested = {
            s.lower() if self.provider == "microsoft" else s for s in self.scopes
        }
        required = requested - {"offline_access"}
        if not required <= normalized or not normalized <= requested:
            raise ProviderError("PERMISSION_DENIED", retryable=False)
        access, refresh = (
            response.get("access_token"),
            response.get("refresh_token") or previous_refresh,
        )
        expires = response.get("expires_in")
        if (
            not isinstance(access, str)
            or not access
            or len(access) > 24000
            or not isinstance(refresh, str)
            or not refresh
            or len(refresh) > 24000
            or type(expires) is not int
            or not 60 <= expires <= 86400
            or str(response.get("token_type", "")).lower() != "bearer"
        ):
            raise ProviderError("PROVIDER_RESPONSE_INVALID", retryable=False)
        return {
            "access_token": access,
            "refresh_token": refresh,
            "expires_in": expires,
            "scopes": sorted(granted),
            "provider": self.provider,
            "kind": self.kind,
        }

    def identity(self, token: str) -> str:
        url, key = (
            ("https://graph.microsoft.com/v1.0/me?$select=id", "id")
            if self.provider == "microsoft"
            else (
                (
                    "https://gmail.googleapis.com/gmail/v1/users/me/profile",
                    "emailAddress",
                )
                if self.kind == "email"
                else ("https://openidconnect.googleapis.com/v1/userinfo", "sub")
            )
        )
        identity = self.http.request(
            "GET", url, headers={"Authorization": "Bearer " + token}
        ).get(key)
        if not isinstance(identity, str) or not 1 <= len(identity) <= 255:
            raise ProviderError("PROVIDER_RESPONSE_INVALID", retryable=False)
        return identity

    def complete(self, db, connection_id, user_id, state, code, *, now=None):
        self.configured()
        now = now or datetime.now(timezone.utc)
        item = self.connection(db, connection_id, user_id, lock=True)
        digest = hashlib.sha256(state.encode()).hexdigest()
        pending = db.scalar(
            select(ProviderOAuthState)
            .where(
                ProviderOAuthState.state_digest == digest,
                ProviderOAuthState.connection_id == item.id,
                ProviderOAuthState.user_id == user_id,
            )
            .with_for_update()
        )
        if (
            pending is None
            or pending.expires_at <= now
            or item.oauth_generation != digest
        ):
            raise ProviderError("OAUTH_STATE_INVALID", retryable=False)
        state_data = self.decrypt(pending.encrypted_verifier, item.id)
        if state_data.get("connector") != "accounts":
            raise ProviderError("OAUTH_STATE_INVALID", retryable=False)
        db.delete(pending)
        db.commit()  # consume before token I/O; code retries must start fresh
        tokens = self.grant(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect,
                "code_verifier": state_data["verifier"],
            }
        )
        tokens["account_id"] = self.identity(tokens["access_token"])
        item = self.connection(db, connection_id, user_id, lock=True)
        if item.oauth_generation != digest:
            raise ProviderError("OAUTH_STATE_INVALID", retryable=False)
        from app.db.models.provider_sync import ProviderSyncState

        if (
            item.external_account_id
            and item.external_account_id != tokens["account_id"]
        ):
            db.execute(
                delete(ProviderSyncState).where(
                    ProviderSyncState.connection_id == item.id
                )
            )
        else:
            for sync in db.scalars(
                select(ProviderSyncState)
                .where(ProviderSyncState.connection_id == item.id)
                .with_for_update()
            ):
                sync.status, sync.next_run_at, sync.attempt_count, sync.last_error = (
                    "pending",
                    now,
                    0,
                    None,
                )
                sync.lease_token, sync.lease_expires_at = None, None
                sync.encrypted_checkpoint = None
                sync.coverage_start_at = sync.coverage_through_at = (
                    sync.round_started_at
                ) = None
                sync.last_success_at = None
        stored = db.get(IntegrationCredential, item.id)
        if stored is None:
            stored = IntegrationCredential(connection_id=item.id, user_id=user_id)
            db.add(stored)
        stored.encrypted_tokens = self.encrypt(tokens, item.id)
        stored.expires_at = now + timedelta(seconds=tokens["expires_in"])
        item.scopes, item.external_account_id, item.status = (
            list(tokens["scopes"]),
            tokens["account_id"],
            "connected",
        )
        item.connected_at, item.revoked_at, item.failure_status = now, None, None
        item.__dict__["_credential_state"] = "configured"
        from app.repositories.audit import record

        record(
            db, user_id, "integration", item.id, "provider.authorized",
            actor_type="USER", source_provider=item.provider.upper(),
            source_type=item.connection_type.upper(), source_provenance="OFFICIAL_OAUTH",
            source_reference=item.external_account_id,
            idempotency_key=f"SOURCE_AUTHORIZED:{item.id}:{digest}",
        )
        db.commit()
        return item

    def access_token(self, db, connection_id, user_id, now):
        self.configured()
        item = self.connection(db, connection_id, user_id, lock=True)
        stored = db.scalar(
            select(IntegrationCredential)
            .where(
                IntegrationCredential.connection_id == item.id,
                IntegrationCredential.user_id == user_id,
            )
            .with_for_update()
        )
        if item.status != "connected" or stored is None:
            raise ProviderError("AUTH_REQUIRED", retryable=False)
        tokens = self.decrypt(stored.encrypted_tokens, item.id)
        if (
            tokens.get("provider") != self.provider
            or tokens.get("kind") != self.kind
            or tokens.get("account_id") != item.external_account_id
        ):
            raise ProviderError(
                "AUTH_REQUIRED", retryable=False
            )  # metadata-only/legacy credentials are not full-access grants
        if stored.expires_at <= now + timedelta(seconds=60):
            try:
                fresh = self.grant(
                    {
                        "grant_type": "refresh_token",
                        "refresh_token": tokens["refresh_token"],
                    },
                    previous_refresh=tokens["refresh_token"],
                )
            except ProviderError as error:
                if not error.retryable:
                    item.status = "error"
                    item.failure_status = error.code
                    db.delete(stored)
                    db.commit()
                raise
            fresh["account_id"] = tokens["account_id"]
            tokens = fresh
            stored.encrypted_tokens = self.encrypt(tokens, item.id)
            stored.expires_at = now + timedelta(seconds=fresh["expires_in"])
        db.commit()
        access = tokens.get("access_token")
        if not isinstance(access, str) or not access:
            raise ProviderError("CREDENTIAL_UNAVAILABLE", retryable=False)
        if self.identity(access) != tokens["account_id"]:
            raise ProviderError("PERMISSION_DENIED", retryable=False)
        return access

    def authorize_projection(self, db, connection, now):
        """Read-only local grant check; no refresh under a planning transaction.

        Remote revocation is known only after a provider reports it. A valid
        refresh grant may outlive an access token; an unusable expired grant may not.
        """
        self.configured()
        stored = db.scalar(
            select(IntegrationCredential)
            .where(
                IntegrationCredential.connection_id == connection.id,
                IntegrationCredential.user_id == connection.user_id,
            )
            .execution_options(populate_existing=True)
        )
        granted = {
            s.removeprefix("https://graph.microsoft.com/").casefold()
            for s in connection.scopes
        }
        required = {s.casefold() for s in self.scopes} - {"offline_access"}
        if (
            connection.status != "connected"
            or not connection.oauth_generation
            or stored is None
            or stored.user_id != connection.user_id
            or not required <= granted
        ):
            raise ProviderError("AUTH_REQUIRED", retryable=False)
        tokens = self.decrypt(stored.encrypted_tokens, connection.id)
        if (
            tokens.get("provider") != self.provider
            or tokens.get("kind") != self.kind
            or tokens.get("account_id") != connection.external_account_id
            or not isinstance(tokens.get("access_token"), str)
            or not tokens.get("access_token")
            or stored.expires_at <= now + timedelta(seconds=60)
            and not tokens.get("refresh_token")
        ):
            raise ProviderError("AUTH_REQUIRED", retryable=False)


def account_oauth(settings, connection, *, transport=None):
    return AccountOAuth(
        settings, connection.provider, connection.connection_type, transport=transport
    )
