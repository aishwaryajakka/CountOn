"""Ring adapter: turns raw Ring events (doorbell, motion, package delivery) into CountOn EvidenceCreate."""

from datetime import timezone
from typing import Any

from pydantic import AwareDatetime, TypeAdapter

from app.schemas.evidence import EvidenceCreate

_parse_time = TypeAdapter(AwareDatetime)

# Supported Ring event kinds and their default metric mappings
PACKAGE_DETECTED_KINDS = {"package_detected", "package_delivered", "package_delivery", "package_present"}
PACKAGE_REMOVED_KINDS = {"package_not_detected", "package_removed", "package_missing"}
DOORBELL_KINDS = {"doorbell_ding", "doorbell", "ding", "button_press"}
MOTION_KINDS = {"motion_detected", "motion"}


def ring_event_to_evidence(raw: dict[str, Any]) -> EvidenceCreate | None:
    """Convert one raw Ring event (doorbell, motion, or package delivery) into CountOn's EvidenceCreate.

    Returns None if the raw payload is not a recognized Ring event.
    """
    kind = str(raw.get("kind", "")).lower()
    if not kind:
        return None

    # Resolve timestamp safely
    raw_time = raw.get("timestamp") or raw.get("created_at") or raw.get("time")
    if raw_time:
        try:
            observed_at = _parse_time.validate_python(raw_time).astimezone(timezone.utc)
        except ValueError:
            return None  # Invalid source time must not become fresh evidence.
    else:
        return None  # Missing source time cannot establish freshness.

    device = raw.get("device", "front_door")
    confidence = float(raw.get("confidence", 0.9))
    event_id = raw.get("event_id") or raw.get("id")
    raw_data = {**raw, "provenance": "SIMULATED_RING"} if raw.get("simulated") is True else raw

    if kind in PACKAGE_DETECTED_KINDS:
        metric = raw.get("metric", "package_detected")
        return EvidenceCreate(
            external_event_id=event_id,
            source="ring_simulator" if raw.get("simulated") is True else "ring",
            metric=metric,
            value={"value": True, "detected": True, "kind": kind, "device": device},
            observed_at=observed_at,
            confidence=confidence,
            raw_data=raw_data,
        )

    if kind in PACKAGE_REMOVED_KINDS:
        metric = raw.get("metric", "package_detected")
        return EvidenceCreate(
            external_event_id=event_id,
            source="ring_simulator" if raw.get("simulated") is True else "ring",
            metric=metric,
            value={"detected": False, "kind": kind, "device": device},
            observed_at=observed_at,
            confidence=confidence,
            raw_data=raw_data,
        )

    if kind in DOORBELL_KINDS:
        metric = raw.get("metric", "doorbell_pressed")
        return EvidenceCreate(
            external_event_id=event_id,
            source="ring_simulator" if raw.get("simulated") is True else "ring",
            metric=metric,
            value={"value": True, "event": "doorbell_ding", "kind": kind, "device": device},
            observed_at=observed_at,
            confidence=confidence,
            raw_data=raw_data,
        )

    if kind in MOTION_KINDS:
        metric = raw.get("metric", "motion_detected")
        return EvidenceCreate(
            external_event_id=event_id,
            source="ring_simulator" if raw.get("simulated") is True else "ring",
            metric=metric,
            value={"value": True, "event": "motion_detected", "kind": kind, "device": device},
            observed_at=observed_at,
            confidence=confidence,
            raw_data=raw_data,
        )

    return None
