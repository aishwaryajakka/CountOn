"""Expectation HTTP lifecycle endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status as http_status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_db
from app.db.models import Expectation, ExpectationStatus, ExpectationType
from app.schemas.expectation import ExpectationCreate, ExpectationResponse, ExpectationUpdate
from app.services import expectation_service as service

router = APIRouter(prefix="/expectations", tags=["expectations"])
Database = Annotated[Session, Depends(get_db)]


@router.post("", response_model=ExpectationResponse, status_code=http_status.HTTP_201_CREATED, summary="Create an expectation")
def create_expectation(payload: ExpectationCreate, db: Database, user: CurrentUser) -> Expectation:
    return service.create_expectation(db, payload, user.id)


@router.get("", response_model=list[ExpectationResponse], summary="List expectations")
def list_expectations(
    db: Database, user: CurrentUser, status: ExpectationStatus | None = None,
    type: ExpectationType | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Expectation]:
    return service.list_expectations(db, user.id, status, limit, offset, type)


@router.get("/{expectation_id}", response_model=ExpectationResponse, summary="Read an expectation")
def get_expectation(expectation_id: UUID, db: Database, user: CurrentUser) -> Expectation:
    return service.get_expectation(db, expectation_id, user.id)


@router.patch("/{expectation_id}", response_model=ExpectationResponse, summary="Update provided expectation fields")
def update_expectation(expectation_id: UUID, payload: ExpectationUpdate, db: Database, user: CurrentUser) -> Expectation:
    return service.update_expectation(db, expectation_id, payload, user.id)


@router.delete("/{expectation_id}", status_code=http_status.HTTP_204_NO_CONTENT, response_class=Response, summary="Delete an expectation and its evidence and evaluations")
def delete_expectation(expectation_id: UUID, db: Database, user: CurrentUser) -> Response:
    service.delete_expectation(db, expectation_id, user.id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
