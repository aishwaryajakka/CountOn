"""Deterministic speech checks and receipts; no inference and no database access."""

import re
from uuid import UUID, uuid4

from pydantic import ValidationError

from app.agent.actions import AgentStatus, FailureCode
from app.agent.models import AgentResult, TrustResponse
from app.evaluators.base import EvaluationResult
from app.schemas.trust import EvidenceProvenance

SENSITIVE = re.compile(
    r"authorization\s*:|bearer\s+\S+|eyJ[A-Za-z0-9_-]{10,}\."
    r"|(?:postgres(?:ql)?|mysql)(?:\+\w+)?://|(?:AKIA|ASIA)[A-Z0-9]{16}"
    r"|(?:AWS_SECRET_ACCESS_KEY|AWS_ACCESS_KEY_ID|DATABASE_URL|signing_key)\s*[:=]"
    r"|-----BEGIN .*PRIVATE KEY|[A-Za-z0-9_-]{100,}\.[0-9a-f]{64}"
    r"|<\s*(?:script|iframe)\b|\b(?:chain[- ]of[- ]thought|hidden prompt)\s*:",
    re.IGNORECASE,
)


def speech_is_safe(result: AgentResult) -> bool:
    if SENSITIVE.search(result.message) or any(
        ord(char) < 32 and char not in "\n\t" for char in result.message
    ):
        return False
    if result.captured and (
        result.status != AgentStatus.SUCCESS
        or result.expectation is None
        or result.compiled_expectation is None
    ):
        return False
    explained = result.explanation
    if explained is not None:
        try:
            receipt = EvidenceProvenance.model_validate(
                explained.provenance.model_dump()
            )
        except ValidationError:
            return False
        if tuple(explained.evidence_ids) != receipt.used:
            return False
        if explained.result == EvaluationResult.MISMATCH:
            if explained.evaluation_id is None or explained.explanation is None:
                return False
            if (
                tuple(ref.evidence_id for ref in explained.explanation.evidence_refs)
                != receipt.used
            ):
                return False
            if explained.bedrock_used != (explained.explanation.generation == "bedrock"):
                return False
            if explained.bedrock_used and receipt.grounding_passed is not True:
                return False
        elif (
            explained.bedrock_used or explained.explanation is not None or receipt.used
        ):
            return False
    return True


def finish(result: AgentResult, run_id: UUID | None = None) -> AgentResult:
    """Reject unsafe speech while preserving a confirmed save's identity (no retry)."""
    safe = speech_is_safe(result)
    if not safe and not result.captured:
        result = result.model_copy(
            update={"status": AgentStatus.FAILED, "code": FailureCode.PROTOCOL_ERROR}
        )
    explained = result.explanation
    receipt = explained.provenance if explained and safe else EvidenceProvenance()
    answer = (
        result.message
        if safe
        else (
            "I couldn't safely explain that response. Check your CountOn records before retrying a save."
        )
    )
    trust = TrustResponse(
        answer=answer,
        status=result.status,
        evaluator_result=explained.result if explained and safe else None,
        expectation_id=result.expectation_id if safe or result.expectation else None,
        sources_used=receipt.sources_used,
        evidence_ids=receipt.used,
        bedrock_used=result.bedrock_used,
        fallback_used=result.fallback_used or not safe,
        grounded=safe
        and (
            explained is not None
            or result.expectation is not None
            or result.expectations is not None
        ),
        safe_to_say=safe,
        run_id=run_id or uuid4(),
    )
    return result.model_copy(
        update={"message": answer, "trust": trust, "fallback_used": trust.fallback_used}
    )
