"""Nested HTTP endpoints for deterministic evaluation and history."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.db.models import Evaluation
from app.schemas.evaluation import EvaluationResponse
from app.services import evaluation_service as service

router = APIRouter(prefix="/expectations", tags=["evaluations"])
Database = Annotated[Session, Depends(get_db)]


@router.post("/{expectation_id}/evaluate", response_model=EvaluationResponse, summary="Evaluate and persist a deterministic result")
def evaluate_expectation(expectation_id: UUID, db: Database) -> Evaluation:
    return service.evaluate_expectation(db, expectation_id)


@router.get("/{expectation_id}/evaluations", response_model=list[EvaluationResponse], summary="Read evaluation history, newest first")
def list_evaluations(expectation_id: UUID, db: Database) -> list[Evaluation]:
    return service.list_evaluations(db, expectation_id)


@router.get("/{expectation_id}/evaluations/latest", response_model=EvaluationResponse, summary="Read the latest evaluation")
def latest_evaluation(expectation_id: UUID, db: Database) -> Evaluation:
    return service.get_latest_evaluation(db, expectation_id)
