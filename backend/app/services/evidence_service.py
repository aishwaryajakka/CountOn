"""Normalized evidence ingestion; source names are deliberately open-ended."""

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.db.models import Evidence
from app.repositories import evidence as repository
from app.schemas.evidence import EvidenceCreate
from app.services.expectation_service import get_expectation

logger = logging.getLogger(__name__)


def add_evidence(db: Session, expectation_id: UUID, payload: EvidenceCreate) -> Evidence:
    get_expectation(db, expectation_id)
    try:
        evidence = repository.create_evidence(db, expectation_id, payload)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(evidence)
    logger.info("Evidence added id=%s expectation_id=%s", evidence.id, expectation_id)
    return evidence


def list_evidence(db: Session, expectation_id: UUID) -> list[Evidence]:
    get_expectation(db, expectation_id)
    return repository.list_evidence_for_expectation(db, expectation_id)
