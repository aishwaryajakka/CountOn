"""Ingest Ring and Bee events as CountOn evidence."""

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session
from app.integrations.email import normalize_email_event
from app.integrations.bee import normalize_bee_event
from app.integrations.ring import normalize_ring_event
from app.schemas.evidence import EvidenceCreate
from app.services import evidence_service


def ingest_ring_event(
    db: Session,
    expectation_id: UUID,
    user_id: UUID,
    event: dict[str, Any],
) -> Any:
    """Normalize a Ring event and save it as evidence."""
    payload: EvidenceCreate = normalize_ring_event(event)

    return evidence_service.add_evidence(
        db=db,
        expectation_id=expectation_id,
        payload=payload,
        user_id=user_id,
    )


def ingest_bee_event(
    db: Session,
    expectation_id: UUID,
    user_id: UUID,
    event: dict[str, Any],
) -> Any:
    """Normalize a simulated Bee event and save it as evidence."""
    payload: EvidenceCreate = normalize_bee_event(event)

    return evidence_service.add_evidence(
        db=db,
        expectation_id=expectation_id,
        payload=payload,
        user_id=user_id,
    )


def ingest_email_event(
    db: Session,
    expectation_id: UUID,
    user_id: UUID,
    event: dict[str, Any],
) -> Any:
    """Normalize a parsed email event and save it as evidence."""
    payload: EvidenceCreate = normalize_email_event(event)

    return evidence_service.add_evidence(
        db=db,
        expectation_id=expectation_id,
        payload=payload,
        user_id=user_id,
    )
