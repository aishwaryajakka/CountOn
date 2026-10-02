"""Evaluation database operations; newest results are listed first."""

from dataclasses import asdict
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Evaluation
from app.evaluators.base import EvaluationOutput


def create_evaluation(db: Session, expectation_id: UUID, evaluation_output: EvaluationOutput) -> Evaluation:
    evaluation = Evaluation(expectation_id=expectation_id, **asdict(evaluation_output))
    db.add(evaluation)
    db.flush()
    return evaluation


def list_evaluations_for_expectation(db: Session, expectation_id: UUID) -> list[Evaluation]:
    statement = select(Evaluation).where(Evaluation.expectation_id == expectation_id).order_by(
        Evaluation.created_at.desc(), Evaluation.id.desc(),
    )
    return list(db.scalars(statement))


def get_latest_evaluation(db: Session, expectation_id: UUID) -> Evaluation | None:
    statement = select(Evaluation).where(Evaluation.expectation_id == expectation_id).order_by(
        Evaluation.created_at.desc(), Evaluation.id.desc(),
    ).limit(1)
    return db.scalar(statement)
