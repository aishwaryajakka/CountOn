
"""Sync structured CountOn evidence from Outlook messages."""

import html
import json
import re
from datetime import datetime
from typing import Any
from uuid import UUID
from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from app.db.models import ExpectationStatus, ExpectationType
from app.schemas.evidence import EvidenceCreate
from app.services import (
    evidence_service,
    evaluation_service,
    expectation_service,
)
from app.services.microsoft_outlook_service import list_outlook_emails

MARKER = "COUNTON_EVIDENCE:"


def _extract_evidence(email: dict[str, Any]) -> dict[str, Any] | None:
    """Extract explicitly structured evidence from an email body."""
    body = email.get("body")
    content = body.get("content", "") if isinstance(body, dict) else ""

    if not isinstance(content, str):
        return None

    content = html.unescape(BeautifulSoup(content, "html.parser").get_text("\n"))

    match = re.search(
        re.escape(MARKER) + r"\s*(\{.*?\})",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )

    if not match:
        return None

    try:
        json_content = match.group(1).replace("\u00a0", " ")
        data = json.loads(json_content)

        if not isinstance(data, dict):
            return None

        metric = data.get("metric")
        value = data.get("value")
        observed_at = data.get("observed_at")
        unit = data.get("unit")

        if not isinstance(metric, str) or not metric.strip():
            return None

        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None

        if not isinstance(observed_at, str):
            return None

        timestamp = datetime.fromisoformat(
            observed_at.replace("Z", "+00:00")
        )

        # Evidence timestamps must include a timezone.
        if timestamp.tzinfo is None or timestamp.utcoffset() is None:
            return None

        if unit is not None and not isinstance(unit, str):
            return None

        return {
            "metric": metric.strip(),
            "value": value,
            "unit": unit,
            "observed_at": timestamp,
        }

    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def sync_outlook_emails(
    db: Session,
    *,
    connection_id: UUID,
    user_id: UUID,
    top: int = 25,
) -> dict[str, Any]:
    """Fetch Outlook emails and ingest matching structured evidence."""

    payload = list_outlook_emails(
        db,
        connection_id=connection_id,
        user_id=user_id,
        top=top,
    )

    emails = payload.get("value", [])

    if not isinstance(emails, list):
        raise ValueError(
            "Invalid Outlook response: expected an email list"
        )

    expectations = expectation_service.list_expectations(db, user_id)

    eligible = [
        expectation
        for expectation in expectations
        if expectation.status
        in (
            ExpectationStatus.monitoring,
            ExpectationStatus.unknown,
            ExpectationStatus.contradicted,
        )
        and expectation.type == ExpectationType.numeric_comparison
        and expectation.metric
    ]

    evidence_processed = 0
    evidence_skipped = 0
    processed = []

    for email in emails:
        if not isinstance(email, dict):
            evidence_skipped += 1
            processed.append(
                {
                    "message_id": None,
                    "evidence_processed": 0,
                    "reason": "Invalid email format",
                }
            )
            continue

        message_id = email.get("id")

        if not isinstance(message_id, str) or not message_id.strip():
            evidence_skipped += 1
            processed.append(
                {
                    "message_id": None,
                    "evidence_processed": 0,
                    "reason": "Email is missing a valid message ID",
                }
            )
            continue

        extracted = _extract_evidence(email)

        if extracted is None:
            evidence_skipped += 1
            processed.append(
                {
                    "message_id": message_id,
                    "evidence_processed": 0,
                    "reason": "No valid structured evidence found",
                }
            )
            continue

        matched = [
            expectation
            for expectation in eligible
            if expectation.metric == extracted["metric"]
        ]

        if not matched:
            evidence_skipped += 1
            processed.append(
                {
                    "message_id": message_id,
                    "evidence_processed": 0,
                    "reason": (
                        "No matching structured numeric expectation"
                    ),
                }
            )
            continue

        processed_for_email = 0

        for expectation in matched:
            evidence_payload = EvidenceCreate(
                external_event_id=message_id,
                source="microsoft_outlook",
                metric=extracted["metric"],
                value={"amount": extracted["value"]},
                unit=extracted["unit"],
                observed_at=extracted["observed_at"],
                confidence=1.0,
                raw_data={
                    "message_id": message_id,
                    "internet_message_id": email.get(
                        "internetMessageId"
                    ),
                    "subject": email.get("subject"),
                    "received_at": email.get("receivedDateTime"),
                },
            )

            # Existing evidence_service handles deduplication.
            evidence_service.add_evidence(
                db=db,
                expectation_id=expectation.id,
                payload=evidence_payload,
                user_id=user_id,
            )

            # Evaluate the expectation after evidence ingestion.
            evaluation_service.evaluate_expectation(
                db=db,
                expectation_id=expectation.id,
                user_id=user_id,
            )

            processed_for_email += 1
            evidence_processed += 1

        processed.append(
            {
                "message_id": message_id,
                "evidence_processed": processed_for_email,
                "reason": "Structured evidence processed",
            }
        )

    return {
        "emails_fetched": len(emails),
        "evidence_processed": evidence_processed,
        "emails_skipped": evidence_skipped,
        "messages": processed,
    }
