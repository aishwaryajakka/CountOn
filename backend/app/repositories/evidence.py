"""Evidence database operations; ordering is observation time ascending."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Evidence
from app.schemas.evidence import EvidenceCreate


def create_evidence(db: Session, expectation_id: UUID, payload: EvidenceCreate) -> Evidence:
    evidence = Evidence(expectation_id=expectation_id, **payload.model_dump())
    db.add(evidence)
    db.flush()
    return evidence


def list_evidence_for_expectation(db: Session, expectation_id: UUID) -> list[Evidence]:
    statement = select(Evidence).where(Evidence.expectation_id == expectation_id).order_by(
        Evidence.observed_at, Evidence.created_at, Evidence.id,
    )
    return list(db.scalars(statement))
