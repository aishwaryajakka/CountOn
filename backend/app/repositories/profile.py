"""Idempotent PostgreSQL profile creation; no password or email storage."""

from uuid import UUID

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import Profile


def ensure_profile(db: Session, user_id: UUID) -> Profile:
    created_id=db.scalar(insert(Profile).values(id=user_id).on_conflict_do_nothing(index_elements=[Profile.id]).returning(Profile.id))
    if created_id is not None:
        from app.repositories.audit import record
        record(db,user_id,'profile',user_id,'profile.created')
    profile = db.get(Profile, user_id)
    if profile is None:
        raise RuntimeError("Profile creation did not persist")
    return profile


def delete_profile(db: Session, user_id: UUID) -> None:
    profile = db.get(Profile, user_id)
    if profile is not None:
        db.delete(profile)
        db.flush()
