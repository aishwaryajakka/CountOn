"""Deterministic evaluation orchestration with one atomic persistence commit."""

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import EvaluationNotFoundError
from app.db.models import Evaluation, ExpectationStatus, ExpectationType
from app.evaluators import boolean, numeric, temporal
from app.evaluators.base import EvaluationOutput, EvaluationResult
from app.repositories import evaluation as repository
from app.repositories import evidence as evidence_repository
from app.repositories import expectation as expectation_repository
from app.services.expectation_service import get_expectation

logger = logging.getLogger(__name__)


def evaluate_expectation(db: Session, expectation_id: UUID) -> Evaluation:
    expectation = get_expectation(db, expectation_id)
    evidence = evidence_repository.list_evidence_for_expectation(db, expectation_id)
    evaluator = {
        ExpectationType.numeric_comparison: numeric.evaluate,
        ExpectationType.boolean: boolean.evaluate,
        ExpectationType.temporal: temporal.evaluate,
        ExpectationType.event: temporal.evaluate,
    }.get(expectation.type)
    output = evaluator(expectation, evidence) if evaluator else EvaluationOutput(
        result=EvaluationResult.UNKNOWN, confidence=0.0,
        reasoning={"reason": "unsupported_expectation_type"},
    )
    status = expectation.status
    # Keep terminal statuses, while still recording a new evaluation in history.
    if status not in (ExpectationStatus.resolved, ExpectationStatus.cancelled):
        if output.result == EvaluationResult.MATCH:
            status = ExpectationStatus.fulfilled
        elif output.result == EvaluationResult.MISMATCH:
            status = ExpectationStatus.contradicted
        # UNKNOWN preserves the existing status, including monitoring.
    try:
        persisted = repository.create_evaluation(db, expectation_id, output)
        if status != expectation.status:
            expectation_repository.update_expectation(db, expectation, {"status": status})
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(persisted)
    logger.info("Evaluation completed id=%s expectation_id=%s result=%s", persisted.id, expectation_id, output.result.value)
    return persisted


def list_evaluations(db: Session, expectation_id: UUID) -> list[Evaluation]:
    get_expectation(db, expectation_id)
    return repository.list_evaluations_for_expectation(db, expectation_id)


def get_latest_evaluation(db: Session, expectation_id: UUID) -> Evaluation:
    get_expectation(db, expectation_id)
    evaluation = repository.get_latest_evaluation(db, expectation_id)
    if evaluation is None:
        raise EvaluationNotFoundError(expectation_id)
    return evaluation
