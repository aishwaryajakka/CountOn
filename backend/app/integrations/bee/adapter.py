"""Bee adapter: turns raw Bee wearable conversations and context events into CountOn EvidenceCreate."""

from datetime import datetime, timezone
from typing import Any

from pydantic import AwareDatetime, TypeAdapter, ValidationError

from app.schemas.evidence import EvidenceCreate

_parse_time = TypeAdapter(AwareDatetime)

SUPPORTED_BEE_TYPES = {"conversation", "note", "commitment", "mention", "transcript"}


def _infer_confirmation(raw: dict[str, Any]) -> bool | None:
    """Infer confirmation status from explicit keys or summary text."""
    if "confirmed" in raw:
        return bool(raw["confirmed"])
    if "value" in raw and isinstance(raw["value"], bool):
        return raw["value"]

    summary = str(raw.get("summary", "")).lower()
    if not summary:
        return None

    # Check for cancellation / rescheduling keywords
    if any(k in summary for k in ["cancelled", "canceled", "rescheduled", "cannot make it", "won't make it", "emergency", "postponed"]):
        return False
    # Check for confirmation keywords
    if any(k in summary for k in ["confirmed", "will come", "on track", "arriving", "booked", "scheduled"]):
        return True

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
        except (ValueError, TypeError, ValidationError):
            observed_at = datetime.now(timezone.utc)
    else:
        observed_at = datetime.now(timezone.utc)

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
        external_event_id=str(raw.get("id") or raw.get("event_id") or ""),
        source="bee",
        metric=metric,
        value=val_dict,
        observed_at=observed_at,
        confidence=confidence,
        raw_data=raw,
    )