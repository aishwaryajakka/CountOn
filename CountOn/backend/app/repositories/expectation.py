"""Expectation database operations; services own commit boundaries."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Expectation, ExpectationStatus, ExpectationType
from app.schemas.expectation import ExpectationCreate


def create_expectation(db: Session, payload: ExpectationCreate, user_id: UUID, compiler_metadata: dict | None = None) -> Expectation:
    expectation = Expectation(**payload.model_dump(), user_id=user_id, compiler_metadata=compiler_metadata or {})
    db.add(expectation)
    db.flush()
    return expectation


def get_expectation(db: Session, expectation_id: UUID, user_id: UUID) -> Expectation | None:
    return db.scalar(select(Expectation).where(Expectation.id == expectation_id, Expectation.user_id == user_id))


def list_expectations(
    db: Session, user_id: UUID, status: ExpectationStatus | None = None, limit: int = 100, offset: int = 0, type: ExpectationType | None = None,
) -> list[Expectation]:
    statement = select(Expectation).where(Expectation.user_id == user_id)
    if status is not None:
        statement = statement.where(Expectation.status == status)
    if type is not None:
        statement = statement.where(Expectation.type == type)
    statement = statement.order_by(Expectation.created_at.desc(), Expectation.id.desc()).limit(limit).offset(offset)
    return list(db.scalars(statement))


def update_expectation(db: Session, expectation: Expectation, changes: dict[str, Any]) -> Expectation:
    for name, value in changes.items():
        setattr(expectation, name, value)
    db.flush()
    return expectation


def delete_expectation(db: Session, expectation: Expectation) -> None:
    db.delete(expectation)
    db.flush()
