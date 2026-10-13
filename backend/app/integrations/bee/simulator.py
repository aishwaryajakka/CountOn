"""Bee context simulator: simulates wearable conversations, notes, and commitments without an iPhone or Bee CLI."""

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from app.integrations.bee.adapter import bee_event_to_evidence
from app.schemas.evidence import EvidenceCreate


def generate_bee_event(
    event_type: str = "conversation",
    speaker: str = "Sarah",
    summary: str = "Sarah confirmed she will send the updated design document tomorrow morning.",
    start_time: datetime | None = None,
    event_id: str | None = None,
    metric: str | None = None,
    confirmed: bool | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a realistic Bee wearable context event without an iPhone or physical device."""
    at = start_time or datetime.now(timezone.utc)
    ev_id = event_id or f"bee_sim_{uuid.uuid4().hex[:8]}"

    payload: dict[str, Any] = {
        "id": ev_id,
        "type": event_type,
        "start_time": at.isoformat(),
        "speaker": speaker,
        "summary": summary,
        "simulated": True,
        "confidence": 0.85,
    }
    if metric:
        payload["metric"] = metric
    if confirmed is not None:
        payload["confirmed"] = confirmed
    if extra:
        payload.update(extra)

    return payload


def simulate_plumber_confirmed(
    metric: str = "appointment_confirmed",
) -> tuple[dict[str, Any], EvidenceCreate]:
    """Simulate Bee capturing a conversation where the landlord confirms the plumber's arrival."""
    raw = generate_bee_event(
        event_type="conversation",
        speaker="Landlord",
        summary="Spoke with landlord: 'Plumber is confirmed for Friday at 10:00 AM.'",
        metric=metric,
        confirmed=True,
    )
    evidence = bee_event_to_evidence(raw)
    assert evidence is not None
    return raw, evidence


def simulate_plumber_cancelled(
    metric: str = "appointment_confirmed",
) -> tuple[dict[str, Any], EvidenceCreate]:
    """Simulate Bee capturing a conversation where the plumber is cancelled/rescheduled."""
    raw = generate_bee_event(
        event_type="conversation",
        speaker="Landlord",
        summary="Spoke with landlord: 'The plumber had an emergency and cannot come on Friday. We need to reschedule.'",
        metric=metric,
        confirmed=False,
    )
    evidence = bee_event_to_evidence(raw)
    assert evidence is not None
    return raw, evidence


def simulate_document_commitment() -> tuple[dict[str, Any], EvidenceCreate]:
    """Simulate Bee capturing a work commitment conversation."""
    raw = generate_bee_event(
        event_type="conversation",
        speaker="Sarah",
        summary="Sarah said she will send the design document tomorrow morning.",
        metric="conversation_mention",
    )
    evidence = bee_event_to_evidence(raw)
    assert evidence is not None
    return raw, evidence


if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "confirmed"
    if mode == "cancelled":
        raw, evidence = simulate_plumber_cancelled()
    elif mode == "commitment":
        raw, evidence = simulate_document_commitment()
    else:
        raw, evidence = simulate_plumber_confirmed()

    print("Simulated Raw Bee Event:")
    print(json.dumps(raw, indent=2))
    print("\nConverted CountOn Evidence:")
    print(evidence.model_dump_json(indent=2))
