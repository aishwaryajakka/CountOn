"""Normalized evidence ingestion; source names are deliberately open-ended."""

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from sqlalchemy import select, or_
from app.db.models import Evidence, Expectation
from app.core.exceptions import IdempotencyConflictError
from app.core import observability
from app.repositories import operations
from app.repositories import evidence as repository
from app.schemas.evidence import EvidenceCreate
from app.services.expectation_service import get_expectation

logger = logging.getLogger(__name__)


def add_evidence(db: Session, expectation_id: UUID, payload: EvidenceCreate, user_id: UUID, idempotency_key: str | None = None) -> Evidence:
    expectation = get_expectation(db, expectation_id, user_id)
    try:
        if idempotency_key or payload.external_event_id:
            db.scalar(select(Expectation).where(Expectation.id==expectation_id,Expectation.user_id==user_id).with_for_update())
            checks=[]
            if idempotency_key:checks.append(Evidence.idempotency_key==idempotency_key)
            if payload.external_event_id:checks.append((Evidence.source==payload.source) & (Evidence.external_event_id==payload.external_event_id))
            existing_rows=list(db.scalars(select(Evidence).where(Evidence.expectation_id==expectation_id,or_(*checks))))
            if len(existing_rows)>1:raise IdempotencyConflictError()
            existing=existing_rows[0] if existing_rows else None
            if existing:
                if any(getattr(existing,k)!=v for k,v in payload.model_dump().items()):
                    raise IdempotencyConflictError()
                if idempotency_key and existing.idempotency_key != idempotency_key:
                    raise IdempotencyConflictError()
                db.commit()
                return existing
        evidence = repository.create_evidence(db, expectation_id, payload)
        evidence.idempotency_key = idempotency_key
        operations.audit(db, expectation, "evidence.ingested", evidence.id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    observability.record("evidence_ingested")
    db.refresh(evidence)
    logger.info("Evidence added id=%s expectation_id=%s", evidence.id, expectation_id)
    return evidence


def list_evidence(db: Session, expectation_id: UUID, user_id: UUID, limit: int = 100, offset: int = 0) -> list[Evidence]:
    get_expectation(db, expectation_id, user_id)
    return repository.list_evidence_for_expectation(db, expectation_id, limit, offset)
