"""Pure explanation of an immutable evaluation; no evaluation or database writes."""

import json
import logging
import time
from collections.abc import Sequence
from dataclasses import replace
from typing import Literal

from pydantic import ValidationError

from app.ai.bedrock_client import BedrockClient
from app.ai.exceptions import BedrockError
from app.ai.investigation_evidence import (
    InvestigationFacts,
    InvestigationGroundingError,
    normalize,
    same_value,
)
from app.ai.prompts import (
    MISMATCH_INVESTIGATOR_PROMPT_VERSION,
    mismatch_investigator_prompt,
)
from app.core.config import Settings, get_settings
from app.schemas.evaluation import EvaluationResponse
from app.schemas.evidence import EvidenceResponse
from app.schemas.expectation import ExpectationResponse
from app.schemas.investigation import (
    EvidenceReference,
    ExplanationFactor,
    FactorDraft,
    InvestigationContext,
    InvestigatorDraft,
    MismatchExplanation,
)

logger = logging.getLogger(__name__)
COMPARISONS = {
    "less_than": "<",
    "less_than_or_equal": "≤",
    "greater_than": ">",
    "greater_than_or_equal": "≥",
    "equal": "=",
    "not_equal": "≠",
}


def number(value: float | bool | None, *, currency: bool = False) -> str:
    if value is None:
        return "unavailable"
    if isinstance(value, bool):
        return str(value).lower()
    return f"${value:.2f}" if currency else format(value, ".15g")


def summary(facts: InvestigationFacts) -> str:
    expected = facts.expected
    currency = bool(facts.evidence and facts.evidence[0].unit == "USD")
    comparison = COMPARISONS.get(expected.comparison or "", "value")
    text = (
        f"CountOn recorded MISMATCH: expected {comparison} "
        f"{number(expected.target, currency=currency)}; observed "
        f"{number(facts.observed.value, currency=currency)}."
    )
    if expected.materiality_threshold is not None:
        threshold = expected.materiality_threshold
        label = (
            f"{number(threshold * 100)}% (relative)"
            if expected.tolerance_kind == "relative"
            else f"{number(threshold)} (absolute)"
            if expected.tolerance_kind == "absolute"
            else number(threshold)
        )
        text += f" Recorded materiality threshold: {label}."
    return text


def packet(facts: InvestigationFacts) -> str:
    return json.dumps(
        {
            "result": "MISMATCH",
            "expected": facts.expected.model_dump(mode="json"),
            "observed": facts.observed.model_dump(mode="json"),
            "evaluator_reason": facts.reason,
            "evidence": [item.public_fact() for item in facts.evidence],
            "conflicting_evidence": facts.conflicts,
        },
        separators=(",", ":"),
        allow_nan=False,
    )


def render_factor(draft: FactorDraft, facts: InvestigationFacts) -> ExplanationFactor:
    refs = {item.ref: item for item in facts.evidence}
    labels = draft.evidence_refs
    if (
        len(set(labels)) != len(labels)
        or set(draft.values) != set(labels)
        or any(label not in refs for label in labels)
    ):
        raise InvestigationGroundingError()
    items = [refs[label] for label in labels]
    if any(not same_value(draft.values[item.ref], item.value) for item in items):
        raise InvestigationGroundingError()
    kind = draft.kind
    strength: Literal["observation", "possible_contribution", "conflicting"] = (
        "observation"
    )
    if kind == "observed_measurement" and labels == ["E1"]:
        description = f"The recorded {items[0].metric} measurement was {number(items[0].value, currency=items[0].unit == 'USD')}."
    elif (
        kind in ("usage_change", "rate_change")
        and len(items) == 1
        and items[0].metric
        == ("energy_usage_change" if kind == "usage_change" else "rate_change")
    ):
        description = f"Reported {'usage' if kind == 'usage_change' else 'rate'} change: {number(items[0].value)}%."
    elif kind == "possible_rate_offset" and len(items) == 3 and not facts.conflicts:
        by_metric = {item.metric: item for item in items}
        usage, rate = by_metric.get("energy_usage_change"), by_metric.get("rate_change")
        if (
            "E1" not in labels
            or usage is None
            or rate is None
            or isinstance(usage.value, bool)
            or isinstance(rate.value, bool)
            or not usage.value < 0 < rate.value
            or facts.expected.metric != "total_cost"
            or facts.expected.comparison not in ("less_than", "less_than_or_equal")
            or not isinstance(facts.expected.target, float)
            or not isinstance(facts.observed.value, float)
            or not facts.observed.value > facts.expected.target
        ):
            raise InvestigationGroundingError()
        description = (
            f"Usage fell {number(-usage.value)}% while the rate rose {number(rate.value)}%. "
            "The higher rate could have contributed to the bill mismatch; these observations do not establish a net effect or cause."
        )
        strength = "possible_contribution"
    elif (
        kind == "conflicting_observations"
        and len(items) >= 2
        and facts.conflicts
        and len({item.metric for item in items}) == 1
        and len({item.item.observed_at for item in items}) == 1
        and any(not same_value(items[0].value, item.value) for item in items[1:])
    ):
        description = "Evidence reports conflicting values for the same metric and observation time; the cause cannot be resolved from these records."
        strength = "conflicting"
    else:
        raise InvestigationGroundingError()
    return ExplanationFactor(
        description=description, evidence_refs=labels, strength=strength
    )


