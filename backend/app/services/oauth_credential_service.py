
"""Persist OAuth credentials encrypted and connection metadata safely."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session


from app.db.models.integration import IntegrationConnection
from app.db.models.oauth_credential import OAuthCredential
from app.repositories import audit
from app.services.oauth_crypto import encrypt_token



def save_google_connection(
    db: Session,
    user_id: UUID,
    user_info: dict,
    token: dict,
) -> IntegrationConnection:
    """Save the Google account and encrypted tokens atomically."""
    google_id = user_info.get("sub")
    email = user_info.get("email")

    access_token = token.get("access_token")
    if not google_id or not email or not access_token:
        raise ValueError("Google account information is incomplete.")

    refresh_token = token.get("refresh_token")

    print("Google refresh token received:", bool(refresh_token))
    print("Google token expiry received:", token.get("expires_at") is not None)
    encrypted_access_token = encrypt_token(access_token)
    encrypted_refresh_token = (
        encrypt_token(refresh_token) if refresh_token else None
    )


    scopes_value = token.get("scope") or ""

    if isinstance(scopes_value, str):
        scopes = scopes_value.split()
    else:
        scopes = list(scopes_value or [])

    print("DEBUG OAuth token scopes:", repr(scopes))


    # Preserve Gmail read-only scope when Google returns it
    # in the authorization token response.
    required_scope = "https://www.googleapis.com/auth/gmail.readonly"

    if required_scope in scopes_value if isinstance(scopes_value, str) else required_scope in scopes:
        if required_scope not in scopes:
            scopes.append(required_scope)

    # Preserve Gmail read-only scope when Google returns it
    # in the authorization token response.
    required_scope = "https://www.googleapis.com/auth/gmail.readonly"

    if required_scope in scopes_value if isinstance(scopes_value, str) else required_scope in scopes:
        if required_scope not in scopes:
            scopes.append(required_scope)
    print("Google scopes returned:", scopes_value)
    if isinstance(scopes_value, str):
        scopes = scopes_value.split()
    else:
        scopes = list(scopes_value or [])

    try:
        connection = db.execute(
            select(IntegrationConnection).where(
                IntegrationConnection.user_id == user_id,
                IntegrationConnection.provider == "google",
                IntegrationConnection.connection_type == "email",
                IntegrationConnection.external_account_id == google_id,
            )
        ).scalar_one_or_none()

        if connection is None:
            connection = IntegrationConnection(
                user_id=user_id,
                provider="google",
                connection_type="email",
                external_account_id=google_id,
                display_name=email,
                status="connected",
                scopes=scopes,
            )
            db.add(connection)
            db.flush()
        else:
            connection.display_name = email
            connection.status = "connected"
            connection.scopes = scopes

        credential = db.execute(
            select(OAuthCredential).where(
                OAuthCredential.integration_id == connection.id
            )
        ).scalar_one_or_none()

        if credential is None:
            credential = OAuthCredential(
                integration_id=connection.id,
                user_id=user_id,
                provider="google",
                access_token_encrypted=encrypted_access_token,
                refresh_token_encrypted=encrypted_refresh_token,
                token_type=token.get("token_type", "Bearer"),
                expires_at=(
                    datetime.fromtimestamp(
                        float(token["expires_at"]), tz=timezone.utc
                    )
                    if token.get("expires_at") is not None
                    else None
                ),
                scopes=" ".join(scopes),
            )
            db.add(credential)
        else:
            credential.access_token_encrypted = encrypted_access_token
            if encrypted_refresh_token is not None:
                credential.refresh_token_encrypted = encrypted_refresh_token
            credential.token_type = token.get("token_type", "Bearer")
            credential.expires_at = (
                datetime.fromtimestamp(
                    float(token["expires_at"]), tz=timezone.utc
                )
                if token.get("expires_at") is not None
                else None
            )
            credential.scopes = " ".join(scopes)

        audit.record(
            db,
            user_id,
            "integration",
            connection.id,
            "integration.google_connected",
            metadata={"provider": "google", "email": email},
        )

        db.commit()
        db.refresh(connection)
        return connection
    except Exception:
        db.rollback()
        raise
