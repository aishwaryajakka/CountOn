"""Authenticated, redacted audit history."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import AwareDatetime
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_db
from app.schemas.audit import AuditEventResponse
from app.services import audit_service

router = APIRouter(prefix="/audit-events", tags=["audit"])
Database = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[AuditEventResponse])
def list_events(
    db: Database,
    user: CurrentUser,
    expectation_id: UUID | None = None,
    source_provider: Annotated[str | None, Query(min_length=1, max_length=30)] = None,
    result_status: Literal["MATCH", "UNKNOWN", "MISMATCH"] | None = None,
    occurred_after: AwareDatetime | None = None,
    occurred_before: AwareDatetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return audit_service.list_events(
        db,
        user.id,
        expectation_id=expectation_id,
        source_provider=source_provider,
        result_status=result_status,
        occurred_after=occurred_after,
        occurred_before=occurred_before,
        limit=limit,
        offset=offset,
    )
