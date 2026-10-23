
"""Create and validate one-time OAuth state values."""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models.oauth_state import OAuthState


STATE_TTL_MINUTES = 10


def create_state(
    db: Session,
    user_id: UUID,
    provider: str,
) -> str:
    """Create a random state; store only its hash."""
    raw_state = secrets.token_urlsafe(32)
    state_hash = hashlib.sha256(
        raw_state.encode("utf-8")
    ).hexdigest()

    record = OAuthState(
        state_hash=state_hash,
        user_id=user_id,
        provider=provider,
        expires_at=datetime.now(timezone.utc)
        + timedelta(minutes=STATE_TTL_MINUTES),
    )

    db.add(record)
    db.commit()

    return raw_state


def consume_state(
    db: Session,
    raw_state: str,
    provider: str,
) -> UUID | None:
    """Validate and consume a state value exactly once."""
    if not raw_state:
        return None

    state_hash = hashlib.sha256(
        raw_state.encode("utf-8")
    ).hexdigest()
    now = datetime.now(timezone.utc)

    statement = (
        update(OAuthState)
        .where(
            OAuthState.state_hash == state_hash,
            OAuthState.provider == provider,
            OAuthState.expires_at > now,
            OAuthState.consumed_at.is_(None),
        )
        .values(consumed_at=now)
        .returning(OAuthState.user_id)
    )

    try:
        user_id = db.execute(statement).scalar_one_or_none()
        db.commit()
        return user_id
    except Exception:
        db.rollback()
        raise
