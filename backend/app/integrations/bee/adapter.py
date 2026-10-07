"""Bee adapter: turns a raw Bee conversation into CountOn's EvidenceCreate."""

from datetime import timezone

from pydantic import TypeAdapter, AwareDatetime

from app.schemas.evidence import EvidenceCreate

_parse_time = TypeAdapter(AwareDatetime)


def bee_event_to_evidence(raw: dict) -> EvidenceCreate | None:
    """Convert one raw Bee conversation. Returns None if it isn't one."""
    if raw.get("type") != "conversation":
        return None

    observed_at = _parse_time.validate_python(raw["start_time"]).astimezone(timezone.utc)

    return EvidenceCreate(
        external_event_id=raw.get("id"),
        source="bee",
        metric="conversation_mention",
        value={"speaker": raw.get("speaker"), "summary": raw.get("summary")},
        observed_at=observed_at,
        confidence=0.8,
        raw_data=raw,
    )