"""Normalize simulated Bee wearable events into CountOn evidence."""

import math

"""Normalize simulated Bee wearable events into CountOn evidence."""

from datetime import datetime
from typing import Any

from app.schemas.evidence import EvidenceCreate


def normalize_bee_event(event: dict[str, Any]) -> EvidenceCreate:
    """Convert a simulated Bee wearable event into normalized evidence."""

    event_id = event.get("event_id") or event.get("id")
    metric = event.get("metric")
    value = event.get("value")
    observed_at = event.get("observed_at")

    if not isinstance(event_id, str) or not event_id.strip():
        raise ValueError("Bee event must include a non-empty event_id or id")

    if not isinstance(metric, str) or not metric.strip():
        raise ValueError("Bee event must include a non-empty metric")

    if not isinstance(value, (int, float, bool, dict)):
        raise ValueError("Bee event value must be a number, boolean, or object")

    if isinstance(value, float) and not math.isfinite(value):
    if isinstance(value, float) and not __import__("math").isfinite(value):
        raise ValueError("Bee event value must be finite")

    if not isinstance(observed_at, str) or not observed_at.strip():
        raise ValueError("Bee event must include observed_at")

    try:
        timestamp = datetime.fromisoformat(
            observed_at.replace("Z", "+00:00")
        )
        timestamp = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Bee event timestamp must be valid ISO 8601") from exc

    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Bee event timestamp must include a timezone")

    unit = event.get("unit")
    if unit is not None and not isinstance(unit, str):
        raise ValueError("Bee event unit must be a string")

    confidence = event.get("confidence", 1.0)
    if (
        not isinstance(confidence, (int, float))
        or isinstance(confidence, bool)
        or not math.isfinite(confidence)
        or not 0 <= confidence <= 1
    ):
        raise ValueError("Bee event confidence must be a number between 0 and 1")
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        raise ValueError("Bee event confidence must be a number")

    evidence_value = value if isinstance(value, dict) else {"amount": value}

    return EvidenceCreate(
        external_event_id=event_id,
        source="bee",
        metric=metric,
        value=evidence_value,
        unit=unit,
        observed_at=timestamp,
        confidence=confidence,
        raw_data=event,
    )
    )
