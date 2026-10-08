"""Canonical demo identity provisioning, separate from tagged application data."""
from uuid import UUID

import httpx

from db.scripts._demo import DEMO_NAME, TAG, lock


def admin_headers(secret: str) -> dict[str, str]:
    headers = {"apikey": secret}
    if not secret.startswith("sb_secret_"):
        headers["Authorization"] = f"Bearer {secret}"
    return headers


def find_auth_user(client: httpx.Client, headers: dict, email: str) -> UUID | None:
    """Admin list is paginated; never create after an incomplete/failed lookup."""
    for page in range(1, 101):
        response = client.get("/auth/v1/admin/users", headers=headers,
                              params={"page": page, "per_page": 1000})
        response.raise_for_status()
        users = response.json()["users"]
        matches = [UUID(user["id"]) for user in users
                   if (user.get("email") or "").casefold() == email.casefold()]
        if len(matches) > 1:
            raise RuntimeError("Ambiguous demo Auth identity")
        if matches:
            return matches[0]
        if len(users) < 1000:
            return None
    raise RuntimeError("Auth lookup pagination limit reached; no account created")


def ensure_auth_user(client: httpx.Client, settings) -> UUID:
    if not settings.supabase_secret_key:
        print("Set backend-only SUPABASE_SECRET_KEY for demo Auth setup.")
        raise RuntimeError("Auth Admin configuration required")
    headers = admin_headers(settings.supabase_secret_key.get_secret_value())
    owner = find_auth_user(client, headers, settings.counton_demo_email)
    if owner is not None:
        if settings.counton_demo_user_id and settings.counton_demo_user_id != owner:
            print("COUNTON_DEMO_USER_ID differs from the Auth account found by email; correct the configured UUID.")
            raise RuntimeError("Demo UUID mismatch")
        return owner  # No password or metadata mutation on an existing account.
    if settings.counton_demo_user_id:
        print("No Auth account matches the demo email; remove the stale configured UUID before setup.")
        raise RuntimeError("Demo UUID mismatch")
    if not settings.counton_demo_password or not settings.counton_demo_password.get_secret_value():
        print("Set COUNTON_DEMO_PASSWORD in backend/.env.local or the process environment to create the account.")
        raise RuntimeError("Demo password required")
    response = client.post("/auth/v1/admin/users", headers=headers, json={
        "email": settings.counton_demo_email,
        "password": settings.counton_demo_password.get_secret_value(),
        "email_confirm": True,
        "user_metadata": {"display_name": DEMO_NAME, "full_name": DEMO_NAME,
                          "timezone": "America/Chicago"},
    })
    # Concurrent setup may win the unique-email race. Reuse it without a reset.
    if response.status_code in (409, 422):
        owner = find_auth_user(client, headers, settings.counton_demo_email)
        if owner is not None:
            return owner
    response.raise_for_status()
    return UUID(response.json()["id"])


def ensure_demo_profile(db, owner: UUID, *, verified_auth: bool = False):
    from app.db.models import Profile
    from app.repositories.audit import record

    lock(db, owner)
    profile = db.get(Profile, owner)
    if profile is not None and profile.demo_tag != TAG and not verified_auth:
        raise RuntimeError("Refusing to alter an unrelated profile")
    if profile is None:
        profile = Profile(id=owner, display_name=DEMO_NAME,
                          timezone="America/Chicago", demo_tag=TAG)
        db.add(profile)
        db.flush()
        record(db, owner, "profile", owner, "profile.created",
               metadata={"demo": True, "demo_tag": TAG})
    elif (profile.display_name, profile.timezone, profile.demo_tag) != (DEMO_NAME, "America/Chicago", TAG):
        # Auth lookup explicitly verifies this canonical account before adopting
        # a pre-existing profile. Application rows and unrelated audits stay intact.
        profile.display_name, profile.timezone, profile.demo_tag = DEMO_NAME, "America/Chicago", TAG
        record(db, owner, "profile", owner, "profile.updated",
               metadata={"demo": True, "demo_tag": TAG})
    db.commit()
    return profile
