"""Owned monitoring plans: references and confirmation, never caller identity/facts."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator

from app.schemas.provider_sync import SourceRule


class SourcePlanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    order_id: str | None = Field(default=None, pattern=r"^\d{3}-\d{7}-\d{7}$")
    calendar_uid: str | None = Field(default=None, min_length=1, max_length=255)
    expected_start: AwareDatetime | None = None


class SourceChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sync_id: UUID
    external_id: str = Field(min_length=1, max_length=512)


class SourceCandidate(SourceChoice):
    group_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    provider: Literal["google", "microsoft"]
    account_label: str = Field(max_length=150)
    label: str = Field(max_length=180)
    rule: SourceRule
    suggestion_reason: str = Field(default="Explicit source identity.", max_length=180)
    synced_at: AwareDatetime | None = None
    sync_status: str = Field(default="pending", max_length=32)


class MonitoringPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expectation_id: UUID
    status: Literal[
        "ready", "clarification", "permission_required", "unsupported", "bounded"
    ]
    question: str | None = None
    candidates: list[SourceCandidate] = Field(default_factory=list, max_length=20)
    triggers: tuple[str, ...] = ("verified_provider_change", "periodic_reconciliation")
    deadline: AwareDatetime | None = None
    bedrock_calls: Literal[0] = 0


class ConfirmMonitoringPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    confirmed: Literal[True]
    query: SourcePlanRequest = Field(default_factory=SourcePlanRequest)
    sources: list[SourceChoice] = Field(min_length=1, max_length=4)

    @field_validator("confirmed", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("Explicit confirmation is required")
        return value


class AppliedMonitoringPlan(BaseModel):
    expectation_id: UUID
    job_id: UUID
    binding_ids: list[UUID]
    status: Literal["pending", "running", "paused", "completed", "failed", "cancelled"]
