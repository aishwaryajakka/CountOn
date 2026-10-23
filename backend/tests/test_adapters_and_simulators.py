"""Unit tests for Ring and Bee adapters and simulators."""

import sys
from pathlib import Path
from uuid import uuid4

# Ensure backend directory is in path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db.models.evidence import Evidence
from app.db.models.expectation import ComparisonType, Expectation, ExpectationType
from app.evaluators.base import EvaluationResult
from app.evaluators.boolean import evaluate as evaluate_boolean
from app.evaluators.numeric import evaluate as evaluate_numeric
from app.integrations.bee.adapter import bee_event_to_evidence
from app.integrations.bee.simulator import (
    simulate_document_commitment,
    simulate_plumber_cancelled,
    simulate_plumber_confirmed,
)
from app.integrations.ring.adapter import ring_event_to_evidence
from app.integrations.ring.simulator import (
    simulate_doorbell_ring,
    simulate_motion,
    simulate_package_delivery,
    simulate_package_missing,
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
    _raw, ev_create = simulate_package_delivery(device="front_door", metric="package_detected")
    assert ev_create.source == "ring_simulator"
    assert ev_create.metric == "package_detected"
    assert ev_create.value["value"] is True
    assert ev_create.value["detected"] is True

    # Evaluate against boolean expectation
    expectation = _mock_expectation("package_detected")
    db_evidence = _to_db_evidence(expectation.id, ev_create)
    output = evaluate_boolean(expectation, [db_evidence])
    assert output.result == EvaluationResult.MATCH
    assert output.observed["value"] is True


def test_ring_package_missing_is_unknown():
    _raw, ev_create = simulate_package_missing(device="front_door", metric="package_detected")
    assert ev_create.source == "ring_simulator"
    assert ev_create.metric == "package_detected"
    assert "value" not in ev_create.value
    assert ev_create.value["detected"] is False

    expectation = _mock_expectation("package_detected")
    db_evidence = _to_db_evidence(expectation.id, ev_create)
    output = evaluate_boolean(expectation, [db_evidence])
    assert output.result == EvaluationResult.UNKNOWN
    assert "value" not in output.observed


def test_ring_doorbell_and_motion():
    _, ev_doorbell = simulate_doorbell_ring(device="porch")
    assert ev_doorbell.metric == "doorbell_pressed"
    assert ev_doorbell.value["event"] == "doorbell_ding"

    _, ev_motion = simulate_motion(device="driveway")
    assert ev_motion.metric == "motion_detected"
    assert ev_motion.value["event"] == "motion_detected"


def test_bee_conversation_plumber_confirmed():
    _raw, ev_create = simulate_plumber_confirmed(metric="appointment_confirmed")
    assert ev_create.source == "bee_simulator"
    assert ev_create.metric == "appointment_confirmed"
    assert ev_create.value["commitment_confirmed"] is True
    assert "value" not in ev_create.value
    assert "Landlord" in ev_create.value["speaker"]

    expectation = _mock_expectation("appointment_confirmed")
    db_evidence = _to_db_evidence(expectation.id, ev_create)
    output = evaluate_boolean(expectation, [db_evidence])
    assert output.result == EvaluationResult.UNKNOWN


def test_bee_conversation_plumber_cancelled():
    _raw, ev_create = simulate_plumber_cancelled(metric="appointment_confirmed")
    assert ev_create.source == "bee_simulator"
    assert ev_create.metric == "appointment_confirmed"
    assert ev_create.value["commitment_confirmed"] is False
    assert "value" not in ev_create.value

    expectation = _mock_expectation("appointment_confirmed")
    db_evidence = _to_db_evidence(expectation.id, ev_create)
    output = evaluate_boolean(expectation, [db_evidence])
    assert output.result == EvaluationResult.UNKNOWN


def test_bee_document_commitment():
    _raw, ev_create = simulate_document_commitment()
    assert ev_create.source == "bee_simulator"
    assert ev_create.metric == "conversation_mention"
    assert "Sarah" in ev_create.value["speaker"]


def test_simulator_adapters_never_retain_media_or_transcripts():
    ring = ring_event_to_evidence(
        {
            "simulated": True,
            "event_id": "ring-private-payload",
            "kind": "package_detected",
            "timestamp": "2026-10-13T12:00:00Z",
            "video_url": "https://private.invalid/video",
            "provider_payload": {"private": "content"},
        }
    )
    bee = bee_event_to_evidence(
        {
            "simulated": True,
            "id": "bee-private-payload",
            "type": "conversation",
            "start_time": "2026-10-13T12:00:00Z",
            "summary": "Only the approved summary",
            "transcript": "private full conversation",
            "audio_url": "https://private.invalid/audio",
        }
    )

    assert ring is not None and ring.raw_data == {
        "provenance": "SIMULATED_RING",
        "simulated": True,
    }
    assert bee is not None and bee.raw_data == {
        "provenance": "SIMULATED_BEE",
        "simulated": True,
        "category": "conversation",
    }


def test_utility_bill_within_tolerance_evaluates_to_match():
    expectation = Expectation(
        id=uuid4(),
        user_id=uuid4(),
        claim="My next electric bill should be lower.",
        type=ExpectationType.numeric_comparison,
        metric="total_cost",
        comparison=ComparisonType.less_than,
        baseline=142.10,
        materiality_threshold=0.05,
        evidence_sources=["utility_bill"],
    )
    db_evidence = Evidence(
        id=uuid4(),
        expectation_id=expectation.id,
        source="utility_bill",
        metric="total_cost",
        value={"amount": 148.00},
        confidence=1.0,
    )
    output = evaluate_numeric(expectation, [db_evidence])
    assert output.result == EvaluationResult.MATCH
    assert output.reasoning["reason"] == "deviation_below_materiality_threshold"
    assert output.observed["value"] == 148.00


def test_utility_bill_exceeding_tolerance_evaluates_to_mismatch():
    expectation = Expectation(
        id=uuid4(),
        user_id=uuid4(),
        claim="My next electric bill should be lower.",
        type=ExpectationType.numeric_comparison,
        metric="total_cost",
        comparison=ComparisonType.less_than,
        baseline=142.10,
        materiality_threshold=0.05,
        evidence_sources=["utility_bill"],
    )
    db_evidence = Evidence(
        id=uuid4(),
        expectation_id=expectation.id,
        source="utility_bill",
        metric="total_cost",
        value={"amount": 162.00},
        confidence=1.0,
    )
    output = evaluate_numeric(expectation, [db_evidence])
    assert output.result == EvaluationResult.MISMATCH
    assert output.reasoning["reason"] == "observed_value_failed_comparison"
    assert output.observed["value"] == 162.00


def test_utility_bill_below_baseline_evaluates_to_match():
    expectation = Expectation(
        id=uuid4(),
        user_id=uuid4(),
        claim="My next electric bill should be lower.",
        type=ExpectationType.numeric_comparison,
        metric="total_cost",
        comparison=ComparisonType.less_than,
        baseline=142.10,
        materiality_threshold=0.05,
        evidence_sources=["utility_bill"],
    )
    db_evidence = Evidence(
        id=uuid4(),
        expectation_id=expectation.id,
        source="utility_bill",
        metric="total_cost",
        value={"amount": 130.00},
        confidence=1.0,
    )
    output = evaluate_numeric(expectation, [db_evidence])
    assert output.result == EvaluationResult.MATCH
    assert output.reasoning["reason"] == "comparison_satisfied"


if __name__ == "__main__":
    test_ring_package_delivery_matches()
    print("PASS: test_ring_package_delivery_matches")
    test_ring_package_missing_is_unknown()
    print("PASS: test_ring_package_missing_is_unknown")
    test_ring_doorbell_and_motion()
    print("PASS: test_ring_doorbell_and_motion")
    test_bee_conversation_plumber_confirmed()
    print("PASS: test_bee_conversation_plumber_confirmed")
    test_bee_conversation_plumber_cancelled()
    print("PASS: test_bee_conversation_plumber_cancelled")
    test_bee_document_commitment()
    print("PASS: test_bee_document_commitment")
    print("\nALL ADAPTER & SIMULATOR TESTS PASSED!")
