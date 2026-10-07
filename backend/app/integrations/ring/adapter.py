"""Ring adapter: turns a raw Ring event into CountOn's EvidenceCreate."""

from datetime import timezone

from pydantic import TypeAdapter, AwareDatetime

from app.schemas.evidence import EvidenceCreate

_parse_time = TypeAdapter(AwareDatetime)


def ring_event_to_evidence(raw: dict) -> EvidenceCreate | None:
    """Convert one raw Ring event. Returns None if it isn't a package event."""
    if raw.get("kind") != "package_detected":
        return None

    observed_at = _parse_time.validate_python(raw["timestamp"]).astimezone(timezone.utc)

    return EvidenceCreate(
        external_event_id=raw.get("event_id"),
        source="ring",
        metric="package_detected",
        value={"detected": True},
        observed_at=observed_at,
        confidence=raw.get("confidence", 0.9),
        raw_data=raw,
    )