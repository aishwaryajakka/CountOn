"""Whitelisted run metadata using the existing audit_events table."""

from sqlalchemy.orm import Session

from app.agent.models import AgentResult
from app.core.auth import AuthenticatedUser
from app.db.models.expectation import Expectation
from app.db.session import SessionLocal
from app.repositories import audit


def record_run(
    db: Session, user: AuthenticatedUser, result: AgentResult, duration_ms: int,
    *, channel: str | None = None,
) -> None:
    trust = result.trust
    if trust is None:
        raise ValueError("A completed trust receipt is required")
    if trust.expectation_id is not None:
        expectation = db.get(Expectation, trust.expectation_id)
        if expectation is None or expectation.user_id != user.id:
            raise ValueError("Audit expectation must belong to the authenticated user")
    explained = result.explanation
    receipt = explained.provenance if explained and trust.safe_to_say else None
    # Construct explicitly. Never serialize AgentInput, AgentResult, or state.
    audit.record(
        db,
        user_id=user.id,
        entity_type="orchestration",  # type: ignore[no-untyped-call]
        entity_id=trust.run_id,
        action=result.action.value,
        expectation_id=trust.expectation_id,
        metadata={
            "run_id": str(trust.run_id),
            "action": result.action.value,
            "capabilities": [tool.value for tool in result.invoked_capabilities],
            "evaluator_result": trust.evaluator_result.value
            if trust.evaluator_result
            else None,
            "evaluation_id": str(explained.evaluation_id)
            if explained and explained.evaluation_id
            else None,
            "evidence_ids": [str(identity) for identity in trust.evidence_ids],
            "sources_used": [source.value for source in trust.sources_used],
            "source_decisions": [
                decision.model_dump(mode="json") for decision in receipt.decisions
            ]
            if receipt
            else [],
            "bedrock_used": trust.bedrock_used,
            "bedrock_attempted": receipt.bedrock_attempted
            if receipt
            else result.bedrock_used,
            "fallback_used": trust.fallback_used,
            "grounded": trust.grounded,
            "model_grounding_passed": receipt.grounding_passed if receipt else None,
            "safe_to_say": trust.safe_to_say,
            "duration_ms": max(0, duration_ms),
            "status": trust.status.value,
        },
        actor_type="USER",
        source_provider=channel,
        source_type="VOICE" if channel == "ALEXA" else "CONVERSATION",
        source_provenance="SIGNED_ASK" if channel == "ALEXA" else "AUTHENTICATED_WEB",
    )
    if (
        explained is not None
        and explained.explanation is not None
        and explained.evaluation_id is not None
        and trust.safe_to_say
    ):
        # Record the accepted explanation envelope, never its speech, prompt,
        # model response, or evidence values. The linked IDs and grounding flags
        # are sufficient for provenance and operational review.
        audit.record(
            db,
            user_id=user.id,
            entity_type="explanation",
            entity_id=explained.evaluation_id,
            action="explanation.generated",
            expectation_id=trust.expectation_id,
            metadata={
                "run_id": str(trust.run_id),
                "evaluation_id": str(explained.evaluation_id),
                "evidence_ids": [str(identity) for identity in trust.evidence_ids],
                "sources_used": [source.value for source in trust.sources_used],
                "bedrock_used": trust.bedrock_used,
                "bedrock_attempted": receipt.bedrock_attempted if receipt else False,
                "fallback_used": trust.fallback_used,
                "grounded": trust.grounded,
                "model_grounding_passed": receipt.grounding_passed if receipt else None,
                "safe_to_say": trust.safe_to_say,
            },
            actor_type="SYSTEM",
            source_type="GROUNDED_EXPLANATION",
            source_provenance="BEDROCK"
            if trust.bedrock_used
            else "DETERMINISTIC_FALLBACK",
            evidence_id=trust.evidence_ids[0] if trust.evidence_ids else None,
            evaluation_id=explained.evaluation_id,
            result_status=trust.evaluator_result.value
            if trust.evaluator_result
            else None,
            idempotency_key=f"EXPLANATION_GENERATED:{trust.run_id}",
        )
    if result.captured and trust.expectation_id is not None:
        audit.record(
            db, user.id, "expectation", trust.expectation_id,
            "expectation.confirmed", trust.expectation_id, {},
            actor_type="USER", source_provider=channel,
            source_type="VOICE" if channel == "ALEXA" else "CONVERSATION",
            source_provenance="SIGNED_ASK" if channel == "ALEXA" else "AUTHENTICATED_WEB",
            idempotency_key=f"EXPECTATION_CONFIRMED:{trust.expectation_id}",
        )
    db.commit()


def persist_run(user: AuthenticatedUser, result: AgentResult, duration_ms: int) -> None:
    with SessionLocal() as db:
        record_run(db, user, result, duration_ms, channel="ALEXA")
