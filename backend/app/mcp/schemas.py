"""Structured tool contracts; capture reuses the existing API contract."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.expectation import ExpectationStatus, ExpectationType
from app.schemas.expectation import ExpectationCreate

CaptureExpectationInput = ExpectationCreate


class GetExpectationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expectation_id: UUID


class ListExpectationsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ExpectationStatus | None = None
    type: ExpectationType | None = None
    limit: int = Field(default=50, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class ExpectationResult(BaseModel):
    """Compact public fields shared by capture/get/list results."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    claim: str
    type: ExpectationType
    status: ExpectationStatus
    metric: str | None
    created_at: datetime


class ExpectationListResult(BaseModel):
    expectations: list[ExpectationResult]
    limit: int
    offset: int
