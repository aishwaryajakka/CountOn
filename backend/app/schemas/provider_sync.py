"""Explicit source selection; no caller identity, tokens or arbitrary fetch URL."""

from datetime import datetime
from typing import Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)


class SyncSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    calendar_id: str | None = Field(default=None, min_length=1, max_length=255)


class SourceRule(BaseModel):
    model_config = ConfigDict(
        extra="forbid", hide_input_in_errors=True, str_strip_whitespace=True
    )
    kind: Literal["bill", "reply", "commitment", "order", "calendar"]
    sender: str | None = Field(
        default=None, pattern=r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$", max_length=254
    )
    subject_contains: str | None = Field(default=None, min_length=3, max_length=100)
    thread_id: str | None = Field(default=None, min_length=1, max_length=512)
    event_id: str | None = Field(default=None, min_length=1, max_length=512)
    message_id: str | None = Field(default=None, min_length=1, max_length=512)
    recipient: str | None = Field(
        default=None, pattern=r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$", max_length=254
    )
    order_id: str | None = Field(default=None, pattern=r"^\d{3}-\d{7}-\d{7}$")
    expected_start: AwareDatetime | None = None
    calendar_uid: str | None = Field(default=None, min_length=1, max_length=255)
    occurrence_start: AwareDatetime | None = None
    currency: Literal["USD"] = "USD"
    timezone: str = Field(default="UTC", max_length=64)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Select an IANA source timezone") from None
        return value

    @model_validator(mode="after")
    def explicit_match(self):
        if self.kind == "calendar":
            if not self.event_id:
                raise ValueError("Select an exact calendar event")
        elif not self.sender or not (
            self.subject_contains or self.thread_id or self.order_id
        ):
            raise ValueError(
                "Email needs an exact sender and topic, thread or order identifier"
            )
        if self.kind == "reply" and not self.thread_id:
            raise ValueError("Expected replies require an exact thread")
        if self.kind == "order" and not self.order_id:
            raise ValueError("Orders require an exact order identifier")
        return self


class BindingCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sync_id: UUID
    rule: SourceRule


class SyncResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    connection_id: UUID
    stream: str
    status: str
    last_success_at: datetime | None
    next_run_at: datetime
    last_error: str | None
    coverage_start_at: datetime | None
    coverage_through_at: datetime | None


class BindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    expectation_id: UUID
    sync_id: UUID
    rule: SourceRule


class DisconnectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revoke: bool = True
    erase_evidence: bool = False
