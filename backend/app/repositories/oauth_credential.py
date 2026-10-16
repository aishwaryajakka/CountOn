
"""Persistence operations for encrypted OAuth credentials."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.oauth_credential import OAuthCredential


def get_by_connection_id(
    db: Session,
    connection_id: UUID,
) -> OAuthCredential | None:
    return db.scalar(
        select(OAuthCredential).where(
            OAuthCredential.connection_id == connection_id
        )
    )


def save(
    db: Session,
    *,
    connection_id: UUID,
    user_id: UUID,
    provider: str,
    encrypted_access_token: str,
    encrypted_refresh_token: str | None = None,
    expires_at: datetime | None = None,
    token_type: str = "Bearer",
    scopes: str = "",
) -> OAuthCredential:
    item = get_by_connection_id(db, connection_id)

    if item is None:
        item = OAuthCredential(
            connection_id=connection_id,
            user_id=user_id,
            provider=provider,
            encrypted_access_token=encrypted_access_token,
            encrypted_refresh_token=encrypted_refresh_token,
            expires_at=expires_at,
            token_type=token_type,
            scopes=scopes,
        )
        db.add(item)
    else:
        item.user_id = user_id
        item.provider = provider
        item.encrypted_access_token = encrypted_access_token

        # Preserve the existing refresh token if Google omits a new one.
        if encrypted_refresh_token is not None:
            item.encrypted_refresh_token = encrypted_refresh_token

        item.expires_at = expires_at
        item.token_type = token_type
        item.scopes = scopes

    db.flush()
    return item


def delete(db: Session, connection_id: UUID) -> None:
    item = get_by_connection_id(db, connection_id)

    if item is not None:
        db.delete(item)
        db.flush()
