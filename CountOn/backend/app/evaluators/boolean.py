"""Minimal boolean assertions: actual True matches, actual False contradicts.

The current contract has no boolean target field, so expectations assert True.
Only literal booleans or booleans under the `value` key are supported.
"""

from math import isfinite

from app.db.models.expectation import Expectation
from app.db.models.evidence import Evidence
from app.evaluators.base import EvaluationOutput, EvaluationResult, latest_evidence


def evaluate(expectation: Expectation, evidence: list[Evidence]) -> EvaluationOutput:
    expected = {"metric": expectation.metric, "value": True}
    item = latest_evidence(evidence, expectation.metric)
    reason = "no_relevant_evidence"
    observed = {}
    if item is not None:
        value = item.value.get("value") if isinstance(item.value, dict) else item.value
        observed = {"metric": item.metric, "evidence_id": str(item.id)}
        if isinstance(value, bool):
            observed["value"] = value
            if item.confidence is not None and isfinite(item.confidence) and 0 < item.confidence <= 1:
                return EvaluationOutput(
                    result=EvaluationResult.MATCH if value else EvaluationResult.MISMATCH,
                    expected=expected, observed=observed, confidence=item.confidence,
                    reasoning={"reason": "comparison_satisfied" if value else "observed_value_failed_comparison"},
                )
            reason = "unusable_evidence_confidence"
        else:
            reason = "malformed_boolean_evidence"
    return EvaluationOutput(
        result=EvaluationResult.UNKNOWN, expected=expected, observed=observed,
        confidence=0.0, reasoning={"metric": expectation.metric, "reason": reason},
    )
