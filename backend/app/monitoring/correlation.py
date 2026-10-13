"""Stable-identifier correlation only; no semantic matching or model verdicts."""

from datetime import datetime
from uuid import UUID

from app.core.observability import record
from app.db.models import Evidence
from app.evaluators.base import EvaluationOutput, EvaluationResult
from app.integrations.normalization import version
from app.schemas.provider_sync import SourceRule


def association(rules: list[SourceRule]) -> str | None:
    if not 1 < len(rules) <= 4:
        return None
    if all(r.kind == "order" and r.order_id == rules[0].order_id for r in rules):
        return "order"
    if (
        all(r.kind in ("calendar", "commitment") for r in rules)
        and rules[0].calendar_uid
        and all(r.calendar_uid == rules[0].calendar_uid for r in rules)
        and all(r.occurrence_start == rules[0].occurrence_start for r in rules)
        and all(r.expected_start == rules[0].expected_start for r in rules)
    ):
        return "calendar"
    return None


def evaluate_sources(db, expectation, bindings, **kwargs):
    from app.monitoring.evidence import evaluate

    rules = [SourceRule.model_validate(b.rule) for b in bindings]
    kind = association(rules)
    outputs, fingerprints = [], []
    reason = "ambiguous_sources"
    chosen = []
    if kind:
        for binding in bindings:
            output, fingerprint = evaluate(
                db, expectation, binding_override=binding, **kwargs
            )
            outputs.append(output)
            fingerprints.append(fingerprint)
        # A lost/expired source is not evidence that other records are correct.
        if any(o.result == EvaluationResult.UNKNOWN for o in outputs):
            reason = "incomplete_correlated_evidence"
        else:
            ids = [o.reasoning.get("evidence_ids", []) for o in outputs]
            rows = [
                db.get(Evidence, UUID(identities[0])) if identities else None
                for identities in ids
            ]
            if not all(rows):
                reason = "incomplete_correlated_evidence"
            elif kind == "order":
                # Compare current reports from every explicitly selected source.
                # Current reports from independent accounts cannot resolve a
                # material contradiction by choosing the later alleged arrival.
                chosen = list(range(len(outputs)))
            else:
                calendars = [i for i, r in enumerate(rules) if r.kind == "calendar"]
                chosen = calendars or list(range(len(outputs)))
                # A newer contradictory email cannot be silently ignored while
                # waiting for its authoritative calendar to reconcile.
                if calendars:
                    modified = []
                    for i in calendars:
                        value = rows[i].raw_data.get("source_timestamp")
                        modified.append(
                            datetime.fromisoformat(value)
                            if value
                            else rows[i].observed_at
                        )
                    for i in range(len(outputs)):
                        if (
                            i not in calendars
                            and rows[i].observed_at > max(modified)
                            and outputs[i].result != outputs[calendars[0]].result
                        ):
                            chosen.append(i)
            if chosen:
                reason = (
                    None
                    if len({outputs[i].result for i in chosen}) == 1
                    else "conflicting_evidence"
                )
                if reason is None and kind == "order":
                    arrivals = {rows[i].observed_at for i in chosen}
                    if len(arrivals) > 1:
                        reason = "conflicting_evidence"
                if (
                    reason is None
                    and kind == "calendar"
                    and expectation.metric == "event_unchanged"
                ):
                    states = {
                        (
                            bool(r.raw_data.get("correlation", {}).get("cancelled")),
                            None
                            if r.raw_data.get("correlation", {}).get("cancelled")
                            else r.raw_data.get("correlation", {}).get("start"),
                        )
                        for i, r in enumerate(rows)
                        if i in chosen and rules[i].kind == "calendar"
                    }
                    if len(states) > 1:
                        reason = "conflicting_evidence"
    evidence_ids = sorted(
        {identity for o in outputs for identity in o.reasoning.get("evidence_ids", [])}
    )
    metadata = {
        "monitoring": True,
        "reason": reason or "correlated_sources_agree",
        "evidence_ids": evidence_ids,
        "binding_ids": sorted(str(b.id) for b in bindings),
        "association": kind,
        "source_results": [
            {
                "binding_id": str(binding.id),
                "result": output.result.value,
                "reason": output.reasoning.get("reason"),
            }
            for binding, output in zip(bindings, outputs, strict=False)
        ],
        "checked_at": kwargs["now"].isoformat(),
        "policy_version": "stable_sources_v2",
        "authoritative_evidence_ids": [
            identity
            for i in chosen
            for identity in outputs[i].reasoning.get("evidence_ids", [])
        ],
    }
    if reason:
        result = EvaluationOutput(
            EvaluationResult.UNKNOWN,
            expected={"metric": expectation.metric},
            confidence=0,
            reasoning=metadata,
        )
    else:
        selected = outputs[chosen[0]]
        metadata["primary_reason"] = selected.reasoning.get("reason")
        result = EvaluationOutput(
            selected.result,
            expected=selected.expected,
            observed=selected.observed,
            confidence=min(outputs[i].confidence for i in chosen),
            reasoning=metadata,
        )
    record("source_correlations", reason or "agreed")
    record("monitoring_outcomes", result.result.value)
    if result.result == EvaluationResult.UNKNOWN:
        record("monitoring_unknown_reasons", reason)
    return result, version(
        {
            "policy": "stable_sources_v2",
            "children": sorted(fingerprints),
            "rules": [r.model_dump(mode="json") for r in rules],
            "result": result.result.value,
            "reason": reason,
        }
    )
