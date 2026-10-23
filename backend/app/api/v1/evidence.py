"""Nested HTTP endpoints for normalized evidence."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_db
from app.db.models import Evidence
from app.schemas.evidence import EvidenceCreate, EvidenceResponse
from app.services import evidence_service as service

router = APIRouter(prefix="/expectations", tags=["evidence"])
Database = Annotated[Session, Depends(get_db)]


@router.post("/{expectation_id}/evidence", response_model=EvidenceResponse, status_code=status.HTTP_201_CREATED, summary="Add normalized evidence to an expectation")
def add_evidence(expectation_id: UUID, payload: EvidenceCreate, db: Database, user: CurrentUser, idempotency_key: Annotated[str | None, Header(min_length=1, max_length=128)] = None) -> Evidence:
    # This route accepts user-submitted facts, not verified provider authority.
    # Provider workers and dedicated simulators call the service after their own
    # grant/binding checks. Never let an HTTP payload impersonate those paths.
    raw = {key: value for key, value in payload.raw_data.items()
           if key in {"external_id", "provider_record_ref", "category", "simulated"}}
    if "provenance" in payload.raw_data:
        raw["provenance"] = "USER_SUBMITTED"
    payload = payload.model_copy(update={"raw_data": raw})
    return service.add_evidence(db, expectation_id, payload, user.id, idempotency_key)


@router.get("/{expectation_id}/evidence", response_model=list[EvidenceResponse], summary="List evidence by observation time")
def list_evidence(expectation_id: UUID, db: Database, user: CurrentUser, limit: Annotated[int, Query(ge=1, le=100)] = 100, offset: Annotated[int, Query(ge=0)] = 0) -> list[Evidence]:
    return service.list_evidence(db, expectation_id, user.id, limit, offset)
