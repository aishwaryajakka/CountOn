"""Redacted, linked user-visible audit history contracts."""

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditExpectationSummary(BaseModel):
    id: UUID
    claim: str
    status: str


class AuditEvidenceSummary(BaseModel):
    id: UUID
    source: str
    metric: str | None
    value: dict[str, Any]
    unit: str | None
    observed_at: datetime


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_event_id: UUID
    counton_user_id: UUID
    expectation_id: UUID | None
    event_type: str
    occurred_at: datetime
    source_provider: str | None
    source_type: str | None
    source_provenance: str | None
    source_reference: str | None
    evidence_id: UUID | None
    evaluation_id: UUID | None
    result_status: Literal["MATCH", "UNKNOWN", "MISMATCH"] | None
    action_taken: str
    actor_type: Literal["USER", "SYSTEM", "PROVIDER"]
    action_metadata: dict[str, Any]
    request_id: str | None
    expectation: AuditExpectationSummary | None
    evidence: AuditEvidenceSummary | None
