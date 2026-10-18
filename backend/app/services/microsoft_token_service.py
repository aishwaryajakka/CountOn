
"""Load, refresh, and persist Microsoft OAuth credentials."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.repositories import integration as integration_repository
from app.services.microsoft_oauth_service import (
    refresh_access_token,
)
from app.services.oauth_credential_service import (
    get_credentials,
    save_credentials,
)


class MicrosoftOAuthError(Exception):
    """Raised when Microsoft credentials or token refresh fail."""


def get_valid_microsoft_access_token(
    db: Session,
    *,
    connection_id: UUID,
    user_id: UUID,
    connection_type: str = "email",
) -> str:
    """Return a valid access token for an owned Microsoft integration."""

    connection = integration_repository.get(db, connection_id, user_id)

    if (
        connection is None
        or connection.provider != "microsoft"
        or connection.connection_type != connection_type
        or connection.status != "connected"
    ):
        raise MicrosoftOAuthError(
            "Connected Microsoft integration was not found."
        )

    credentials = get_credentials(db, connection_id)

    if credentials is None:
        raise MicrosoftOAuthError(
            "Microsoft credentials were not found; reconnect the account."
        )

    access_token = credentials.get("access_token")
    refresh_token = credentials.get("refresh_token")
    expires_at = credentials.get("expires_at")
    now = datetime.now(timezone.utc)

    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    needs_refresh = (
        not access_token
        or expires_at is None
        or expires_at <= now + timedelta(seconds=60)
    )

    if not needs_refresh:
        return access_token

    if not refresh_token:
        raise MicrosoftOAuthError(
            "Microsoft refresh token is unavailable; reconnect the account."
        )

    try:
        refreshed = _refresh_token(refresh_token)
    except (httpx.HTTPError, ValueError, KeyError, RuntimeError):
        raise MicrosoftOAuthError(
            "Microsoft token refresh failed; reconnect the account if needed."
        ) from None

    new_access_token = refreshed.get("access_token")
    expires_in = refreshed.get("expires_in")

    if (
        not isinstance(new_access_token, str)
        or not new_access_token
        or not isinstance(expires_in, (int, float))
        or isinstance(expires_in, bool)
        or expires_in <= 0
    ):
        raise MicrosoftOAuthError(
            "Microsoft returned invalid refreshed credentials."
        )

    new_refresh_token = refreshed.get("refresh_token") or refresh_token
    scopes = " ".join(connection.scopes or [])

    save_credentials(
        db,
        connection_id=connection_id,
        user_id=user_id,
        provider="microsoft",
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        expires_at=now + timedelta(seconds=expires_in),
        token_type=refreshed.get("token_type") or "Bearer",
        scopes=refreshed.get("scope") or scopes,
    )

    # Leave transaction commit to the calling service.
    db.flush()

    return new_access_token


def _refresh_token(refresh_token: str) -> dict:
    """Call the existing Microsoft refresh helper synchronously."""
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(refresh_access_token(refresh_token))

    raise MicrosoftOAuthError(
        "Token refresh must run outside an active async event loop."
    )
