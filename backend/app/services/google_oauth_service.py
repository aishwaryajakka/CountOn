
"""Google OAuth helpers for Calendar integration."""

from urllib.parse import urlencode

from app.core.config import get_settings

from datetime import datetime, timedelta, timezone

import httpx


GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"

GOOGLE_CALENDAR_SCOPES = [
    "openid",
    "email",
    "https://www.googleapis.com/auth/calendar.events.readonly",
]


class GoogleOAuthError(ValueError):
    """Raised when Google OAuth configuration is incomplete."""


def build_authorization_url(state: str) -> str:
    """Build Google's authorization URL without exposing client secrets."""
    settings = get_settings()

    if not settings.google_client_id:
        raise GoogleOAuthError("Google OAuth client ID is not configured.")

    if not settings.google_redirect_uri:
        raise GoogleOAuthError("Google OAuth redirect URI is not configured.")

    if not state:
        raise GoogleOAuthError("OAuth state cannot be empty.")

    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(GOOGLE_CALENDAR_SCOPES),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": "consent",
        "state": state,
    }

    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"




def exchange_authorization_code(code: str) -> dict:
    """Exchange Google's authorization code for tokens."""
    settings = get_settings()

    if not code:
        raise GoogleOAuthError("Authorization code is missing.")

    if not settings.google_client_id:
        raise GoogleOAuthError("Google OAuth client ID is not configured.")

    if not settings.google_client_secret:
        raise GoogleOAuthError("Google OAuth client secret is not configured.")

    if not settings.google_redirect_uri:
        raise GoogleOAuthError("Google OAuth redirect URI is not configured.")

    response = httpx.post(
        GOOGLE_TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret.get_secret_value(),
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=10.0,
        follow_redirects=False,
    )

    if response.is_error:
        # Do not expose Google's response, which may contain sensitive details.
        raise GoogleOAuthError("Google token exchange failed.")

    try:
        tokens = response.json()
    except ValueError:
        raise GoogleOAuthError("Google returned an invalid token response.") from None

    access_token = tokens.get("access_token")
    expires_in = tokens.get("expires_in")

    if not isinstance(access_token, str) or not access_token:
        raise GoogleOAuthError("Google did not return an access token.")

    if not isinstance(expires_in, (int, float)) or isinstance(expires_in, bool) or expires_in <= 0:
        raise GoogleOAuthError("Google returned an invalid token expiry.")

    return {
        "access_token": access_token,
        "refresh_token": tokens.get("refresh_token"),
        "expires_at": datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        "scope": tokens.get("scope", ""),
        "token_type": tokens.get("token_type", "Bearer"),
    }



GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"


def fetch_google_userinfo(access_token: str) -> dict:
    """Fetch and validate the Google account identity."""
    if not isinstance(access_token, str) or not access_token:
        raise GoogleOAuthError("Google access token is missing.")

    try:
        response = httpx.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10.0,
            follow_redirects=False,
        )
        response.raise_for_status()
        userinfo = response.json()
    except (httpx.HTTPError, ValueError):
        raise GoogleOAuthError(
            "Could not verify the Google account."
        ) from None

    if not isinstance(userinfo, dict):
        raise GoogleOAuthError("Google returned invalid account information.")

    subject = userinfo.get("sub")
    email = userinfo.get("email")

    if (
        not isinstance(subject, str)
        or not subject
        or not isinstance(email, str)
        or not email
    ):
        raise GoogleOAuthError(
            "Google account information is incomplete."
        )

    return {
        "sub": subject,
        "email": email,
    }



def refresh_google_access_token(refresh_token: str) -> dict:
    """Refresh an expired Google access token."""
    settings = get_settings()

    if not refresh_token:
        raise GoogleOAuthError("Google refresh token is missing.")

    if not settings.google_client_id or not settings.google_client_secret:
        raise GoogleOAuthError("Google OAuth configuration is incomplete.")

    try:
        response = httpx.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret.get_secret_value(),
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            timeout=10.0,
            follow_redirects=False,
        )
        response.raise_for_status()
        tokens = response.json()
    except (httpx.HTTPError, ValueError):
        raise GoogleOAuthError("Google access token refresh failed.") from None

    access_token = tokens.get("access_token")
    expires_in = tokens.get("expires_in")

    if (
        not isinstance(access_token, str)
        or not access_token
        or not isinstance(expires_in, (int, float))
        or isinstance(expires_in, bool)
        or expires_in <= 0
    ):
        raise GoogleOAuthError("Google returned an invalid refresh response.")

    return {
        "access_token": access_token,
        "expires_at": datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        "token_type": tokens.get("token_type", "Bearer"),
    }
