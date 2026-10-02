"""Expectation HTTP contracts; domain requirements are checked in services."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from app.db.models.expectation import ComparisonType, ExpectationStatus, ExpectationType


class ExpectationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)

    claim: str = Field(min_length=1)
    type: ExpectationType
    metric: str | None = Field(default=None, min_length=1, max_length=100)
    comparison: ComparisonType | None = None
    baseline: float | None = None
    target_value: float | None = None
    deadline: AwareDatetime | None = None
    evidence_sources: list[str] = Field(default_factory=list)
    materiality_threshold: float = Field(default=0.05, ge=0, le=1)


class ExpectationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)

    claim: str | None = Field(default=None, min_length=1)
    metric: str | None = Field(default=None, min_length=1, max_length=100)
    comparison: ComparisonType | None = None
    baseline: float | None = None
    target_value: float | None = None
    deadline: AwareDatetime | None = None
    evidence_sources: list[str] | None = None
    materiality_threshold: float | None = Field(default=None, ge=0, le=1)
    status: ExpectationStatus | None = None


class ExpectationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID | None
    claim: str
    type: ExpectationType
    metric: str | None
    comparison: ComparisonType | None
    baseline: float | None
    target_value: float | None
    deadline: datetime | None
    evidence_sources: list[str]
    materiality_threshold: float
    status: ExpectationStatus
    compiler_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
