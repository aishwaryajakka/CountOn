
"""Dashboard summary and unresolved mismatch endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_db
from app.api.v1.notifications import NotificationResponse
from app.db.models import Expectation, ExpectationStatus, Notification

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

Database = Annotated[Session, Depends(get_db)]


class DashboardSummaryResponse(BaseModel):
    total: int
    by_status: dict[str, int]


@router.get("/summary", response_model=DashboardSummaryResponse)
def dashboard_summary(
    db: Database,
    user: CurrentUser,
) -> DashboardSummaryResponse:
    rows = db.execute(
        select(Expectation.status, func.count(Expectation.id))
        .where(Expectation.user_id == user.id)
        .group_by(Expectation.status)
    ).all()

    counts = {status.value: 0 for status in ExpectationStatus}

    for status, count in rows:
        counts[status.value if hasattr(status, "value") else status] = count

    return DashboardSummaryResponse(
        total=sum(counts.values()),
        by_status=counts,
    )


@router.get(
    "/unresolved-mismatches",
    response_model=list[NotificationResponse],
)
def unresolved_mismatches(
    db: Database,
    user: CurrentUser,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    statement = (
        select(Notification)
        .where(
            Notification.user_id == user.id,
            Notification.status == "pending",
            Notification.type == "expectation_mismatch",
        )
        .order_by(
            Notification.created_at.desc(),
            Notification.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )

    return list(db.scalars(statement))
