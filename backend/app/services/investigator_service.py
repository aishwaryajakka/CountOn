"""Owned, read-only orchestration of the existing grounded investigator."""

from uuid import UUID

from sqlalchemy.orm import Session

from app.ai.investigation_evidence import InvestigationInputError
from app.evaluators.base import EvaluationResult
from app.repositories import evidence as evidence_repository
from app.schemas.evaluation import EvaluationResponse
from app.schemas.evidence import EvidenceResponse
from app.schemas.expectation import ExpectationResponse
from app.schemas.investigation import InvestigationContext, MismatchExplanation
from app.services import evaluation_service, expectation_service, investigation_service
from app.services.investigation_service import MismatchInvestigator


def investigate_expectation_mismatch(
    db: Session,
    expectation_id: UUID,
    user_id: UUID,
    *,
    investigator: MismatchInvestigator | None = None,
) -> MismatchExplanation:
    """Use a verified principal, never a payload user ID. No writes or reevaluation.

    Existing owned services enforce access and select the newest recorded result.
    Missing evaluation/non-MISMATCH raises before fetching evidence or invoking AI.
    """
    expectation = expectation_service.get_expectation(db, expectation_id, user_id)
    evaluation = evaluation_service.get_latest_evaluation(db, expectation_id, user_id)
    if evaluation.result != EvaluationResult.MISMATCH:
        raise InvestigationInputError()
    evidence = evidence_repository.investigation_evidence(
        db, expectation_id, evaluation
    )
    return investigation_service.investigate_mismatch(
        expectation=ExpectationResponse.model_validate(expectation),
        evaluation=EvaluationResponse.model_validate(evaluation),
        evidence=[EvidenceResponse.model_validate(row) for row in evidence],
        context=InvestigationContext(authenticated_user_id=user_id),
        investigator=investigator,
    )
