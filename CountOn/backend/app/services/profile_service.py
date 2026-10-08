"""Application profile bootstrap after identity has been authenticated."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Profile
from app.repositories import profile as repository


def ensure_profile(db: Session, user_id: UUID) -> Profile:
    try:
        profile = repository.ensure_profile(db, user_id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return profile
