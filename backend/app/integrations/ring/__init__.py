
"""Normalize Ring camera events into CountOn evidence."""

from datetime import datetime
from typing import Any

from app.schemas.evidence import EvidenceCreate


def normalize_ring_event(event: dict[str, Any]) -> EvidenceCreate:
    """Convert a Ring-style camera event into normalized evidence."""
    event_id = event.get("event_id") or event.get("id")
    event_type = event.get("event_type") or event.get("type")
    observed_at = event.get("observed_at") or event.get("created_at")

    if not isinstance(event_id, str) or not event_id.strip():
        raise ValueError("Ring event must include a non-empty event_id or id")

    if not isinstance(event_type, str) or not event_type.strip():
        raise ValueError("Ring event must include a non-empty event_type or type")

    if not isinstance(observed_at, str) or not observed_at.strip():
        raise ValueError("Ring event must include observed_at or created_at")

    try:
        timestamp = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Ring event timestamp must be valid ISO 8601") from exc

    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Ring event timestamp must include a timezone")

    return EvidenceCreate(
        external_event_id=event_id,
        source="ring",
        metric="camera_event",
        value={"event_type": event_type},
        observed_at=timestamp,
        confidence=1.0,
        raw_data=event,
    )
