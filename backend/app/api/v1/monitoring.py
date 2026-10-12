"""Narrow scheduling endpoints use the existing verified current user."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_db
from app.schemas.monitoring import MonitoringResponse, MonitoringSchedule
from app.services import monitoring_service

router = APIRouter(prefix="/expectations", tags=["monitoring"])
Database = Annotated[Session, Depends(get_db)]


@router.get("/{expectation_id}/monitoring", response_model=MonitoringResponse)
def get(expectation_id: UUID, db: Database, user: CurrentUser):
    return monitoring_service.get(db, expectation_id, user.id)


@router.put("/{expectation_id}/monitoring", response_model=MonitoringResponse)
def configure(
    expectation_id: UUID, schedule: MonitoringSchedule, db: Database, user: CurrentUser
):
    return monitoring_service.configure(db, expectation_id, user.id, schedule)
