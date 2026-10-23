"""Ring simulation adapters; no live hardware authority is implied."""

from typing import Any

from pydantic import AwareDatetime, TypeAdapter

from app.schemas.evidence import EvidenceCreate


def normalize_ring_event(event: dict[str, Any]) -> EvidenceCreate:
    """Compatibility for explicit manual camera observations from main."""
    identity = event.get("event_id") or event.get("id")
    kind = event.get("event_type") or event.get("type")
    if (
        not isinstance(identity, str)
        or not identity.strip()
        or not isinstance(kind, str)
        or not kind.strip()
    ):
        raise ValueError("A camera event requires an identifier and event type")
    return EvidenceCreate(
        external_event_id=identity,
        source="ring_simulator",
        metric="camera_event",
        value={"event_type": kind},
        observed_at=TypeAdapter(AwareDatetime).validate_python(
            event.get("observed_at") or event.get("created_at")
        ),
        confidence=1,
        raw_data={"simulated": True, "provenance": "SIMULATED_RING"},
    )
