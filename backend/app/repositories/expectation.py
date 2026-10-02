"""Expectation database operations; services own commit boundaries."""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Expectation, ExpectationStatus
from app.schemas.expectation import ExpectationCreate


def create_expectation(db: Session, payload: ExpectationCreate, user_id: UUID | None = None) -> Expectation:
    expectation = Expectation(**payload.model_dump(), user_id=user_id)
    db.add(expectation)
    db.flush()
    return expectation


def get_expectation(db: Session, expectation_id: UUID) -> Expectation | None:
    return db.scalar(select(Expectation).where(Expectation.id == expectation_id))


def list_expectations(
    db: Session, status: ExpectationStatus | None = None, limit: int = 100, offset: int = 0,
) -> list[Expectation]:
    statement = select(Expectation)
    if status is not None:
        statement = statement.where(Expectation.status == status)
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
