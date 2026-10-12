"""Owned scheduling and explicit provider rules; never accept credentials here."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class OutlookRule(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    sender: str = Field(
        pattern=r"^[A-Za-z0-9.!#$%&\x27*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$",
        max_length=254,
    )
    subject_prefix: str = Field(min_length=1, max_length=100)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")


class MonitoringSchedule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    next_run_at: AwareDatetime
    interval_seconds: int = Field(default=3600, ge=60, le=31536000)
    recurring: bool = False
    window_start_at: AwareDatetime | None = None
    max_evidence_age_seconds: int = Field(default=86400, ge=1, le=31536000)
    max_attempts: int = Field(default=5, ge=1, le=20)
    status: Literal["pending", "paused"] = "pending"
    connection_id: UUID | None = None
    outlook_rule: OutlookRule | None = None

    @model_validator(mode="after")
    def check_binding(self):
        if (self.connection_id is None) != (self.outlook_rule is None):
            raise ValueError(
                "An Outlook binding requires both connection and explicit rule"
            )
        if self.window_start_at and self.window_start_at > self.next_run_at:
            raise ValueError("Monitoring window must start before the due time")
        return self


class MonitoringResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    expectation_id: UUID
    status: str
    next_run_at: datetime
    last_run_at: datetime | None
    interval_seconds: int
    recurring: bool
    max_evidence_age_seconds: int
    attempt_count: int
    max_attempts: int
    last_error: str | None
    connection_id: UUID | None
    window_start_at: datetime | None
    provider_config: dict
