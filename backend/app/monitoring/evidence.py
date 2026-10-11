"""Conservative monitoring policy; AI never evaluates or resolves conflicting facts."""

import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal
from math import isfinite

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Evidence, Expectation, ExpectationType
from app.evaluators import boolean, numeric
from app.evaluators.base import EvaluationOutput, EvaluationResult


def evaluate(
    db: Session,
    expectation: Expectation,
    *,
    now: datetime,
    max_age: int,
    window_start: datetime | None,
    provider_identity: dict | None = None,
) -> tuple[EvaluationOutput, str]:
    query = select(Evidence).where(Evidence.expectation_id == expectation.id)
    if provider_identity:
        query = query.where(Evidence.raw_data.contains(provider_identity))
    if expectation.metric:
        query = query.where(Evidence.metric == expectation.metric)
    if expectation.evidence_sources:
        query = query.where(Evidence.source.in_(expectation.evidence_sources))
    start = max(expectation.created_at, window_start or expectation.created_at)
    query = query.where(Evidence.observed_at >= start)
    # Read the latest timestamp first; inspect ALL ties, bounded conservatively.
    latest = db.scalar(
        query.order_by(Evidence.observed_at.desc(), Evidence.id.desc()).limit(1)
    )
    peers = (
        []
        if latest is None
        else list(
            db.scalars(
                query.where(Evidence.observed_at == latest.observed_at)
                .order_by(Evidence.id)
                .limit(101)
            )
        )
    )
    ids = [str(row.id) for row in peers]
    reason = None
    if latest is None:
        reason = "no_relevant_evidence"
    elif latest.observed_at > now:
        reason = "future_evidence"
    elif latest.observed_at < now - timedelta(seconds=max_age):
        reason = "stale_evidence"
    elif (
        expectation.deadline
        and expectation.type
        in (ExpectationType.numeric_comparison, ExpectationType.boolean)
        and latest.observed_at > expectation.deadline
    ):
        reason = "observation_after_deadline"
    elif len(peers) > 100:
        reason = "insufficient_evidence"
    elif any(
        not isfinite(row.confidence) or row.confidence <= 0 or row.confidence > 1
        for row in peers
    ):
        reason = "unusable_evidence_confidence"
    else:
        # Compare normalized facts; 162 and 162.0 are the same measurement.
        values: list[tuple[Decimal | bool | None, str | None]] = []
        for row in peers:
            if expectation.type == ExpectationType.numeric_comparison:
                value = numeric.extract_numeric(row.value)
                values.append((value, row.unit))
            else:
                value = row.value.get("value") if isinstance(row.value, dict) else None
                values.append((value if isinstance(value, bool) else None, row.unit))
        if any(value[0] is None for value in values):
            reason = "malformed_evidence"
        elif any(value != values[0] for value in values):
            reason = "conflicting_evidence"
    expected = {"metric": expectation.metric, "type": expectation.type.value}
    if reason:
        output = EvaluationOutput(
            EvaluationResult.UNKNOWN,
            expected=expected,
            confidence=0,
            reasoning={"reason": reason},
        )
    elif expectation.type == ExpectationType.numeric_comparison:
        output = numeric.evaluate(expectation, peers)
    elif expectation.type == ExpectationType.boolean:
        output = boolean.evaluate(expectation, peers)
    elif expectation.type in (ExpectationType.temporal, ExpectationType.event):
        # Only explicit positive event evidence establishes occurrence. Missing
        # evidence, or an assertion of absence, does not prove a missed deadline.
        if not expectation.metric or not expectation.deadline:
            output = EvaluationOutput(
                EvaluationResult.UNKNOWN,
                expected=expected,
                confidence=0,
                reasoning={"reason": "missing_temporal_criteria"},
            )
        elif latest is not None and latest.value.get("value") is True:
            result = (
                EvaluationResult.MATCH
                if latest.observed_at <= expectation.deadline
                else EvaluationResult.MISMATCH
            )
            output = EvaluationOutput(
                result,
                expected={**expected, "deadline": expectation.deadline.isoformat()},
                observed={
                    "metric": latest.metric,
                    "value": True,
                    "evidence_id": str(latest.id),
                },
                confidence=min(row.confidence for row in peers),
                reasoning={
                    "reason": "event_observed_on_time"
                    if result == EvaluationResult.MATCH
                    else "event_observed_after_deadline"
                },
            )
        else:
            output = EvaluationOutput(
                EvaluationResult.UNKNOWN,
                expected=expected,
                confidence=0,
                reasoning={"reason": "event_not_established"},
            )
    else:
        output = EvaluationOutput(
            EvaluationResult.UNKNOWN,
            expected=expected,
            confidence=0,
            reasoning={"reason": "unsupported_expectation_type"},
        )
    output.reasoning.update(
        evidence_ids=ids,
        monitoring=True,
        checked_at=now.isoformat(),
        window_start=start.isoformat(),
        max_evidence_age_seconds=max_age,
    )
    # Stable observation/criteria identity suppresses repeats across polling runs.
    fingerprint = hashlib.sha256(
        json.dumps(
            {
                "criteria": [
                    expectation.type.value,
                    expectation.metric,
                    str(expectation.baseline),
                    str(expectation.target_value),
                    str(expectation.comparison),
                    str(expectation.deadline),
                    expectation.materiality_threshold,
                ],
                "ids": ids,
                "result": output.result.value,
            },
            sort_keys=True,
            allow_nan=False,
        ).encode()
    ).hexdigest()
    return output, fingerprint
