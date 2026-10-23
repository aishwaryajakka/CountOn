"""Bee context/simulation adapters, independent of the optional official CLI."""

import math
from typing import Any

from pydantic import AwareDatetime, TypeAdapter

from app.schemas.evidence import EvidenceCreate


def normalize_bee_event(event: dict[str, Any]) -> EvidenceCreate:
    """Retain main's explicit numeric simulator observations, never infer a promise outcome."""
    identity, metric, value = (
        event.get("event_id"),
        event.get("metric"),
        event.get("value"),
    )
    if (
        not isinstance(identity, str)
        or not identity.strip()
        or not isinstance(metric, str)
        or not metric.strip()
        or isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError(
            "A numeric simulated observation requires an identifier, metric and finite value"
        )
    return EvidenceCreate(
        external_event_id=identity,
        source="bee_simulator",
        metric=metric,
        value={"amount": value},
        unit=event.get("unit"),
        observed_at=TypeAdapter(AwareDatetime).validate_python(
            event.get("observed_at")
        ),
        confidence=event.get("confidence", 1),
        raw_data={"simulated": True, "provenance": "SIMULATED_BEE"},
    )
