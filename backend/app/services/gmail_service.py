
"""Fetch messages from the authenticated user's connected Gmail account."""

import base64
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from uuid import UUID

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.integration import IntegrationConnection
from app.db.models.oauth_credential import OAuthCredential
from app.services.oauth_crypto import decrypt_token


def fetch_gmail_messages(
    db: Session,
    user_id: UUID,
    max_results: int = 10,
) -> list[dict]:
    """Fetch recent Gmail messages without saving them as evidence."""

    if not 1 <= max_results <= 100:
        raise ValueError("max_results must be between 1 and 100.")

    connection = db.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.user_id == user_id,
            IntegrationConnection.provider == "google",
            IntegrationConnection.connection_type == "email",
            IntegrationConnection.status == "connected",
        )
    )

    if connection is None:
        raise ValueError("No connected Google email account found.")

    credential = db.scalar(
        select(OAuthCredential).where(
            OAuthCredential.integration_id == connection.id,
            OAuthCredential.user_id == user_id,
            OAuthCredential.provider == "google",
        )
    )

    if credential is None:
        raise ValueError("Google OAuth credentials were not found.")

    required_scope = "https://www.googleapis.com/auth/gmail.readonly"

    credential_scopes = credential.scopes or ""

    if isinstance(credential_scopes, str):
        saved_scopes = credential_scopes.split()
    else:
        saved_scopes = list(credential_scopes)

    if required_scope not in saved_scopes:
        raise ValueError(
            f"Gmail read-only permission is missing. "
            f"Saved scopes: {saved_scopes}"
        )
        raise ValueError("Gmail read-only permission is missing.")

    access_token = decrypt_token(credential.access_token_encrypted)
    refresh_token = (
        decrypt_token(credential.refresh_token_encrypted)
        if credential.refresh_token_encrypted
        else None
    )

    credentials = Credentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=None,
        client_secret=None,
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        expiry=(
            credential.expires_at.replace(tzinfo=timezone.utc)
            if credential.expires_at
            and credential.expires_at.tzinfo is None
            else credential.expires_at
        ),
    )

    if credentials.expired and not credentials.refresh_token:
        raise ValueError(
            "Google access token expired. Reconnect your Google account."
        )

    service = build(
        "gmail",
        "v1",
        credentials=credentials,
        cache_discovery=False,
    )

    response = (
        service.users()
        .messages()
        .list(userId="me", maxResults=max_results)
        .execute()
    )

    messages = []

    for item in response.get("messages", []):
        message = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=item["id"],
                format="full",
            )
            .execute()
        )

        headers = {
            header["name"].lower(): header["value"]
            for header in message.get("payload", {}).get("headers", [])
        }

        internal_date = message.get("internalDate")
        received_at = (
            datetime.fromtimestamp(
                int(internal_date) / 1000,
                tz=timezone.utc,
            ).isoformat()
            if internal_date
            else parsedate_to_datetime(headers["date"]).isoformat()
            if headers.get("date")
            else None
        )

        messages.append(
            {
                "message_id": message["id"],
                "thread_id": message.get("threadId"),
                "sender": headers.get("from"),
                "subject": headers.get("subject"),
                "received_at": received_at,
                "snippet": message.get("snippet", ""),
            }
        )

    return messages
