
"""Normalized evidence ingestion; source names are deliberately open-ended."""

import logging
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core import observability
from app.core.exceptions import (
    ExpectationNotFoundError,
    IdempotencyConflictError,
)
from app.db.models import Evidence, Expectation
from app.repositories import evidence as repository
from app.repositories import operations
from app.schemas.evidence import EvidenceCreate

from app.services.expectation_service import get_expectation


logger = logging.getLogger(__name__)


def add_evidence(
    db: Session,
    expectation_id: UUID,
    payload: EvidenceCreate,
    user_id: UUID,
    idempotency_key: str | None = None,
) -> Evidence:
    try:
        # Serialize evidence ingestion for this expectation.
        expectation = db.scalar(
            select(Expectation)
            .where(
                Expectation.id == expectation_id,
                Expectation.user_id == user_id,
            )
            .with_for_update()
        )

        if expectation is None:
            raise ExpectationNotFoundError(expectation_id)

        # Check for an existing submission after acquiring the lock.
        checks = []
        if idempotency_key:
            checks.append(Evidence.idempotency_key == idempotency_key)

        if payload.external_event_id:
            checks.append(
                (Evidence.source == payload.source)
                & (
                    Evidence.external_event_id
                    == payload.external_event_id
                )
            )

        if checks:
            existing_rows = list(
                db.scalars(
                    select(Evidence).where(
                        Evidence.expectation_id == expectation_id,
                        or_(*checks),
                    )
                )
            )

            if len(existing_rows) > 1:
                raise IdempotencyConflictError()

            existing = existing_rows[0] if existing_rows else None

            if existing is not None:
                if any(
                    getattr(existing, key) != value
                    for key, value in payload.model_dump().items()
                ):
                    raise IdempotencyConflictError()

                if (
                    idempotency_key
                    and existing.idempotency_key != idempotency_key
                ):
                    raise IdempotencyConflictError()

                db.commit()
                return existing

        # Create evidence and its audit event atomically.
        evidence = Evidence(
            expectation_id=expectation_id,
            **payload.model_dump(),
            idempotency_key=idempotency_key,
        )
        db.add(evidence)
        db.flush()

        operations.audit(
            db,
            expectation,
            "evidence.ingested",
            evidence.id,
        )

        db.commit()
        db.refresh(evidence)

    except Exception:
        db.rollback()
        raise

    observability.record("evidence_ingested")
    logger.info(
        "Evidence added id=%s expectation_id=%s",
        evidence.id,
        expectation_id,
    )
    return evidence

def list_evidence(
    db: Session,
    expectation_id: UUID,
    user_id: UUID,
    limit: int = 100,
    offset: int = 0,
) -> list[Evidence]:
    get_expectation(db, expectation_id, user_id)

    return repository.list_evidence_for_expectation(
        db,
        expectation_id,
        limit,
        offset,
    )

    observability.record("evidence_ingested")
    db.refresh(evidence)
    logger.info("Evidence added id=%s expectation_id=%s", evidence.id, expectation_id)
    return evidence