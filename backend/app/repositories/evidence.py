"""Evidence database operations; ordering is observation time ascending."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Evidence, Evaluation
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


def investigation_evidence(db: Session, expectation_id: UUID, evaluation: Evaluation, max_records: int = 12) -> list[Evidence]:
    """Bound historical reads after service ownership checks; never mutate evidence.

    Return pinned measurement, same-time conflicts, and latest contributor candidates.
    One extra candidate per metric allows the investigator to disclose truncation.
    """
    from app.ai.investigation_evidence import CONTRIBUTORS
    metric = evaluation.expected.get("metric") or evaluation.observed.get("metric")
    try:
        pinned_id = UUID(evaluation.observed.get("evidence_id", ""))
    except (ValueError, TypeError, AttributeError):
        pinned_id = None
    base = select(Evidence).where(Evidence.expectation_id == expectation_id,
                                  Evidence.created_at <= evaluation.created_at)
    primary = db.scalar(base.where(Evidence.id == pinned_id)) if pinned_id else None
    rows = [primary] if primary is not None else []
    if primary is not None:
        peers = base.where(Evidence.metric == metric, Evidence.observed_at == primary.observed_at,
                           Evidence.id != primary.id)
        rows.extend(db.scalars(peers.order_by(Evidence.created_at.desc(), Evidence.id.desc()).limit(max_records + 1)))
    elif pinned_id is None:
        # Legacy snapshot: mirror latest evaluator semantics within the as-of window.
        rows.extend(db.scalars(base.where(Evidence.metric == metric).order_by(
            Evidence.observed_at.desc(), Evidence.created_at.desc(), Evidence.id.desc()).limit(max_records + 1)))
    for contributor in CONTRIBUTORS.get(metric, ()):
        statement = base.where(Evidence.metric == contributor)
        if primary is not None:
            statement = statement.where(Evidence.observed_at <= primary.observed_at)
        rows.extend(db.scalars(statement.order_by(Evidence.observed_at.desc(), Evidence.created_at.desc(), Evidence.id.desc()).limit(max_records + 1)))
    return rows
