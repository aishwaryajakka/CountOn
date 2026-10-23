
"""Normalize billing and delivery emails into CountOn evidence."""

from datetime import datetime
import math
from typing import Any

from app.schemas.evidence import EvidenceCreate


def normalize_email_event(event: dict[str, Any]) -> EvidenceCreate:
    """Convert a parsed email event into normalized CountOn evidence."""

    event_id = event.get("message_id") or event.get("id")
    category = event.get("category")
    observed_at = event.get("received_at") or event.get("observed_at")

    if not isinstance(event_id, str) or not event_id.strip():
        raise ValueError("Email must include a non-empty message_id or id")

    if category not in {"billing", "delivery"}:
        raise ValueError("Email category must be billing or delivery")

    if not isinstance(observed_at, str) or not observed_at.strip():
        raise ValueError("Email must include received_at or observed_at")

    try:
        timestamp = datetime.fromisoformat(observed_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Email timestamp must be valid ISO 8601") from exc

    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Email timestamp must include a timezone")

    if category == "billing":
        metric = event.get("metric", "billing_amount")
        amount = event.get("amount")
        currency = event.get("currency")

        if not isinstance(metric, str) or not metric.strip():
            raise ValueError("Billing email metric must be a non-empty string")

        if (
            not isinstance(amount, (int, float))
            or isinstance(amount, bool)
            or not math.isfinite(amount)
        ):
            raise ValueError("Billing email amount must be a finite number")

        if currency is not None and not isinstance(currency, str):
            raise ValueError("Billing email currency must be a string")

        value = {"amount": amount}
        unit = currency

    else:
        status = event.get("delivery_status")

        if not isinstance(status, str) or not status.strip():
            raise ValueError(
                "Delivery email must include a non-empty delivery_status"
            )

        metric = "delivery_status"
        value = {"status": status.strip()}
        unit = None

    return EvidenceCreate(
        external_event_id=event_id.strip(),
        source="email",
        metric=metric.strip(),
        value=value,
        unit=unit,
        observed_at=timestamp,
        confidence=1.0,
        raw_data=event,
    )

