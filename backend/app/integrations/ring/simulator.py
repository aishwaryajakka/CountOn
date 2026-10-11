"""Ring event simulator: simulates package deliveries, doorbell rings, and motion events without physical hardware."""

from datetime import datetime, timezone
import json
import uuid
from typing import Any

from app.integrations.ring.adapter import ring_event_to_evidence
from app.schemas.evidence import EvidenceCreate


def generate_ring_event(
    kind: str = "package_detected",
    device: str = "front_door",
    confidence: float = 0.95,
    timestamp: datetime | None = None,
    event_id: str | None = None,
    metric: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Generate a realistic Ring event payload without physical hardware."""
    at = timestamp or datetime.now(timezone.utc)
    ev_id = event_id or f"ring_sim_{uuid.uuid4().hex[:8]}"

    payload: dict[str, Any] = {
        "event_id": ev_id,
        "kind": kind,
        "timestamp": at.isoformat(),
        "confidence": confidence,
        "device": device,
        "simulated": True,
    }
    if metric:
        payload["metric"] = metric
    if extra:
        payload.update(extra)

    return payload


def simulate_package_delivery(
    device: str = "front_door",
    confidence: float = 0.95,
    metric: str = "package_detected",
) -> tuple[dict[str, Any], EvidenceCreate]:
    """Simulate a successful package delivery on doorstep."""
    raw = generate_ring_event(
        kind="package_detected",
        device=device,
        confidence=confidence,
        metric=metric,
        extra={"description": f"Package detected by Ring camera at {device}"},
    )
    evidence = ring_event_to_evidence(raw)
    assert evidence is not None
    return raw, evidence


def simulate_package_missing(
    device: str = "front_door",
    confidence: float = 0.90,
    metric: str = "package_detected",
) -> tuple[dict[str, Any], EvidenceCreate]:
    """Simulate a missed delivery or package removed event."""
    raw = generate_ring_event(
        kind="package_not_detected",
        device=device,
        confidence=confidence,
        metric=metric,
        extra={"description": f"No package present at {device}"},
    )
    evidence = ring_event_to_evidence(raw)
    assert evidence is not None
    return raw, evidence


def simulate_doorbell_ring(
    device: str = "front_door",
    confidence: float = 1.0,
) -> tuple[dict[str, Any], EvidenceCreate]:
    """Simulate someone pressing the doorbell."""
    raw = generate_ring_event(
        kind="doorbell_ding",
        device=device,
        confidence=confidence,
        extra={"description": f"Doorbell button pressed at {device}"},
    )
    evidence = ring_event_to_evidence(raw)
    assert evidence is not None
    return raw, evidence


def simulate_motion(
    device: str = "front_door",
    confidence: float = 0.88,
) -> tuple[dict[str, Any], EvidenceCreate]:
    """Simulate motion detected in camera field of view."""
    raw = generate_ring_event(
        kind="motion_detected",
        device=device,
        confidence=confidence,
        extra={"description": f"Motion detected near {device}"},
    )
    evidence = ring_event_to_evidence(raw)
    assert evidence is not None
    return raw, evidence


if __name__ == "__main__":
    import sys
    kind = sys.argv[1] if len(sys.argv) > 1 else "package_detected"
    raw = generate_ring_event(kind=kind)
    evidence = ring_event_to_evidence(raw)
    print("Simulated Raw Ring Event:")
    print(json.dumps(raw, indent=2))
    print("\nConverted CountOn Evidence:")
    print(evidence.model_dump_json(indent=2) if evidence else "None")
