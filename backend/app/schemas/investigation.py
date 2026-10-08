"""Concise grounded explanations; no model reasoning or mutable evaluation state."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.expectation import ComparisonType

EvidenceLabel = str


class InvestigationContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    authenticated_user_id: UUID | None = Field(default=None, repr=False)


class ExpectedValue(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)
    metric: str | None
    comparison: ComparisonType | None
    target: float | bool | None
    materiality_threshold: float | None
    tolerance_kind: Literal["relative", "absolute"] | None


class ObservedValue(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, frozen=True)
    metric: str | None
    value: float | bool | None


class ExplanationFactor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    description: str = Field(min_length=1, max_length=500)
    evidence_refs: list[str] = Field(min_length=1, max_length=12)
    strength: Literal["observation", "possible_contribution", "conflicting"]


class EvidenceReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ref: str = Field(pattern=r"^E[1-9][0-9]?$", max_length=3)
    evidence_id: UUID


class MismatchExplanation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    result: Literal["MISMATCH"] = "MISMATCH"
    summary: str = Field(min_length=1, max_length=1000)
    expected: ExpectedValue
    observed: ObservedValue
    evaluator_reason: str | None
    key_factors: list[ExplanationFactor] = Field(default_factory=list, max_length=12)
    caveats: list[str] = Field(default_factory=list, max_length=8)
    confidence_note: str
    confidence: float = Field(default=0.0, ge=0, le=1, allow_inf_nan=False)
    insufficient_evidence: bool = True
    evidence_refs: list[EvidenceReference] = Field(default_factory=list, max_length=12)
    prompt_version: str
    grounded: Literal[True] = True
    generation: Literal["bedrock", "deterministic"]


class FactorDraft(BaseModel):
    """Restricted fact proposals, not arbitrary text that could invent causality."""

    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    kind: Literal[
        "observed_measurement",
        "usage_change",
        "rate_change",
        "possible_rate_offset",
        "conflicting_observations",
    ]
    evidence_refs: list[str] = Field(min_length=1, max_length=3)
    values: dict[str, float | bool]


class InvestigatorDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected: ExpectedValue
    observed: ObservedValue
    summary_kind: Literal["mismatch", "insufficient_cause", "possible_contribution"]
    key_factors: list[FactorDraft] = Field(default_factory=list, max_length=6)
