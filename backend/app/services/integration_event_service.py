"""Compatibility manual-event entry points using canonical ownership and persistence.

These are user submissions/simulations, not verified provider callbacks. Real
Gmail/Graph sync still requires the existing encrypted grant and source binding.
"""

from app.core.exceptions import InvalidExpectationError
from app.integrations.bee import normalize_bee_event
from app.integrations.email import normalize_email_event
from app.integrations.ring import normalize_ring_event
from app.services import evaluation_service, evidence_service, expectation_service


def _ingest(db, expectation_id, user_id, event, normalize):
    expectation = expectation_service.get_expectation(db, expectation_id, user_id)
    payload = normalize(event)
    if payload.source not in expectation.evidence_sources:
        raise InvalidExpectationError(
            "Explicitly approve this manual/simulated source before ingestion"
        )
    saved = evidence_service.add_evidence(db, expectation_id, payload, user_id)
    evaluation_service.evaluate_expectation(
        db, expectation_id, user_id, idempotency_key=f"manual-event:{saved.id}"
    )
    return saved


def ingest_ring_event(db, expectation_id, user_id, event):
    return _ingest(db, expectation_id, user_id, event, normalize_ring_event)


def ingest_bee_event(db, expectation_id, user_id, event):
    return _ingest(db, expectation_id, user_id, event, normalize_bee_event)


def ingest_email_event(db, expectation_id, user_id, event):
    return _ingest(db, expectation_id, user_id, event, normalize_email_event)
