"""Compiler and Investigator HTTP contract schemas."""

from typing import Literal
from uuid import UUID
from pydantic import BaseModel, Field, ConfigDict

from app.ai.models.expectation import Expectation, ClarificationRequest, InvestigationResult


class CompileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    text: str = Field(..., description="Casual user statement to compile into a structured expectation")
    mock_mode: bool | None = Field(default=None, description="Optional override to force mock vs Bedrock mode")


class CompileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: Literal["expectation", "clarification"]
    expectation: Expectation | None = None
    clarification: ClarificationRequest | None = None


class InvestigationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expectation_id: UUID = Field(..., description="ID of the expectation to investigate after a mismatch")
    mock_mode: bool | None = Field(default=None, description="Optional override to force mock vs Bedrock mode")


class InvestigationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    explanation: str
    key_factors: list[str] = Field(default_factory=list)
    confidence: float
