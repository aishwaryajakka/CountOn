"""Mismatch investigation service orchestrating AI root-cause analysis."""

from uuid import UUID
from sqlalchemy.orm import Session
from fastapi import HTTPException, status

from app.ai.investigator import investigate_mismatch
from app.ai.models.expectation import (
    Expectation as AIExpectation,
    EvaluationResult as AIEvaluationResult,
    Evidence as AIEvidence,
    InvestigationResult,
)
from app.services import expectation_service


def investigate_expectation_mismatch(
    db: Session,
    expectation_id: UUID,
    user_id: UUID,
    mock_mode: bool | None = None,
) -> InvestigationResult:
    """
    Fetches DB expectation, evaluation, and evidence records, converts to AI models,
    and runs Bedrock root-cause mismatch investigation.
    """
    expectation = expectation_service.get_expectation(db, expectation_id, user_id)

    # Find latest evaluation
    latest_eval = expectation.evaluations[0] if expectation.evaluations else None
    if not latest_eval:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Expectation has not been evaluated yet.",
        )

    # Convert DB Expectation to AI model
    ai_expectation = AIExpectation(
        id=str(expectation.id),
        claim=expectation.claim,
        type=expectation.type.value if hasattr(expectation.type, "value") else str(expectation.type),
        metric=expectation.metric,
        comparison=expectation.comparison.value if expectation.comparison and hasattr(expectation.comparison, "value") else (str(expectation.comparison) if expectation.comparison else None),
        baseline=float(expectation.baseline) if expectation.baseline is not None else None,
        deadline=expectation.deadline.isoformat() if expectation.deadline else None,
        evidence_sources=expectation.evidence_sources or [],
        materiality_threshold=expectation.materiality_threshold,
        status="mismatch" if latest_eval.result.value == "MISMATCH" else "monitoring",
    )

    # Convert DB Evaluation to AI model
    ai_evaluation = AIEvaluationResult(
        result=latest_eval.result.value if hasattr(latest_eval.result, "value") else str(latest_eval.result),
        expected=str(latest_eval.expected),
        contradiction=latest_eval.result.value == "MISMATCH",
        details=latest_eval.reasoning if isinstance(latest_eval.reasoning, dict) else {},
    )

    # Convert DB Evidence list to AI Evidence models
    ai_evidence_list = [
        AIEvidence(
            expectation_id=str(e.expectation_id),
            source=e.source,
            metric=e.metric,
            value=e.value,
            unit=e.unit,
            timestamp=e.observed_at.isoformat() if e.observed_at else None,
            confidence=e.confidence,
        )
        for e in expectation.evidence
    ]

    return investigate_mismatch(
        expectation=ai_expectation,
        evaluation_result=ai_evaluation,
        evidence=ai_evidence_list,
        mock_mode=mock_mode,
    )
