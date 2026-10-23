
"""Look up CountOn users through the Supabase Auth Admin API."""

from uuid import UUID

import httpx

from app.core.config import get_settings


def get_user_email(user_id: UUID) -> str:
    """Return a user's verified email from Supabase Auth."""
    settings = get_settings()

    if not settings.supabase_url or not settings.supabase_secret_key:
        raise RuntimeError("SUPABASE_ADMIN_LOOKUP_NOT_CONFIGURED")

    secret_key = settings.supabase_secret_key.get_secret_value()
    url = (
        f"{settings.supabase_url.rstrip('/')}"
        f"/auth/v1/admin/users/{user_id}"
    )

    try:
        response = httpx.get(
            url,
            headers={
                "apikey": secret_key,
                "Authorization": f"Bearer {secret_key}",
            },
            timeout=10,
            follow_redirects=False,
        )
        response.raise_for_status()
        user = response.json()
    except (httpx.HTTPError, ValueError):
        raise RuntimeError("SUPABASE_USER_LOOKUP_FAILED") from None

    email = user.get("email")
    if not isinstance(email, str) or not email.strip():
        raise RuntimeError("SUPABASE_USER_EMAIL_UNAVAILABLE")

    if user.get("email_confirmed_at") is None:
        raise RuntimeError("SUPABASE_USER_EMAIL_UNVERIFIED")

    return email.strip()
