"""Structured tool contracts; capture reuses the existing API contract."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models.expectation import ExpectationStatus, ExpectationType
from app.evaluators.base import EvaluationResult
from app.schemas.compiler import CompileContext
from app.schemas.expectation import ExpectationCreate
from app.schemas.investigation import MismatchExplanation


class CaptureExpectationInput(ExpectationCreate):
    compilation_state: str | None = Field(default=None, max_length=24000)


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


class CompileExpectationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=2000)
    conversational: bool = False
    compilation_id: UUID | None = None
    timezone: str = Field(default="UTC", min_length=1, max_length=100)
    locale: str | None = Field(default=None, pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        return CompileContext.valid_timezone(value)


class ContinueCompilationInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    state: str = Field(min_length=1, max_length=24000)
    answer: str = Field(min_length=1, max_length=2000)


class CompilationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal[
        "compiled", "clarification", "cancelled", "expired", "unsupported", "error"
    ]
    message: str
    expectation: ExpectationCreate | None = None
    state: str | None = None
    capture_state: str | None = None
    code: str | None = None
    bedrock_used: bool = False
    prompt_version: str
    clarification_turn: int = 0


class ExplainMismatchInput(GetExpectationInput):
    pass


class ExplanationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: EvaluationResult | None = None
    expectation_id: UUID
    evaluation_id: UUID | None = None
    evidence_ids: list[UUID] = Field(default_factory=list, max_length=12)
    fallback_used: bool = False
    explanation: MismatchExplanation | None = None
    message: str
    code: (
        Literal[
            "NO_EVALUATION", "NOT_MISMATCH", "NO_EVIDENCE", "INVESTIGATION_UNAVAILABLE"
        ]
        | None
    ) = None
    bedrock_used: bool = False
