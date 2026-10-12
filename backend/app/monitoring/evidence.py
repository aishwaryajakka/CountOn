"""Conservative monitoring policy; AI never evaluates or resolves conflicting facts."""

import hashlib
import json
from datetime import datetime, timedelta
from decimal import Decimal
from math import isfinite

from sqlalchemy import or_, select
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
    binding_override=None,
) -> tuple[EvaluationOutput, str]:
    from app.monitoring.sources import context

    if binding_override is None and provider_identity is None:
        from app.monitoring.correlation import evaluate_sources
        from app.monitoring.sources import bindings

        selected = bindings(db, expectation)
        if len(selected) > 1:
            return evaluate_sources(
                db,
                expectation,
                selected,
                now=now,
                max_age=max_age,
                window_start=window_start,
            )

    source_identity, source_reason = (
        (None, None)
        if provider_identity
        else context(db, expectation, now, max_age, binding_override=binding_override)
    )
    query = select(Evidence).where(Evidence.expectation_id == expectation.id)
    if source_identity:
        query = query.where(Evidence.raw_data.contains(source_identity))
        from app.db.models import ProviderSourceEvent
        from app.monitoring.sources import bindings

        selected = bindings(db, expectation)
        if binding_override is not None:
            selected = [b for b in selected if b.id == binding_override.id]
        query = query.where(
            or_(
                Evidence.raw_data.contains({"absence_verified": True}),
                select(ProviderSourceEvent.id)
                .where(
                    ProviderSourceEvent.sync_id == selected[0].sync_id,
                    ProviderSourceEvent.external_id
                    == Evidence.raw_data["source_event_id"].astext,
                    ProviderSourceEvent.version
                    == Evidence.raw_data["source_version"].astext,
                )
                .exists(),
            )
        )
    if provider_identity:
        query = query.where(Evidence.raw_data.contains(provider_identity))
    if expectation.metric:
        query = query.where(Evidence.metric == expectation.metric)
    if expectation.evidence_sources:
        query = query.where(Evidence.source.in_(expectation.evidence_sources))
    start = max(expectation.created_at, window_start or expectation.created_at)
    query = query.where(Evidence.observed_at >= start)
    # Read the latest timestamp first; inspect ALL ties, bounded conservatively.
    latest = None
    if source_identity and expectation.metric == "reply_received":
        positive = query.where(Evidence.value.contains({"value": True}))
        latest = db.scalar(
            positive.order_by(Evidence.observed_at, Evidence.id).limit(1)
        )
        if latest:
            query = positive
    latest = latest or db.scalar(
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
    from app.monitoring.sources import current_calendar_fact, grounded_provider_fact

    fresh_calendar = bool(
        latest
        and source_identity
        and not source_reason
        and current_calendar_fact(db, expectation, latest)
    )
    reason = None
    if latest is None:
        reason = (
            "incomplete_mailbox_coverage"
            if (
                source_identity
                and expectation.metric == "reply_received"
                and expectation.deadline
                and now >= expectation.deadline
            )
            else "no_relevant_evidence"
        )
    elif latest.observed_at > now:
        reason = "future_evidence"
    elif source_identity and any(
        not row.raw_data.get("absence_verified")
        and not grounded_provider_fact(db, expectation, row)
        for row in peers
    ):
        reason = "provider_evidence_not_grounded"
    elif latest.observed_at < now - timedelta(seconds=max_age) and not fresh_calendar:
        reason = "stale_evidence"
    elif (
        expectation.deadline
        and expectation.type
        in (ExpectationType.numeric_comparison, ExpectationType.boolean)
        and expectation.metric
        not in ("reply_received", "delivery_reported", "package_delivery")
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
    elif latest is not None and latest.raw_data.get("absence_verified") is True:
        # Only the trusted synchronizer creates these records. Verify current
        # coverage again: stale/disconnected coverage cannot prove absence.
        from app.db.models import ProviderSyncState
        from app.monitoring.sources import bindings

        selected = bindings(db, expectation)
        sync = (
            db.get(ProviderSyncState, selected[0].sync_id)
            if len(selected) == 1
            else None
        )
        from app.monitoring.sources import absence_still_current, verify_absence

        covered = bool(
            verify_absence(
                latest, expectation, selected[0] if len(selected) == 1 else None
            )
            and expectation.metric == "reply_received"
            and expectation.deadline
            and now >= expectation.deadline
            and sync
            and sync.coverage_start_at
            and sync.coverage_start_at <= start
            and sync.coverage_through_at
            and sync.coverage_through_at >= expectation.deadline
            and not source_reason
            and absence_still_current(db, expectation, selected[0])
        )
        output = EvaluationOutput(
            EvaluationResult.MISMATCH if covered else EvaluationResult.UNKNOWN,
            expected={**expected, "deadline": str(expectation.deadline)},
            observed={"value": False, "evidence_id": str(latest.id)},
            confidence=latest.confidence if covered else 0,
            reasoning={
                "reason": "reply_absent_after_covered_deadline"
                if covered
                else "incomplete_mailbox_coverage"
            },
        )
    elif (
        expectation.metric == "reply_received"
        and latest is not None
        and latest.value.get("value") is False
    ):
        output = EvaluationOutput(
            EvaluationResult.UNKNOWN,
            expected=expected,
            confidence=0,
            reasoning={"reason": "reply_absence_not_verified"},
        )
    elif expectation.type == ExpectationType.numeric_comparison:
        output = numeric.evaluate(expectation, peers)
    elif (
        expectation.metric
        in ("reply_received", "delivery_reported", "package_delivery")
        and expectation.deadline
        and latest is not None
        and latest.value.get("value") is True
    ):
        on_time = latest.observed_at <= expectation.deadline
        reply_covered = True
        if not on_time and expectation.metric == "reply_received":
            from app.db.models import ProviderSyncState
            from app.monitoring.sources import absence_still_current, bindings

            selected = bindings(db, expectation)
            sync = (
                db.get(ProviderSyncState, selected[0].sync_id)
                if len(selected) == 1
                else None
            )
            reply_covered = bool(
                sync
                and sync.coverage_start_at
                and sync.coverage_start_at <= start
                and sync.coverage_through_at
                and sync.coverage_through_at >= expectation.deadline
                and absence_still_current(
                    db, expectation, selected[0], before_deadline_only=True
                )
            )
        output = EvaluationOutput(
            EvaluationResult.MATCH
            if on_time
            else EvaluationResult.MISMATCH
            if reply_covered
            else EvaluationResult.UNKNOWN,
            expected={**expected, "deadline": expectation.deadline.isoformat()},
            observed={"value": True, "evidence_id": str(latest.id)},
            confidence=latest.confidence if reply_covered else 0,
            reasoning={
                "reason": "event_observed_on_time"
                if on_time
                else "event_observed_after_deadline"
                if reply_covered
                else "incomplete_mailbox_coverage"
            },
        )
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
    if source_reason:
        output = EvaluationOutput(
            EvaluationResult.UNKNOWN,
            expected=expected,
            confidence=0,
            reasoning={"reason": source_reason},
        )
    output.reasoning.update(
        evidence_ids=ids,
        monitoring=True,
        checked_at=now.isoformat(),
        window_start=start.isoformat(),
        max_evidence_age_seconds=max_age,
        calendar_state_revalidated=fresh_calendar,
    )
    from app.core.observability import record

    record(
        "monitoring_source_outcomes" if binding_override else "monitoring_outcomes",
        output.result.value,
    )
    if output.result == EvaluationResult.UNKNOWN:
        record(
            "monitoring_source_unknown_reasons"
            if binding_override
            else "monitoring_unknown_reasons",
            output.reasoning.get("reason", "unsupported"),
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
