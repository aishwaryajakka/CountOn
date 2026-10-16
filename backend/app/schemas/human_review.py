"""Human Review & Verification schema models and storage."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class ReviewStatus(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    FLAGGED = "flagged"
    REJECTED = "rejected"


class HumanReviewItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: UUID = Field(default_factory=uuid4)
    input_text: str = Field(..., description="The user query or statement sent to Bedrock")
    model_output: dict[str, Any] = Field(..., description="The raw or parsed Bedrock output")
    expected_output: dict[str, Any] | None = Field(default=None, description="Expected ground truth criteria")
    status: ReviewStatus = Field(default=ReviewStatus.PENDING)
    reviewer_notes: str | None = Field(default=None)
    reviewer_verdict: str | None = Field(default=None)
    latency_ms: float | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed_at: datetime | None = None


class ReviewActionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ReviewStatus = Field(..., description="Status: verified, flagged, or rejected")
    reviewer_notes: str | None = Field(default=None, description="Human reviewer notes/comments")
    reviewer_verdict: str | None = Field(default=None, description="Human verdict summary")
