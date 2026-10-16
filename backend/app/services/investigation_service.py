"""Pure explanation boundary. Callers must first load data through owned services."""

from collections.abc import Sequence
from typing import Protocol

from app.agent.privacy import EvidenceAccessPolicy
from app.ai.investigation_evidence import InvestigationInputError
from app.ai.mismatch_investigator import BedrockMismatchInvestigator
from app.evaluators.base import EvaluationResult
from app.schemas.evaluation import EvaluationResponse
from app.schemas.evidence import EvidenceResponse
from app.schemas.expectation import ExpectationResponse
from app.schemas.investigation import InvestigationContext, MismatchExplanation


class MismatchInvestigator(Protocol):
    def investigate_mismatch(
        self,
        *,
        expectation: ExpectationResponse,
        evaluation: EvaluationResponse,
        evidence: Sequence[EvidenceResponse],
        context: InvestigationContext | None = None,
    ) -> MismatchExplanation: ...


def investigate_mismatch(
    *,
    expectation: ExpectationResponse,
    evaluation: EvaluationResponse,
    evidence: Sequence[EvidenceResponse],
    context: InvestigationContext | None = None,
    investigator: MismatchInvestigator | None = None,
) -> MismatchExplanation:
    """Does not authorize a transport, fetch data, reevaluate, mutate or persist.

    Future orchestration must get owned expectation/evaluation/evidence via existing
    services and pass the verified principal as context, never a client-supplied ID.
    """
    if (
        evaluation.result != EvaluationResult.MISMATCH
        or evaluation.expectation_id != expectation.id
        or context
        and context.authenticated_user_id not in (None, expectation.user_id)
        or any(item.expectation_id != expectation.id for item in evidence)
    ):
        raise InvestigationInputError()
    policy = EvidenceAccessPolicy(expectation)
    evidence = [item for item in evidence if policy.decide(item).allowed]
    if investigator is not None:
        return investigator.investigate_mismatch(
            expectation=expectation,
            evaluation=evaluation,
            evidence=evidence,
            context=context,
        )
    owned = BedrockMismatchInvestigator()
    try:
        return owned.investigate_mismatch(
            expectation=expectation,
            evaluation=evaluation,
            evidence=evidence,
            context=context,
        )
    finally:
        owned.close()
