"""Whitelisted run metadata using the existing audit_events table."""

from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.actions import AgentAction, AgentStatus
from app.agent.models import AgentResult
from app.core.auth import AuthenticatedUser
from app.db.models.compilation_session import CompilationSession
from app.db.models.expectation import Expectation
from app.db.session import SessionLocal
from app.mcp.compilation_lifecycle import digest
from app.repositories import audit


def record_run(
    db: Session, user: AuthenticatedUser, result: AgentResult, duration_ms: int,
    *, channel: Literal["ALEXA", "ALEXA_WEB"] | None = None,
) -> None:
    trust = result.trust
    if trust is None:
        raise ValueError("A completed trust receipt is required")
    origin = {"ALEXA": "alexa_skill", "ALEXA_WEB": "alexa_web", None: "web"}[channel]
    provider = channel or "WEB"
    expectation = None
    if trust.expectation_id is not None:
        expectation = db.get(Expectation, trust.expectation_id)
        if expectation is None or expectation.user_id != user.id:
            raise ValueError("Audit expectation must belong to the authenticated user")
    explained = result.explanation
    receipt = explained.provenance if explained and trust.safe_to_say else None
    # Correlate only through owned persisted compilation rows, never by decoding
    # or storing a bearer-like draft/transport token or guessing the latest draft.
    draft = result.clarification_state or result.capture_state
    compilation_reference = trust.run_id
    if draft is not None or result.captured:
        predicate = (
            CompilationSession.token_digest == digest(draft.get_secret_value())
            if draft is not None else CompilationSession.expectation_id == trust.expectation_id
        )
        matches = list(db.scalars(select(CompilationSession.id).where(
            CompilationSession.user_id == user.id, predicate,
        ).limit(2)))
        if len(matches) == 1:
            compilation_reference = matches[0]
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
            "channel": origin,
            "reason": result.code.value if result.code else None,
        },
        actor_type="USER",
        source_provider=provider,
        source_type="VOICE" if channel == "ALEXA" else "CONVERSATION",
        source_provenance="SIGNED_ASK" if channel == "ALEXA" else "AUTHENTICATED_WEB",
        idempotency_key=f"ORCHESTRATION:{trust.run_id}",
    )
    if result.action in (
        AgentAction.COMPILE_EXPECTATION, AgentAction.CONTINUE_CLARIFICATION,
        AgentAction.CAPTURE_EXPECTATION, AgentAction.CANCEL,
    ):
        lifecycle_status = (
            "completed" if result.captured
            else "cancelled" if result.status == AgentStatus.CANCELLED
            else "pending" if result.clarification_required or result.confirmation_required
            else "failed"
        )
        audit.record(  # type: ignore[no-untyped-call]
            db, user.id, "clarification", trust.run_id, "clarification.updated",
            trust.expectation_id,
            {"run_id": str(trust.run_id), "action": result.action.value,
             "status": lifecycle_status, "channel": origin},
            actor_type="USER", source_provider=provider,
            source_type="VOICE" if channel == "ALEXA" else "CONVERSATION",
            source_provenance="SIGNED_ASK" if channel == "ALEXA" else "AUTHENTICATED_WEB",
            source_reference=compilation_reference,
            idempotency_key=f"CLARIFICATION_UPDATED:{trust.run_id}",
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
        audit.record(  # type: ignore[no-untyped-call]
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
                "channel": origin,
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
        assert expectation is not None
        # Only the authenticated server adapter supplies this origin. The MCP
        # creation event remains intact; confirmation adds the parent channel.
        if expectation.compiler_metadata.get("creation_source") in (None, "mcp"):
            expectation.compiler_metadata = {
                **expectation.compiler_metadata, "creation_source": origin,
            }
        audit.record(  # type: ignore[no-untyped-call]
            db, user.id, "expectation", trust.expectation_id,
            "expectation.confirmed", trust.expectation_id,
            {"channel": origin, "status": "SUCCESS"},
            actor_type="USER", source_provider=provider,
            source_type="VOICE" if channel == "ALEXA" else "CONVERSATION",
            source_provenance="SIGNED_ASK" if channel == "ALEXA" else "AUTHENTICATED_WEB",
            idempotency_key=f"EXPECTATION_CONFIRMED:{trust.expectation_id}",
        )
    db.commit()


def persist_run(user: AuthenticatedUser, result: AgentResult, duration_ms: int) -> None:
    with SessionLocal() as db:
        record_run(db, user, result, duration_ms, channel="ALEXA")
