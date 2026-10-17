

"""Load, refresh, and persist Google OAuth credentials."""

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories import integration as integration_repository
from app.services.google_oauth_service import (
    GoogleOAuthError,
    refresh_google_access_token,
)
from app.services.oauth_credential_service import (
    get_credentials,
    save_credentials,
)


def get_valid_google_access_token(
    db: Session,
    *,
    connection_id: UUID,
    user_id: UUID,
) -> str:
    """Return a valid token for an owned, connected Google Calendar."""
    connection = integration_repository.get(db, connection_id, user_id)

    if (
        connection is None
        or connection.provider != "google"
        or connection.connection_type != "calendar"
        or connection.status != "connected"
    ):
        raise GoogleOAuthError(
            "Connected Google Calendar integration was not found."
        )

    credentials = get_credentials(db, connection_id)

    if credentials is None:
        raise GoogleOAuthError("Google credentials were not found.")

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
        raise GoogleOAuthError(
            "Google refresh token is unavailable; reconnect the account."
        )

    refreshed = refresh_google_access_token(refresh_token)

    scopes = " ".join(connection.scopes or [])

    save_credentials(
        db,
        connection_id=connection_id,
        user_id=user_id,
        provider="google",
        access_token=refreshed["access_token"],
        refresh_token=None,
        expires_at=refreshed["expires_at"],
        token_type=refreshed.get("token_type") or "Bearer",
        scopes=scopes,
    )

    # Leave commit/rollback to the caller's transaction boundary.
    db.flush()

    return refreshed["access_token"]
