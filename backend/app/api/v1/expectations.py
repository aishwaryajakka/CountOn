"""Expectation HTTP lifecycle endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status as http_status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models import Expectation, ExpectationStatus
from app.schemas.expectation import ExpectationCreate, ExpectationResponse, ExpectationUpdate
from app.services import expectation_service as service

router = APIRouter(prefix="/expectations", tags=["expectations"])
Database = Annotated[Session, Depends(get_db)]


@router.post("", response_model=ExpectationResponse, status_code=http_status.HTTP_201_CREATED, summary="Create an expectation")
def create_expectation(payload: ExpectationCreate, db: Database) -> Expectation:
    return service.create_expectation(db, payload)


@router.get("", response_model=list[ExpectationResponse], summary="List expectations")
def list_expectations(
    db: Database, status: ExpectationStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[Expectation]:
    return service.list_expectations(db, status, limit, offset)


@router.get("/{expectation_id}", response_model=ExpectationResponse, summary="Read an expectation")
def get_expectation(expectation_id: UUID, db: Database) -> Expectation:
    return service.get_expectation(db, expectation_id)


@router.patch("/{expectation_id}", response_model=ExpectationResponse, summary="Update provided expectation fields")
def update_expectation(expectation_id: UUID, payload: ExpectationUpdate, db: Database) -> Expectation:
    return service.update_expectation(db, expectation_id, payload)


@router.delete("/{expectation_id}", status_code=http_status.HTTP_204_NO_CONTENT, response_class=Response, summary="Delete an expectation and its evidence and evaluations")
def delete_expectation(expectation_id: UUID, db: Database) -> Response:
    service.delete_expectation(db, expectation_id)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)