def explanation(
    facts: InvestigationFacts, draft: InvestigatorDraft | None
) -> MismatchExplanation:
    factors = (
        [render_factor(item, facts) for item in draft.key_factors] if draft else []
    )
    if (
        draft
        and draft.summary_kind == "possible_contribution"
        and not any(item.strength == "possible_contribution" for item in factors)
    ):
        raise InvestigationGroundingError()
    text = summary(facts)
    caveats = [
        "These observations do not prove causality or that contributing measurements cover the same billing period."
    ]
    if not any(item.strength == "possible_contribution" for item in factors):
        text += " There isn't enough supporting evidence to explain what caused the mismatch."
    if facts.conflicts:
        text += " The available evidence is conflicting."
        caveats.append(
            "Evidence contains conflicting observations; no causal source was chosen. The recorded evaluation remains unchanged."
        )
    if facts.uncorroborated:
        caveats.append(
            "The evaluation's observed measurement could not be corroborated by the supplied evidence."
        )
    if facts.truncated:
        caveats.append("Only a bounded selection of relevant evidence was considered.")
    if facts.expected.target is None or facts.observed.value is None:
        caveats.append(
            "Some historical evaluation fields are unavailable; no replacement values were inferred."
        )
    supported = any(item.strength == "possible_contribution" for item in factors)
    # Conservative evidence-support indicator, not a model score or probability
    # that a proposed cause is true. Conflicts can never increase confidence.
    confidence = (
        0.5 * min(0.5, *(item.item.confidence for item in facts.evidence))
        if facts.conflicts and factors
        else min(0.5, *(item.item.confidence for item in facts.evidence))
        if supported
        else 0.0
    )
    return MismatchExplanation(
        summary=text,
        expected=facts.expected,
        observed=facts.observed,
        evaluator_reason=facts.reason,
        key_factors=factors,
        caveats=caveats,
        confidence_note="Confidence concerns the available supporting observations, not causal certainty or the deterministic evaluation result.",
        confidence=confidence,
        insufficient_evidence=not supported or facts.conflicts,
        evidence_refs=[
            EvidenceReference(ref=item.ref, evidence_id=item.item.id)
            for item in facts.evidence
        ],
        prompt_version=MISMATCH_INVESTIGATOR_PROMPT_VERSION,
        generation="bedrock" if draft else "deterministic",
    )


class BedrockMismatchInvestigator:
    def __init__(
        self, *, client: BedrockClient | None = None, settings: Settings | None = None
    ) -> None:
        self.settings = settings or get_settings()
        self.client = client or BedrockClient(settings=self.settings)
        self.owned = client is None

    def close(self) -> None:
        if self.owned:
            self.client.close()

    def investigate_mismatch(
        self,
        *,
        expectation: ExpectationResponse,
        evaluation: EvaluationResponse,
        evidence: Sequence[EvidenceResponse],
        context: InvestigationContext | None = None,
    ) -> MismatchExplanation:
        started = time.monotonic()
        facts = normalize(
            expectation=expectation,
            evaluation=evaluation,
            evidence=evidence,
            context=context,
            max_evidence=self.settings.investigator_max_evidence,
        )
        # Include schema/system overhead in the request budget, not just user facts.
        overhead = (
            len(
                (
                    mismatch_investigator_prompt()
                    + json.dumps(InvestigatorDraft.model_json_schema())
                ).encode()
            )
            + (
                len(json.dumps(InvestigatorDraft.model_json_schema()).encode())
                if self.settings.bedrock_native_structured_output
                else 0
            )
            + 1024
        )
        while (
            facts.evidence
            and overhead + len(packet(facts).encode())
            > self.settings.investigator_max_prompt_bytes
        ):
            facts = replace(facts, evidence=facts.evidence[:-1], truncated=True)
        draft = None
        if facts.evidence:
            try:
                draft = self.client.converse_json(
                    system_prompt=mismatch_investigator_prompt(),
                    user_content=packet(facts),
                    output_model=InvestigatorDraft,
                    operation_name="mismatch_investigator",
                    metadata={"prompt_version": MISMATCH_INVESTIGATOR_PROMPT_VERSION},
                    temperature=0,
                )
                if (
                    draft.expected.model_dump_json() != facts.expected.model_dump_json()
                    or draft.observed.model_dump_json()
                    != facts.observed.model_dump_json()
                ):
                    raise InvestigationGroundingError()
                result = explanation(facts, draft)
            except (BedrockError, InvestigationGroundingError, ValidationError):
                result = explanation(facts, None)
        else:
            result = explanation(facts, None)
        logger.info(
            "Mismatch investigation completed",
            extra={
                "operation_name": "mismatch_investigator",
                "result_status": result.generation,
                "duration_ms": round((time.monotonic() - started) * 1000),
                "prompt_version": MISMATCH_INVESTIGATOR_PROMPT_VERSION,
            },
        )
        return result
