
"""Securely store and retrieve OAuth credentials."""

from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories import oauth_credential as repository
from app.services.oauth_token_encryption import encrypt_token, decrypt_token


def save_credentials(
    db: Session,
    *,
    connection_id: UUID,
    user_id: UUID | None = None,
    provider: str = "google",
    access_token: str,
    refresh_token: str | None = None,
    expires_at: datetime | None = None,
    token_type: str = "Bearer",
    scopes: str = "",
):
    encrypted_access = encrypt_token(access_token)
    encrypted_refresh = (
        encrypt_token(refresh_token) if refresh_token else None
    )

    return repository.save(
        db,
        connection_id=connection_id,
        user_id=user_id,
        provider=provider,
        encrypted_access_token=encrypted_access,
        encrypted_refresh_token=encrypted_refresh,
        expires_at=expires_at,
        token_type=token_type,
        scopes=scopes,
    )


def get_credentials(db: Session, connection_id: UUID) -> dict | None:
    item = repository.get_by_connection_id(db, connection_id)

    if item is None:
        return None

    return {
        "access_token": decrypt_token(item.encrypted_access_token),
        "refresh_token": (
            decrypt_token(item.encrypted_refresh_token)
            if item.encrypted_refresh_token
            else None
        ),
        "expires_at": item.expires_at,
    }


def delete_credentials(db: Session, connection_id: UUID) -> None:
    repository.delete(db, connection_id)
