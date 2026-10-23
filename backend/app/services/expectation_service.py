"""Expectation domain validation and transactional lifecycle operations."""

import logging
from typing import Any, Literal
from uuid import UUID, uuid4

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.exceptions import ExpectationNotFoundError, InvalidExpectationError
from app.db.models import Expectation, ExpectationStatus, ExpectationType, MonitoringJob
from app.repositories import expectation as repository
from app.repositories import operations
from app.repositories.profile import ensure_profile
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


def create_expectation(db: Session, payload: ExpectationCreate, user_id: UUID, *, compiler_metadata: dict | None = None, commit: bool = True, creation_source: Literal["web", "mcp"] | None = None) -> Expectation:
    from app.repositories import audit

    try:
        validate_expectation(payload.model_dump())
    except InvalidExpectationError:
        # A valid authenticated request with invalid domain fields has no row ID.
        # Store a safe attempt ID, never the rejected claim/payload or exception.
        if creation_source:
            ensure_profile(db, user_id)
            audit.record(db, user_id, "expectation", uuid4(), "expectation.creation_failed",
                metadata={"channel": creation_source, "status": "FAILED"},
                actor_type="USER", source_provider=creation_source.upper())
            if commit:
                db.commit()
        raise
    try:
        ensure_profile(db, user_id)
        metadata = dict(compiler_metadata or {})
        if creation_source:
            metadata["creation_source"] = creation_source
        expectation = repository.create_expectation(db, payload, user_id, metadata)
        operations.ensure_job(db, expectation)
        operations.audit(
            db, expectation, "expectation.created", actor_type="USER",
            idempotency_key=f"EXPECTATION_CREATED:{expectation.id}",
            source_provider=creation_source.upper() if creation_source else None,
            source_type="EXPECTATION_CAPTURE",
            source_provenance="AUTHENTICATED_WEB" if creation_source == "web" else "AUTHENTICATED_MCP" if creation_source == "mcp" else None,
            metadata={"status": "SUCCESS", **({"channel": creation_source} if creation_source else {})},
        )
        if commit:
            db.commit()
        else:
            db.flush()
    except Exception:
        db.rollback()
        raise
    db.refresh(expectation)
    logger.info("Expectation created id=%s", expectation.id)
    return expectation


def get_expectation(db: Session, expectation_id: UUID, user_id: UUID) -> Expectation:
    expectation = repository.get_expectation(db, expectation_id, user_id)
    if expectation is None:
        raise ExpectationNotFoundError(expectation_id)
    return expectation


def list_expectations(
    db: Session, user_id: UUID, status: ExpectationStatus | None = None, limit: int = 100, offset: int = 0, type: ExpectationType | None = None,
) -> list[Expectation]:
    return repository.list_expectations(db, user_id, status, limit, offset, type)


def update_expectation(db: Session, expectation_id: UUID, payload: ExpectationUpdate, user_id: UUID) -> Expectation:
    expectation = get_expectation(db, expectation_id, user_id)
    changes = payload.model_dump(exclude_unset=True)
    for name in ("claim", "evidence_sources", "materiality_threshold", "status"):
        if name in changes and changes[name] is None:
            raise InvalidExpectationError(f"{name} cannot be null")
    values = {name: getattr(expectation, name) for name in ("type", "metric", "comparison", "baseline", "target_value")}
    validate_expectation(values | changes)
    try:
        repository.update_expectation(db, expectation, changes)
        if expectation.status in (ExpectationStatus.cancelled, ExpectationStatus.resolved):
            db.execute(update(MonitoringJob).where(MonitoringJob.expectation_id == expectation_id,
                MonitoringJob.user_id == user_id, MonitoringJob.status.in_(['pending','running','paused']))
                .values(status='cancelled', lease_token=None, lease_expires_at=None))
        elif any(field in changes for field in ('metric', 'comparison', 'baseline', 'target_value', 'deadline', 'materiality_threshold', 'evidence_sources', 'status')):
            from datetime import datetime, timezone

            from app.monitoring.sources import wake
            wake(db, expectation, datetime.now(timezone.utc))
        action = (
            "expectation.cancelled"
            if expectation.status == ExpectationStatus.cancelled
            else "expectation.updated"
        )
        operations.audit(
            db, expectation, action, actor_type="USER",
            idempotency_key=f"EXPECTATION_CANCELLED:{expectation.id}"
            if action == "expectation.cancelled" else None,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(expectation)
    return expectation


def delete_expectation(db: Session, expectation_id: UUID, user_id: UUID) -> None:
    expectation = get_expectation(db, expectation_id, user_id)
    try:
        operations.audit(
            db, expectation, "expectation.deleted", actor_type="USER",
            idempotency_key=f"EXPECTATION_CANCELLED:{expectation.id}",
        )
        db.flush()
        repository.delete_expectation(db, expectation)
        db.commit()
    except Exception:
        db.rollback()
        raise
