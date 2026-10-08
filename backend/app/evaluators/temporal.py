"""Temporal and event semantics are deferred; never infer a contradiction."""

from app.db.models.expectation import Expectation
from app.db.models.evidence import Evidence
from app.evaluators.base import EvaluationOutput, EvaluationResult


def evaluate(expectation: Expectation, evidence: list[Evidence]) -> EvaluationOutput:
    return EvaluationOutput(
        result=EvaluationResult.UNKNOWN, confidence=0.0,
        expected={"type": expectation.type.value},
        reasoning={"reason": "temporal_evaluation_not_implemented"},
    )
