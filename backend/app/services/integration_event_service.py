"""Ingest simulated Bee events as CountOn evidence."""

from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from app.integrations.bee import normalize_bee_event
from app.services import evidence_service


def ingest_bee_event(
    db: Session,
    expectation_id: UUID,
    user_id: UUID,
    event: dict[str, Any],
):
    """Normalize a Bee event and save it as evidence."""
    payload = normalize_bee_event(event)

    return evidence_service.add_evidence(
        db=db,
        expectation_id=expectation_id,
        payload=payload,
        user_id=user_id,
    )