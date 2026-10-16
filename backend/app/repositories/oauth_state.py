
"""Repository for one-time OAuth state validation."""

import hashlib
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db.models.oauth_state import OAuthState


STATE_TTL_SECONDS = 600


def hash_state(state: str) -> str:
    """Return a SHA-256 hash of the raw OAuth state."""
    return hashlib.sha256(state.encode("utf-8")).hexdigest()


def create_state(
    db: Session,
    *,
    user_id: UUID,
    state: str,
    provider: str = "google",
) -> OAuthState:
    """Store a hashed state that expires after ten minutes."""
    now = datetime.now(timezone.utc)

    record = OAuthState(
        user_id=user_id,
        provider=provider,
        state_hash=hash_state(state),
        expires_at=now + timedelta(seconds=STATE_TTL_SECONDS),
    )

    db.add(record)
    db.flush()
    return record


def consume_state(
    db: Session,
    *,
    state: str,
    provider: str = "google",
) -> UUID | None:
    """Atomically consume an unexpired state exactly once."""
    statement = (
        update(OAuthState)
        .where(
            OAuthState.state_hash == hash_state(state),
            OAuthState.provider == provider,
            OAuthState.expires_at > func.now(),
            OAuthState.consumed_at.is_(None),
        )
        .values(consumed_at=func.now())
        .returning(OAuthState.user_id)
    )

    user_id = db.execute(statement).scalar_one_or_none()
    db.flush()
    return user_id
