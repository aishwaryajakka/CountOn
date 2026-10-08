"""Numeric edge cases exercise the pure evaluator without a database."""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from app.db.models import ComparisonType, Evidence, Expectation, ExpectationType
from app.evaluators.base import EvaluationResult
from app.evaluators.numeric import evaluate


@pytest.fixture
def expectation():
    return Expectation(
        claim="My next electricity bill will be lower", type=ExpectationType.numeric_comparison,
        metric="total_cost", comparison=ComparisonType.less_than,
        baseline=Decimal("142.10"), materiality_threshold=0.05,
    )


def observation(value, *, metric="total_cost", confidence=1.0, days=0):
    return Evidence(
        id=uuid4(), source="utility_bill", metric=metric, value=value,
        observed_at=datetime(2026, 10, 2, tzinfo=timezone.utc) + timedelta(days=days),
        confidence=confidence,
    )


@pytest.mark.parametrize("comparison,target,observed,result", [
    ("less_than", 142.10, 130, "MATCH"),
    ("less_than", 142.10, 162, "MISMATCH"),
    ("less_than_or_equal", 100, 100, "MATCH"),
    ("less_than_or_equal", 100, 106, "MISMATCH"),
    ("greater_than", 100, 110, "MATCH"),
    ("greater_than", 100, 90, "MISMATCH"),
    ("greater_than_or_equal", 100, 100, "MATCH"),
    ("greater_than_or_equal", 100, 90, "MISMATCH"),
    ("equal", 100, 104, "MATCH"),
    ("equal", 100, 105, "MATCH"),
    ("equal", 100, 106, "MISMATCH"),
    ("not_equal", 100, 104, "MISMATCH"),
    ("not_equal", 100, 106, "MATCH"),
    ("less_than", -100, -110, "MATCH"),
    ("less_than", -100, -90, "MISMATCH"),
    ("less_than", 100, 104, "MATCH"),
    ("less_than", 100, 105, "MISMATCH"),
    ("greater_than", 100, 96, "MATCH"),
    ("greater_than", 100, 95, "MISMATCH"),
    ("equal", 0, 0.05, "MATCH"),
    ("equal", 0, 0.051, "MISMATCH"),
    ("less_than", 0, -1, "MATCH"),
    ("less_than", 0, 0.01, "MATCH"),
    ("less_than", 0, 1, "MISMATCH"),
    ("not_equal", 0, 0.01, "MISMATCH"),
    ("not_equal", 0, 1, "MATCH"),
])
def test_comparisons(expectation, comparison, target, observed, result):
    expectation.comparison = ComparisonType(comparison)
    expectation.baseline = Decimal(str(target))
    output = evaluate(expectation, [observation({"amount": observed})])
    assert output.result == EvaluationResult(result)
    assert output.expected["target"] == target
    assert output.observed["value"] == observed
    assert output.reasoning["comparison"] == comparison
    assert output.reasoning["tolerance_kind"] == ("absolute" if target == 0 else "relative")


@pytest.mark.parametrize("value", [{"amount": 130}, {"value": 130}, {"percentage": -18}, 130, Decimal("130")])
def test_supported_numeric_shapes(expectation, value):
    assert evaluate(expectation, [observation(value)]).result == EvaluationResult.MATCH


@pytest.mark.parametrize("value", [
    {"amount": "130"}, {"value": True}, {"amount": None}, {}, {"other": 130},
    {"value": [130]}, {"amount": {"value": 130}}, "130", False,
    {"value": float("nan")}, {"amount": float("inf")},
])
def test_malformed_evidence_is_unknown(expectation, value):
    output = evaluate(expectation, [observation(value)])
    assert output.result == EvaluationResult.UNKNOWN
    assert output.reasoning["reason"] == "malformed_numeric_evidence"
    assert output.confidence == 0


@pytest.mark.parametrize("evidence", [[], [observation({"percentage": -18}, metric="energy_usage_change")]])
def test_missing_metric_evidence_is_unknown(expectation, evidence):
    output = evaluate(expectation, evidence)
    assert output.result == EvaluationResult.UNKNOWN
    assert output.reasoning["reason"] == "no_relevant_evidence"
    assert output.reasoning["metric"] == "total_cost"


def test_missing_target_is_unknown(expectation):
    expectation.baseline = None
    output = evaluate(expectation, [observation({"amount": 130})])
    assert output.result == EvaluationResult.UNKNOWN
    assert output.reasoning["reason"] == "target_unavailable"


def test_target_value_takes_precedence_even_when_zero(expectation):
    expectation.target_value = Decimal("0")
    output = evaluate(expectation, [observation({"amount": 130})])
    assert output.expected["target"] == 0
    assert output.result == EvaluationResult.MISMATCH


def test_latest_observation_wins_not_input_order(expectation):
    older = observation({"amount": 130})
    newer = observation({"amount": 162}, days=1)
    output = evaluate(expectation, [newer, older])
    assert output.result == EvaluationResult.MISMATCH
    assert output.observed["evidence_id"] == str(newer.id)


def test_malformed_latest_does_not_fall_back_to_stale_observation(expectation):
    output = evaluate(expectation, [observation({"amount": 130}), observation({"amount": "162"}, days=1)])
    assert output.result == EvaluationResult.UNKNOWN


@pytest.mark.parametrize("confidence", [0, -0.1, 1.1, float("nan"), None])
def test_unusable_confidence_is_unknown(expectation, confidence):
    output = evaluate(expectation, [observation({"amount": 130}, confidence=confidence)])
    assert output.result == EvaluationResult.UNKNOWN
    assert output.reasoning["reason"] == "unusable_evidence_confidence"


def test_nonzero_low_confidence_is_preserved(expectation):
    output = evaluate(expectation, [observation({"amount": 130}, confidence=0.2)])
    assert output.result == EvaluationResult.MATCH
    assert output.confidence == 0.2


def test_zero_threshold_requires_strict_directional_comparison(expectation):
    expectation.materiality_threshold = 0
    expectation.baseline = Decimal("100")
    assert evaluate(expectation, [observation({"amount": 100})]).result == EvaluationResult.MISMATCH
    assert evaluate(expectation, [observation({"amount": 99.999})]).result == EvaluationResult.MATCH


def test_reasoning_contains_comparison_and_no_causal_claim(expectation):
    output = evaluate(expectation, [
        observation({"amount": 162}), observation({"percentage": 22}, metric="rate_change"),
    ])
    assert output.reasoning == {
        "metric": "total_cost", "comparison": "less_than", "target": 142.10,
        "observed": 162.0, "materiality_threshold": 0.05,
        "reason": "observed_value_failed_comparison", "tolerance_kind": "relative",
    }


def test_late_arrival_does_not_override_newer_observation(expectation):
    older_observation = observation({"amount": 130})
    older_observation.created_at = datetime(2026, 10, 5, tzinfo=timezone.utc)
    newer_observation = observation({"amount": 162}, days=1)
    newer_observation.created_at = datetime(2026, 10, 3, tzinfo=timezone.utc)
    output = evaluate(expectation, [older_observation, newer_observation])
    assert output.result == EvaluationResult.MISMATCH
    assert output.observed["evidence_id"] == str(newer_observation.id)
