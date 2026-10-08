"""Evaluation-anchored, ownership-checked minimization; no raw provider payloads."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from math import isfinite
from typing import TYPE_CHECKING, cast
from uuid import UUID

if TYPE_CHECKING:
    from app.db.models.evidence import Evidence

from app.db.models.expectation import ComparisonType, ExpectationType
from app.evaluators.base import EvaluationResult, latest_evidence
from app.evaluators.numeric import extract_numeric
from app.schemas.evaluation import EvaluationResponse
from app.schemas.evidence import EvidenceResponse
from app.schemas.expectation import ExpectationResponse
from app.schemas.investigation import ExpectedValue, InvestigationContext, ObservedValue

CONTRIBUTORS = {"total_cost": ("energy_usage_change", "rate_change")}
REASONS = {
    "observed_value_failed_comparison",
    "comparison_satisfied",
    "deviation_below_materiality_threshold",
}


class InvestigationInputError(Exception):
    def __init__(self) -> None:
        super().__init__(
            "Mismatch investigation requires a related, authorized MISMATCH evaluation"
        )


class InvestigationGroundingError(Exception):
    def __init__(self) -> None:
        super().__init__("Investigator output could not be grounded")


def safe_metric(value: object) -> str | None:
    return (
        value
        if isinstance(value, str) and re.fullmatch(r"[a-z][a-z0-9_]{0,99}", value)
        else None
    )


def atom(value: object) -> float | bool | None:
    if isinstance(value, bool):
        return value
    if isinstance(value, dict):
        boolean = value.get("value")
        if isinstance(boolean, bool):
            return boolean
    numeric = extract_numeric(value)
    return float(numeric) if numeric is not None else None


def same_value(left: float | bool | None, right: float | bool | None) -> bool:
    return isinstance(left, bool) == isinstance(right, bool) and left == right


def aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


@dataclass(frozen=True)
class SelectedEvidence:
    ref: str
    item: EvidenceResponse
    metric: str
    value: float | bool
    unit: str | None

    def public_fact(self) -> dict[str, object]:
        return {
            "ref": self.ref,
            "metric": self.metric,
            "value": self.value,
            "unit": self.unit,
        }


@dataclass(frozen=True)
class InvestigationFacts:
    expected: ExpectedValue
    observed: ObservedValue
    reason: str | None
    evidence: tuple[SelectedEvidence, ...]
    conflicts: bool
    truncated: bool
    uncorroborated: bool


def normalize(
    *,
    expectation: ExpectationResponse,
    evaluation: EvaluationResponse,
    evidence: Sequence[EvidenceResponse],
    context: InvestigationContext | None,
    max_evidence: int,
) -> InvestigationFacts:
    if (
        evaluation.result != EvaluationResult.MISMATCH
        or evaluation.expectation_id != expectation.id
    ):
        raise InvestigationInputError()
    if (
        context
        and context.authenticated_user_id is not None
        and context.authenticated_user_id != expectation.user_id
    ):
        raise InvestigationInputError()
    if not aware(evaluation.created_at) or any(
        item.expectation_id != expectation.id for item in evidence
    ):
        raise InvestigationInputError()
    metric = safe_metric(evaluation.expected.get("metric"))
    comparison_value = evaluation.expected.get("comparison")
    try:
        comparison = (
            ComparisonType(comparison_value) if comparison_value is not None else None
        )
    except (ValueError, TypeError):
        comparison = None
    target = atom(evaluation.expected.get("target", evaluation.expected.get("value")))
    observed = atom(evaluation.observed.get("value"))
    threshold = atom(evaluation.reasoning.get("materiality_threshold"))
    if isinstance(threshold, bool) or threshold is not None and not 0 <= threshold <= 1:
        threshold = None
    tolerance = evaluation.reasoning.get("tolerance_kind")
    expected = ExpectedValue(
        metric=metric,
        comparison=comparison,
        target=target,
        materiality_threshold=threshold,
        tolerance_kind=tolerance if tolerance in ("relative", "absolute") else None,
    )
    observed_value = ObservedValue(
        metric=safe_metric(evaluation.observed.get("metric")), value=observed
    )
    reason = evaluation.reasoning.get("reason")
    reason = reason if isinstance(reason, str) and reason in REASONS else None
    selection_metric = metric
    if metric is None and expectation.type == ExpectationType.boolean:
        selection_metric = observed_value.metric
    allowed = {selection_metric} | set(CONTRIBUTORS.get(metric or "", ()))
    candidates: list[EvidenceResponse] = []
    for item in evidence:
        if (
            item.metric not in allowed
            or not aware(item.created_at)
            or not aware(item.observed_at)
            or item.created_at > evaluation.created_at
        ):
            continue
        if not isfinite(item.confidence) or not 0 < item.confidence <= 1:
            continue
        if item.metric in CONTRIBUTORS.get(metric or "", ()):
            if "percentage" not in item.value or item.unit not in (
                None,
                "percent",
                "%",
            ):
                continue
            if not same_value(atom(item.value), atom(item.value["percentage"])):
                continue
        value = atom(item.value)
        if value is None or (
            item.metric in CONTRIBUTORS.get(metric or "", ())
            and isinstance(value, bool)
        ):
            continue
        candidates.append(item)
    # Duplicate IDs with differing contents are not usable provenance.
    identities: dict[UUID, EvidenceResponse] = {}
    for item in candidates:
        if item.id in identities and item != identities[item.id]:
            raise InvestigationInputError()
        identities[item.id] = item
    candidates = list(identities.values())
    pinned_value = evaluation.observed.get("evidence_id")
    try:
        pinned = UUID(pinned_value) if isinstance(pinned_value, str) else None
    except ValueError:
        pinned = None
    primary = next(
        (
            item
            for item in candidates
            if selection_metric is not None
            and item.id == pinned
            and item.metric == selection_metric
        ),
        None,
    )
    if pinned_value is None and selection_metric:
        # Reuse evaluator ordering only for older snapshots without a recorded ID.
        primary = cast(
            "EvidenceResponse | None",
            latest_evidence(cast("list[Evidence]", candidates), selection_metric),
        )
    if primary is not None and not same_value(atom(primary.value), observed):
        primary = None
    ordered: list[EvidenceResponse] = []
    conflicts = False
    if primary:
        ordered.append(primary)
        ties = sorted(
            (
                item
                for item in candidates
                if item.metric == selection_metric
                and item.observed_at == primary.observed_at
                and item.id != primary.id
            ),
            key=lambda item: (item.observed_at, item.created_at, str(item.id)),
            reverse=True,
        )
        for item in ties:
            if not same_value(atom(item.value), atom(primary.value)):
                conflicts = True
                ordered.append(item)
        for contribution_metric in CONTRIBUTORS.get(metric or "", ()):
            relevant = [
                item
                for item in candidates
                if item.metric == contribution_metric
                and item.observed_at <= primary.observed_at
            ]
            latest = cast(
                "EvidenceResponse | None",
                latest_evidence(cast("list[Evidence]", relevant), contribution_metric),
            )
            if latest:
                ordered.append(latest)
                for item in sorted(
                    relevant,
                    key=lambda item: (item.observed_at, item.created_at, str(item.id)),
                    reverse=True,
                ):
                    if (
                        item.id != latest.id
                        and item.observed_at == latest.observed_at
                        and not same_value(atom(item.value), atom(latest.value))
                    ):
                        conflicts = True
                        ordered.append(item)
    selected = []
    for index, item in enumerate(ordered[:max_evidence], 1):
        value = atom(item.value)
        assert value is not None and item.metric is not None
        unit = item.unit if item.unit in ("USD", "percent", "%", "kWh") else None
        selected.append(
            SelectedEvidence(
                ref=f"E{index}", item=item, metric=item.metric, value=value, unit=unit
            )
        )
    return InvestigationFacts(
        expected=expected,
        observed=observed_value,
        reason=reason,
        evidence=tuple(selected),
        conflicts=conflicts,
        truncated=len(ordered) > max_evidence,
        uncorroborated=primary is None,
    )
