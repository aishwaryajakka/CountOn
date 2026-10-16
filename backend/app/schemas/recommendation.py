"""Structured Recommendation domain models and HTTP contracts.

Provides confidence scoring, source citations, and human approval workflow.
Recommendations require explicit user approval before becoming active expectations.
"""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.expectation import ComparisonType, ExpectationType
from app.schemas.expectation import ExpectationCreate


class RecommendationStatus(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    DISMISSED = "dismissed"


class RecommendationCategory(StrEnum):
    BILLING = "billing"
    DELIVERY = "delivery"
    CALENDAR = "calendar"
    SUBSCRIPTION = "subscription"
    REFUND = "refund"
    OTHER = "other"


class SourceReference(BaseModel):
    """Provenance and context for where a recommendation was extracted."""
    model_config = ConfigDict(extra="ignore")

    provider: str = Field(..., description="Provider source, e.g. google, microsoft, amazon, utility")
    source_id: str | None = Field(default=None, description="External message ID, email thread ID, or order ID")
    snippet: str | None = Field(default=None, description="Verbatim text span or excerpt supporting recommendation")
    timestamp: datetime | None = Field(default=None, description="Timestamp of the original source communication")


class RecommendationBase(BaseModel):
    """Base representation of an AI-extracted recommendation."""
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(..., min_length=1, max_length=200, description="Short human-friendly title")
    claim: str = Field(..., min_length=1, description="Structured expectation claim in clear natural language")
    category: RecommendationCategory = Field(default=RecommendationCategory.OTHER)
    type: ExpectationType = Field(default=ExpectationType.numeric_comparison)
    metric: str | None = Field(default=None, max_length=100)
    comparison: ComparisonType | None = None
    baseline: float | None = None
    target_value: float | None = None
    deadline: datetime | None = None
    evidence_sources: list[str] = Field(default_factory=list)
    confidence: float = Field(..., ge=0.0, le=1.0, description="Normalized model confidence between 0.0 and 1.0")
    source_references: list[SourceReference] = Field(default_factory=list)
    rationale: str = Field(..., min_length=1, max_length=1000, description="Why this expectation is recommended")


class RecommendationResponse(RecommendationBase):
    """Output representation for an existing recommendation."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(default_factory=uuid4)
    status: RecommendationStatus = Field(default=RecommendationStatus.PENDING_APPROVAL)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    reviewed_at: datetime | None = None
    created_expectation_id: UUID | None = None


class RecommendationApprovalRequest(BaseModel):
    """Action payload for user approving or rejecting a recommendation."""
    model_config = ConfigDict(extra="forbid")

    action: RecommendationStatus = Field(..., description="Either approved, rejected, or dismissed")
    custom_baseline: float | None = Field(default=None, description="Optional override for baseline if user edits")
    custom_deadline: datetime | None = Field(default=None, description="Optional override for deadline if user edits")
