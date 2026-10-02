"""Normalized evidence HTTP contracts, independent of source-specific payloads."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, JsonValue


class EvidenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, str_strip_whitespace=True)

    external_event_id: str | None = Field(default=None,min_length=1,max_length=255)
    source: str = Field(min_length=1, max_length=100)
    metric: str | None = Field(default=None, min_length=1, max_length=100)
    value: dict[str, JsonValue]
    unit: str | None = Field(default=None, max_length=50)
    observed_at: AwareDatetime
    confidence: float = Field(default=1.0, ge=0, le=1)
    raw_data: dict[str, JsonValue] = Field(default_factory=dict)


class EvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    expectation_id: UUID
    external_event_id: str | None
    source: str
    metric: str | None
    value: dict[str, Any]
    unit: str | None
    observed_at: datetime
    confidence: float
    raw_data: dict[str, Any]
    created_at: datetime
