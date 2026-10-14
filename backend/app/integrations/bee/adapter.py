"""Bee adapter: turns raw Bee wearable conversations and context events into CountOn EvidenceCreate."""

from datetime import timezone
from typing import Any

from pydantic import AwareDatetime, TypeAdapter

from app.schemas.evidence import EvidenceCreate

_parse_time = TypeAdapter(AwareDatetime)

SUPPORTED_BEE_TYPES = {"conversation", "note", "commitment", "mention", "transcript"}


def _infer_confirmation(raw: dict[str, Any]) -> bool | None:
    """Read only explicit boolean confirmation; prose remains context."""
    if isinstance(raw.get("confirmed"), bool):
        return raw["confirmed"]
    if isinstance(raw.get("value"), bool):
        return raw["value"]
    # Arbitrary conversation text is context, not a verified boolean fact.
    return None


def bee_event_to_evidence(raw: dict[str, Any]) -> EvidenceCreate | None:
    """Convert one raw Bee event (conversation, note, commitment) into CountOn's EvidenceCreate.

    Returns None if it isn't a recognized Bee context event.
    """
    event_type = str(raw.get("type", "")).lower()
    if event_type not in SUPPORTED_BEE_TYPES:
        return None

    # Resolve timestamp safely
    raw_time = raw.get("start_time") or raw.get("timestamp") or raw.get("created_at")
    if raw_time:
        try:
            observed_at = _parse_time.validate_python(raw_time).astimezone(timezone.utc)
        except (ValueError, TypeError):
            return None  # Invalid source time must not become fresh evidence.
    else:
        return None  # Missing source time cannot establish freshness.

    speaker = raw.get("speaker")
    summary = raw.get("summary") or raw.get("text", "")
    confidence = float(raw.get("confidence", 0.85))
    metric = raw.get("metric") or "conversation_mention"

    # Build structured value
    val_dict: dict[str, Any] = {
        "speaker": speaker,
        "summary": summary,
        "type": event_type,
    }

    inferred = _infer_confirmation(raw)
    if inferred is not None:
        val_dict["value"] = inferred

    return EvidenceCreate(
        external_event_id=raw.get("id") or raw.get("event_id") or None,
        source="bee_simulator" if raw.get("simulated") is True else "bee",
        metric=metric,
        value=val_dict,
        observed_at=observed_at,
        confidence=confidence,
        raw_data=raw,
    )
