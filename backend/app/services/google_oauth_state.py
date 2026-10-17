
"""Secure, one-time state management for Google OAuth."""

import secrets
from uuid import UUID

from sqlalchemy.orm import Session

from app.repositories import oauth_state as repository


def create_oauth_state(
    db: Session,
    user_id: UUID,
    provider: str = "google",
) -> str:
    """Generate a random state and persist its hash."""
    state = secrets.token_urlsafe(32)

    repository.create_state(
        db,
        user_id=user_id,
        state=state,
        provider=provider,
    )
    db.commit()

    return state


def consume_oauth_state(
    db: Session,
    state: str,
    provider: str = "google",
) -> UUID | None:
    """Consume a valid state once and persist the consumption."""
    if not state:
        return None

    try:
        user_id = repository.consume_state(
            db,
            state=state,
            provider=provider,
        )
        if user_id is None:
            db.rollback()
            return None

        db.commit()
        return user_id
    except Exception:
        db.rollback()
        raise
