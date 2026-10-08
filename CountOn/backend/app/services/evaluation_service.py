"""Deterministic evaluation orchestration with one atomic persistence commit."""

import logging
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.exceptions import EvaluationNotFoundError
from app.db.models import Evaluation, ExpectationStatus, ExpectationType
from app.evaluators import boolean, numeric, temporal
from app.evaluators.base import EvaluationOutput, EvaluationResult
from app.repositories import evaluation as repository
from app.repositories import operations
from app.core import observability
from app.repositories import evidence as evidence_repository
from app.repositories import expectation as expectation_repository
from app.services.expectation_service import get_expectation
from app.services import notification_service

logger = logging.getLogger(__name__)


def evaluate_expectation(db: Session, expectation_id: UUID, user_id: UUID) -> Evaluation:
    expectation = get_expectation(db, expectation_id, user_id)
    evidence = evidence_repository.latest_relevant_evidence(db, expectation_id, expectation.metric)
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
        operations.audit(db, expectation, "expectation.evaluated", persisted.id)
        notification = notification_service.for_evaluation(db, expectation, persisted)
        db.commit()
    except Exception:
        db.rollback()
        raise
    observability.record("evaluation_results", output.result.value)
    if notification is not None:
        observability.record("notifications_created")
    db.refresh(persisted)
    logger.info("Evaluation completed id=%s expectation_id=%s result=%s", persisted.id, expectation_id, output.result.value)
    return persisted


def list_evaluations(db: Session, expectation_id: UUID, user_id: UUID, limit: int = 100, offset: int = 0) -> list[Evaluation]:
    get_expectation(db, expectation_id, user_id)
    return repository.list_evaluations_for_expectation(db, expectation_id, limit, offset)


def get_latest_evaluation(db: Session, expectation_id: UUID, user_id: UUID) -> Evaluation:
    get_expectation(db, expectation_id, user_id)
    evaluation = repository.get_latest_evaluation(db, expectation_id)
    if evaluation is None:
        raise EvaluationNotFoundError(expectation_id)
    return evaluation
