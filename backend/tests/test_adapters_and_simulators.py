"""Unit tests for Ring and Bee adapters and simulators."""

import sys
from pathlib import Path
from uuid import uuid4

# Ensure backend directory is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.models.expectation import Expectation, ExpectationType
from app.db.models.evidence import Evidence
from app.evaluators.boolean import evaluate as evaluate_boolean
from app.evaluators.base import EvaluationResult
from app.integrations.ring.adapter import ring_event_to_evidence
from app.integrations.ring.simulator import (
    simulate_package_delivery,
    simulate_package_missing,
    simulate_doorbell_ring,
    simulate_motion,
    generate_ring_event,
)
from app.integrations.bee.adapter import bee_event_to_evidence
from app.integrations.bee.simulator import (
    simulate_plumber_confirmed,
    simulate_plumber_cancelled,
    simulate_document_commitment,
    generate_bee_event,
)


def _mock_expectation(metric: str) -> Expectation:
    return Expectation(
        id=uuid4(),
        user_id=uuid4(),
        claim="Testing expectation claim",
        type=ExpectationType.boolean,
        metric=metric,
        evidence_sources=["ring", "bee"],
    )


def _to_db_evidence(expectation_id, ev_create) -> Evidence:
    return Evidence(
        id=uuid4(),
        expectation_id=expectation_id,
        external_event_id=ev_create.external_event_id,
        source=ev_create.source,
        metric=ev_create.metric,
        value=ev_create.value,
        observed_at=ev_create.observed_at,
        confidence=ev_create.confidence,
        raw_data=ev_create.raw_data or {},
    )


def test_ring_package_delivery_matches():
    raw, ev_create = simulate_package_delivery(device="front_door", metric="package_detected")
    assert ev_create.source == "ring"
    assert ev_create.metric == "package_detected"
    assert ev_create.value["value"] is True
    assert ev_create.value["detected"] is True

    # Evaluate against boolean expectation
    expectation = _mock_expectation("package_detected")
    db_evidence = _to_db_evidence(expectation.id, ev_create)
    output = evaluate_boolean(expectation, [db_evidence])
    assert output.result == EvaluationResult.MATCH
    assert output.observed["value"] is True


def test_ring_package_missing_mismatches():
    raw, ev_create = simulate_package_missing(device="front_door", metric="package_detected")
    assert ev_create.source == "ring"
    assert ev_create.metric == "package_detected"
    assert ev_create.value["value"] is False

    expectation = _mock_expectation("package_detected")
    db_evidence = _to_db_evidence(expectation.id, ev_create)
    output = evaluate_boolean(expectation, [db_evidence])
    assert output.result == EvaluationResult.MISMATCH
    assert output.observed["value"] is False


def test_ring_doorbell_and_motion():
    _, ev_doorbell = simulate_doorbell_ring(device="porch")
    assert ev_doorbell.metric == "doorbell_pressed"
    assert ev_doorbell.value["event"] == "doorbell_ding"

    _, ev_motion = simulate_motion(device="driveway")
    assert ev_motion.metric == "motion_detected"
    assert ev_motion.value["event"] == "motion_detected"


def test_bee_conversation_plumber_confirmed():
    raw, ev_create = simulate_plumber_confirmed(metric="appointment_confirmed")
    assert ev_create.source == "bee"
    assert ev_create.metric == "appointment_confirmed"
    assert ev_create.value["value"] is True
    assert "Landlord" in ev_create.value["speaker"]

    expectation = _mock_expectation("appointment_confirmed")
    db_evidence = _to_db_evidence(expectation.id, ev_create)
    output = evaluate_boolean(expectation, [db_evidence])
    assert output.result == EvaluationResult.MATCH


def test_bee_conversation_plumber_cancelled():
    raw, ev_create = simulate_plumber_cancelled(metric="appointment_confirmed")
    assert ev_create.source == "bee"
    assert ev_create.metric == "appointment_confirmed"
    assert ev_create.value["value"] is False

    expectation = _mock_expectation("appointment_confirmed")
    db_evidence = _to_db_evidence(expectation.id, ev_create)
    output = evaluate_boolean(expectation, [db_evidence])
    assert output.result == EvaluationResult.MISMATCH


def test_bee_document_commitment():
    raw, ev_create = simulate_document_commitment()
    assert ev_create.source == "bee"
    assert ev_create.metric == "conversation_mention"
    assert "Sarah" in ev_create.value["speaker"]


if __name__ == "__main__":
    test_ring_package_delivery_matches()
    print("PASS: test_ring_package_delivery_matches")
    test_ring_package_missing_mismatches()
    print("PASS: test_ring_package_missing_mismatches")
    test_ring_doorbell_and_motion()
    print("PASS: test_ring_doorbell_and_motion")
    test_bee_conversation_plumber_confirmed()
    print("PASS: test_bee_conversation_plumber_confirmed")
    test_bee_conversation_plumber_cancelled()
    print("PASS: test_bee_conversation_plumber_cancelled")
    test_bee_document_commitment()
    print("PASS: test_bee_document_commitment")
    print("\nALL ADAPTER & SIMULATOR TESTS PASSED!")

