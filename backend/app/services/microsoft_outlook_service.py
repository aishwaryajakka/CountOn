
"""Fetch Outlook emails through Microsoft Graph."""

from typing import Any
from uuid import UUID

import httpx
from sqlalchemy.orm import Session

from app.services.microsoft_token_service import (
    MicrosoftOAuthError,
    get_valid_microsoft_access_token,
)


GRAPH_MESSAGES_URL = "https://graph.microsoft.com/v1.0/me/messages"


class MicrosoftOutlookError(Exception):
    """Raised when Outlook email retrieval fails."""


def list_outlook_emails(
    db: Session,
    *,
    connection_id: UUID,
    user_id: UUID,
    top: int = 25,
) -> dict[str, Any]:
    """Fetch recent Outlook messages for an owned connected account."""

    if not 1 <= top <= 100:
        raise ValueError("top must be between 1 and 100")

    try:
        access_token = get_valid_microsoft_access_token(
            db,
            connection_id=connection_id,
            user_id=user_id,
            connection_type="email",
        )

        # Persist any refreshed credentials before making the Graph request.
        db.commit()

        response = httpx.get(
            GRAPH_MESSAGES_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "$top": top,
                "$orderby": "receivedDateTime desc",
                "$select": (
                    "id,subject,from,receivedDateTime,bodyPreview,"
                    "body,internetMessageId"
                ),
            },
            timeout=15.0,
            follow_redirects=False,
        )
        response.raise_for_status()
        payload = response.json()


    except MicrosoftOAuthError:
        db.rollback()
        raise
    except httpx.HTTPStatusError as exc:
        db.rollback()

        if exc.response.status_code == 401:
            raise MicrosoftOutlookError(
                "Microsoft rejected the token; reconnect Outlook."
            ) from None

        if exc.response.status_code == 403:
            raise MicrosoftOutlookError(
                "Microsoft denied email access; check the Mail.Read permission."
            ) from None

        raise MicrosoftOutlookError(
            "Microsoft Graph could not return Outlook emails."
        ) from None
    except (httpx.HTTPError, ValueError):
        db.rollback()
        raise MicrosoftOutlookError(
            "Could not retrieve Outlook emails."
        ) from None

    if not isinstance(payload, dict) or not isinstance(
        payload.get("value"), list
    ):
        raise MicrosoftOutlookError(
            "Microsoft Graph returned an invalid email response."
        )

    return payload
