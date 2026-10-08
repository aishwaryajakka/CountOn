"""Persisted evaluation response contract."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.evaluators.base import EvaluationResult


class EvaluationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    expectation_id: UUID
    result: EvaluationResult
    expected: dict[str, Any]
    observed: dict[str, Any]
    confidence: float
    reasoning: dict[str, Any]
    created_at: datetime
