"""
Continuous Monitoring & External Account Event Trigger API Endpoints.
"""

from typing import Annotated, Any
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, status as http_status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_db
from app.services import monitoring_service

router = APIRouter(prefix="/monitoring", tags=["monitoring"])
Database = Annotated[Session, Depends(get_db)]


class AccountEventTriggerRequest(BaseModel):
    provider: str = Field(..., description="External provider e.g. 'gmail', 'outlook', 'amazon', 'google'")
    event_type: str = Field(..., description="Type of event e.g. 'email_received', 'calendar_updated', 'package_shipped', 'delivery_delayed'")
    payload: dict[str, Any] = Field(..., description="Context payload (matches provider context schema)")
    mock_mode: bool | None = Field(default=None, description="Optional override to force mock vs Bedrock mode")


class AccountEventTriggerResponse(BaseModel):
    expectation_id: str
    provider: str
    event_type: str
    evaluation_result: str
    mismatch_detected: bool
    evidence_created: int
    summary: str
    investigation: dict[str, Any] | None = None
    notification_id: str | None = None


class MonitoringCycleResponse(BaseModel):
    status: str
    total_active: int
    evaluated: int
    matches: int
    mismatches: int
    unknowns: int
    timestamp: str


@router.post(
    "/trigger-event",
    response_model=AccountEventTriggerResponse,
    status_code=http_status.HTTP_200_OK,
    summary="Trigger an external account event, automatically ingest evidence, and evaluate expectation",
)
def trigger_account_event(
    payload: AccountEventTriggerRequest,
    db: Database,
    user: CurrentUser,
) -> AccountEventTriggerResponse:
    result = monitoring_service.trigger_account_event(
        db=db,
        user_id=user.id,
        provider=payload.provider,
        event_type=payload.event_type,
        payload=payload.payload,
        mock_mode=payload.mock_mode,
    )
    return AccountEventTriggerResponse(**result.to_dict())


@router.post(
    "/run-cycle",
    response_model=MonitoringCycleResponse,
    status_code=http_status.HTTP_200_OK,
    summary="Run continuous monitoring cycle across all active expectations",
)
def run_monitoring_cycle(
    db: Database,
    user: CurrentUser,
    mock_mode: bool | None = None,
) -> MonitoringCycleResponse:
    res = monitoring_service.run_continuous_monitoring_sweep(
        db=db,
        user_id=user.id,
        mock_mode=mock_mode,
    )
    return MonitoringCycleResponse(**res)
