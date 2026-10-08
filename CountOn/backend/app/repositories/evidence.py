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


def list_evidence_for_expectation(db: Session, expectation_id: UUID, limit: int = 100, offset: int = 0) -> list[Evidence]:
    statement = select(Evidence).where(Evidence.expectation_id == expectation_id).order_by(
        Evidence.observed_at, Evidence.created_at, Evidence.id,
    )
    statement = statement.limit(limit).offset(offset)
    return list(db.scalars(statement))


def latest_relevant_evidence(db: Session, expectation_id: UUID, metric: str | None) -> list[Evidence]:
    """Bound evaluator input without truncating before metric selection."""
    statement=select(Evidence).where(Evidence.expectation_id==expectation_id)
    if metric is not None:
        statement=statement.where(Evidence.metric==metric)
    statement=statement.order_by(Evidence.observed_at.desc(),Evidence.created_at.desc(),Evidence.id.desc()).limit(1)
    return list(db.scalars(statement))
