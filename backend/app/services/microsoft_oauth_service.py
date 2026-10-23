
"""Microsoft identity platform OAuth helpers for Outlook and Calendar."""

from urllib.parse import urlencode

import httpx
import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)

GRAPH_BASE_URL = "https://graph.microsoft.com/v1.0"


def _tenant() -> str:
    return get_settings().microsoft_tenant_id


def _client_credentials() -> tuple[str, str]:
    settings = get_settings()

    if not settings.microsoft_client_id:
        raise RuntimeError("MICROSOFT_CLIENT_ID is not configured")

    if not settings.microsoft_client_secret:
        raise RuntimeError("MICROSOFT_CLIENT_SECRET is not configured")

    return (
        settings.microsoft_client_id,
        settings.microsoft_client_secret.get_secret_value(),
    )


def _scopes(connection_type: str) -> list[str]:
    """Return the OAuth scopes required for the requested connection."""

    if connection_type == "email":
        resource_scopes = ["Mail.Read"]
    elif connection_type == "calendar":
        resource_scopes = ["Calendars.Read"]
    else:
        raise ValueError("Unsupported Microsoft connection type")

    return [
        "openid",
        "profile",
        "email",
        "offline_access",
        "User.Read",
        *resource_scopes,
    ]


def build_authorization_url(
    *,
    state: str,
    redirect_uri: str,
    connection_type: str,
) -> str:
    """Build an authorization URL for Outlook email or Calendar."""

    client_id, _ = _client_credentials()

    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": " ".join(_scopes(connection_type)),
        "state": state,
    }

    return (
        f"https://login.microsoftonline.com/{_tenant()}/oauth2/v2.0/authorize?"
        f"{urlencode(params)}"
    )


async def exchange_authorization_code(
    *,
    code: str,
    redirect_uri: str,
    connection_type: str,
) -> dict:
    """Exchange an authorization code for Microsoft OAuth tokens."""

    client_id, client_secret = _client_credentials()

    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "scope": " ".join(_scopes(connection_type)),
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"https://login.microsoftonline.com/{_tenant()}/oauth2/v2.0/token",
            data=payload,
        )

    if response.is_error:
        try:
            error_data = response.json()
        except ValueError:
            error_data = {}

        logger.error(
            "Microsoft token exchange failed: error=%s, description=%s, codes=%s, trace_id=%s",
            error_data.get("error"),
            error_data.get("error_description"),
            error_data.get("error_codes"),
            error_data.get("trace_id"),
        )
        response.raise_for_status()

    return response.json()


async def refresh_access_token(refresh_token: str) -> dict:
    """Refresh a Microsoft access token using the existing grant."""

    client_id, client_secret = _client_credentials()

    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.post(
            f"https://login.microsoftonline.com/{_tenant()}/oauth2/v2.0/token",
            data=payload,
        )

    response.raise_for_status()
    return response.json()


async def fetch_user_profile(access_token: str) -> dict:
    """Return the Microsoft account identity for the connected user."""

    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{GRAPH_BASE_URL}/me",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"$select": "id,displayName,mail,userPrincipalName"},
        )

        if response.is_error:
            try:
                error_data = response.json()
            except ValueError:
                error_data = {"error": response.text[:500]}

            safe_error = {
                "error": error_data.get("error"),
                "error_description": error_data.get("error_description"),
                "error_codes": error_data.get("error_codes"),
                "timestamp": error_data.get("timestamp"),
                "trace_id": error_data.get("trace_id"),
                "correlation_id": error_data.get("correlation_id"),
            }
            logger.error("Microsoft token exchange failed: %s", safe_error)
            response.raise_for_status()

        return response.json()

    if not profile.get("id"):
        raise RuntimeError("Microsoft profile did not include an account ID")

    return profile