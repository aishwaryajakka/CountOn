"""Boolean values are strict; temporal and event evaluation remain unknown."""

from datetime import datetime, timezone

import pytest

from app.db.models import Evidence, Expectation, ExpectationType
from app.evaluators import boolean, temporal
from app.evaluators.base import EvaluationResult


@pytest.mark.parametrize("value,result", [
    ({"value": True}, "MATCH"), ({"value": False}, "MISMATCH"),
    (True, "MATCH"), (False, "MISMATCH"),
    ({"value": "true"}, "UNKNOWN"), ({"value": 1}, "UNKNOWN"),
    ({"value": "false"}, "UNKNOWN"), ({}, "UNKNOWN"),
])
def test_boolean(value, result):
    expectation = Expectation(type=ExpectationType.boolean, metric="delivered")
    evidence = Evidence(value=value, metric="delivered", confidence=1.0, observed_at=datetime.now(timezone.utc))
    assert boolean.evaluate(expectation, [evidence]).result == EvaluationResult(result)


def test_boolean_missing_evidence():
    expectation = Expectation(type=ExpectationType.boolean, metric="delivered")
    assert boolean.evaluate(expectation, []).result == EvaluationResult.UNKNOWN


def test_boolean_unrelated_evidence():
    expectation = Expectation(type=ExpectationType.boolean, metric="delivered")
    evidence = Evidence(value={"value": True}, metric="other", confidence=1.0, observed_at=datetime.now(timezone.utc))
    assert boolean.evaluate(expectation, [evidence]).result == EvaluationResult.UNKNOWN


@pytest.mark.parametrize("kind", [ExpectationType.temporal, ExpectationType.event])
def test_temporal_and_event_stubs(kind):
    output = temporal.evaluate(Expectation(type=kind), [])
    assert output.result == EvaluationResult.UNKNOWN
    assert output.reasoning["reason"] == "temporal_evaluation_not_implemented"
