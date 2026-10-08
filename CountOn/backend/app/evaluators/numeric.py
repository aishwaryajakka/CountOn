"""Deterministic numeric comparisons using the latest metric observation.

Tolerance is relative to abs(target). For zero targets it is an absolute
amount in the metric's units. Equality includes the tolerance boundary;
directional failures are tolerated only strictly below the threshold.
Numeric strings and booleans are never coerced to numbers.
"""

from decimal import Decimal
from math import isfinite
from typing import Any

from app.db.models.expectation import ComparisonType, Expectation
from app.db.models.evidence import Evidence
from app.evaluators.base import EvaluationOutput, EvaluationResult, latest_evidence


def extract_numeric(value: Any) -> Decimal | None:
    if isinstance(value, dict):
        for key in ("amount", "value", "percentage"):
            if key in value:
                return extract_numeric(value[key]) if not isinstance(value[key], dict) else None
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return None
    number = Decimal(str(value))
    # Values must be both finite and representable in persisted JSON responses.
    try:
        return number if number.is_finite() and isfinite(float(number)) else None
    except (OverflowError, ValueError):
        return None


def evaluate(expectation: Expectation, evidence: list[Evidence]) -> EvaluationOutput:
    target = extract_numeric(
        expectation.target_value if expectation.target_value is not None else expectation.baseline
    )
    comparison = expectation.comparison
    expected = {
        "metric": expectation.metric,
        "comparison": comparison.value if comparison is not None else None,
        "target": float(target) if target is not None else None,
    }
    reasoning = dict(expected, materiality_threshold=expectation.materiality_threshold)

    def unknown(reason: str, observed: dict[str, Any] | None = None) -> EvaluationOutput:
        return EvaluationOutput(
            result=EvaluationResult.UNKNOWN, expected=expected, observed=observed or {},
            confidence=0.0, reasoning=dict(reasoning, reason=reason),
        )

    if target is None:
        return unknown("target_unavailable")
    if not expectation.metric or comparison is None:
        return unknown("invalid_numeric_expectation")
    item = latest_evidence(evidence, expectation.metric)
    if item is None:
        return unknown("no_relevant_evidence")
    observed = {"metric": expectation.metric, "evidence_id": str(item.id)}
    amount = extract_numeric(item.value)
    if amount is None:
        return unknown("malformed_numeric_evidence", observed)
    observed["value"] = float(amount)
    if item.confidence is None or not isfinite(item.confidence) or not 0 < item.confidence <= 1:
        return unknown("unusable_evidence_confidence", observed)
    threshold = extract_numeric(expectation.materiality_threshold)
    if threshold is None or not 0 <= threshold <= 1:
        return unknown("invalid_materiality_threshold", observed)
    difference = abs(amount - target)
    distance = difference / abs(target) if target != 0 else difference
    comparisons = {
        ComparisonType.less_than: amount < target,
        ComparisonType.less_than_or_equal: amount <= target,
        ComparisonType.greater_than: amount > target,
        ComparisonType.greater_than_or_equal: amount >= target,
        ComparisonType.equal: distance <= threshold,
        ComparisonType.not_equal: distance > threshold,
    }
    if comparison not in comparisons:
        return unknown("unsupported_comparison", observed)
    satisfied = comparisons[comparison]
    reason = "comparison_satisfied" if satisfied else "observed_value_failed_comparison"
    if not satisfied and comparison not in (ComparisonType.equal, ComparisonType.not_equal) and distance < threshold:
        satisfied = True
        reason = "deviation_below_materiality_threshold"
    reasoning.update(
        observed=float(amount), reason=reason,
        tolerance_kind="relative" if target != 0 else "absolute",
    )
    return EvaluationOutput(
        result=EvaluationResult.MATCH if satisfied else EvaluationResult.MISMATCH,
        expected=expected, observed=observed, confidence=item.confidence, reasoning=reasoning,
    )
