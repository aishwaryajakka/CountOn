"""Backend-authored provenance, never part of a model's output schema."""

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EvidenceSource(StrEnum):
    UTILITY = "Utility"
    BILLING = "Billing"
    DELIVERY = "Delivery"
    RING = "Ring"
    CALENDAR = "Calendar"
    OUTLOOK = "Outlook"
    BEE = "Bee"
    OTHER = "Declared source"


class SourceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    evidence_id: UUID
    source: EvidenceSource
    allowed: bool


class EvidenceProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    decisions: tuple[SourceDecision, ...] = Field(default=(), max_length=100)
    used: tuple[UUID, ...] = Field(default=(), max_length=12)
    grounding_passed: bool | None = None
    bedrock_attempted: bool = False

    @model_validator(mode="after")
    def allowed_citations(self) -> "EvidenceProvenance":
        identities = [item.evidence_id for item in self.decisions]
        permitted = {item.evidence_id for item in self.decisions if item.allowed}
        if len(set(identities)) != len(identities) or len(set(self.used)) != len(
            self.used
        ):
            raise ValueError("Provenance identities must be unique")
        if not set(self.used) <= permitted:
            raise ValueError("Evidence citations must have an allowed source")
        return self

    @property
    def sources_used(self) -> tuple[EvidenceSource, ...]:
        return tuple(
            dict.fromkeys(
                item.source for item in self.decisions if item.evidence_id in self.used
            )
        )
