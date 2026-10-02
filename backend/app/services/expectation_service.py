"""Expectation domain validation and transactional lifecycle operations."""

import logging
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import ExpectationNotFoundError, InvalidExpectationError
from app.db.models import Expectation, ExpectationStatus, ExpectationType
from app.repositories import expectation as repository
from app.schemas.expectation import ExpectationCreate, ExpectationUpdate

logger = logging.getLogger(__name__)


def validate_expectation(values: dict[str, Any]) -> None:
    if values["type"] == ExpectationType.numeric_comparison:
        if not values.get("metric") or not values["metric"].strip():
            raise InvalidExpectationError("Numeric expectations require a metric")
        if values.get("comparison") is None:
            raise InvalidExpectationError("Numeric expectations require a comparison")
        if values.get("baseline") is None and values.get("target_value") is None:
            raise InvalidExpectationError("Numeric expectations require a baseline or target_value")


def create_expectation(db: Session, payload: ExpectationCreate, user_id: UUID | None = None) -> Expectation:
    validate_expectation(payload.model_dump())
    try:
        expectation = repository.create_expectation(db, payload, user_id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(expectation)
    logger.info("Expectation created id=%s", expectation.id)
    return expectation


def get_expectation(db: Session, expectation_id: UUID) -> Expectation:
    expectation = repository.get_expectation(db, expectation_id)
    if expectation is None:
        raise ExpectationNotFoundError(expectation_id)
    return expectation


def list_expectations(
    db: Session, status: ExpectationStatus | None = None, limit: int = 100, offset: int = 0,
) -> list[Expectation]:
    return repository.list_expectations(db, status, limit, offset)


def update_expectation(db: Session, expectation_id: UUID, payload: ExpectationUpdate) -> Expectation:
    expectation = get_expectation(db, expectation_id)
    changes = payload.model_dump(exclude_unset=True)
    for name in ("claim", "evidence_sources", "materiality_threshold", "status"):
        if name in changes and changes[name] is None:
            raise InvalidExpectationError(f"{name} cannot be null")
    values = {name: getattr(expectation, name) for name in ("type", "metric", "comparison", "baseline", "target_value")}
    validate_expectation(values | changes)
    try:
        repository.update_expectation(db, expectation, changes)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(expectation)
    return expectation


def delete_expectation(db: Session, expectation_id: UUID) -> None:
    expectation = get_expectation(db, expectation_id)
    try:
        repository.delete_expectation(db, expectation)
        db.commit()
    except Exception:
        db.rollback()
        raise
