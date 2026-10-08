"""Authenticated high-level MCP intelligence adapters; capture remains separate."""

from datetime import datetime, timezone
from typing import Literal, cast
from uuid import UUID

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import EvaluationNotFoundError
from app.evaluators.base import EvaluationResult
from app.mcp.compilation_lifecycle import existing_start, locked_state, save_turn
from app.mcp.conversation_state import (
    StateError,
    decode_state,
    encode_state,
    signing_key,
)
from app.mcp.schemas import (
    CompilationResult,
    CompileExpectationInput,
    ContinueCompilationInput,
    ExplainMismatchInput,
    ExplanationResult,
)
from app.repositories import evidence as evidence_repository
from app.schemas.clarification import ClarificationStatus, ClarificationTurn
from app.schemas.compiler import CannotCompile, CompileContext
from app.schemas.evaluation import EvaluationResponse
from app.schemas.evidence import EvidenceResponse
from app.schemas.expectation import ExpectationResponse
from app.schemas.investigation import InvestigationContext
from app.services import (
    compiler_service,
    evaluation_service,
    expectation_service,
    investigation_service,
)


def public_turn(turn: ClarificationTurn, user_id: UUID) -> CompilationResult:
    state = turn.state
    status = {
        ClarificationStatus.ACTIVE: "clarification",
        ClarificationStatus.COMPILED: "compiled",
        ClarificationStatus.CANCELLED: "cancelled",
        ClarificationStatus.EXPIRED: "expired",
        ClarificationStatus.FAILED: "error",
    }[state.status]
    code = (
        (turn.error_code or "COMPILER_INVALID_OUTPUT")
        if status == "error"
        else "CLARIFICATION_REQUIRED"
        if status == "clarification"
        else "CLARIFICATION_EXPIRED"
        if status == "expired"
        else None
    )
    if isinstance(turn.outcome, CannotCompile):
        status, code = "unsupported", "UNSUPPORTED_EXPECTATION"
    return CompilationResult(
        status=cast(
            Literal[
                "compiled",
                "clarification",
                "cancelled",
                "expired",
                "unsupported",
                "error",
            ],
            status,
        ),
        message=turn.message,
        expectation=state.compiled_expectation,
        state=encode_state(state, user_id, get_settings())
        if status == "clarification"
        else None,
        code=code,
        bedrock_used=turn.bedrock_used,
        prompt_version=state.compiler_prompt_version,
        clarification_turn=state.turn_count,
    )


def compile_request(
    request: CompileExpectationInput, user_id: UUID, db: Session | None = None
) -> CompilationResult:
    settings = get_settings()
    if not settings.bedrock_enabled:
        return CompilationResult(
            status="error",
            message="I couldn't interpret that expectation right now. Please try again.",
            code="BEDROCK_DISABLED",
            prompt_version="v2",
        )
    signing_key(
        settings
    )  # Fail before a paid inference when production state config is missing.
    context = CompileContext(
        current_time=datetime.now(timezone.utc),
        timezone=request.timezone,
        locale=request.locale,
    )
    if db is not None and request.compilation_id is not None:
        previous = existing_start(db, request.compilation_id, user_id)
        if previous is not None:
            token = encode_state(previous, user_id, settings)
            return CompilationResult(
                status="compiled"
                if previous.status == ClarificationStatus.COMPILED
                else "clarification",
                message=previous.question or "Your expectation is ready.",
                expectation=previous.compiled_expectation,
                state=token if previous.status == ClarificationStatus.ACTIVE else None,
                capture_state=token
                if previous.status == ClarificationStatus.COMPILED
                else None,
                prompt_version=previous.compiler_prompt_version,
                clarification_turn=previous.turn_count,
            )
    turn = (
        compiler_service.start_expectation_compilation(
            request.text, context, require_timing=True
        )
        if request.conversational
        else compiler_service.start_expectation_compilation(request.text, context)
    )
    if request.compilation_id is not None:
        turn.state.session_id = request.compilation_id
    result = public_turn(turn, user_id)
    if db is not None:
        token = save_turn(db, turn, user_id)
        result.state = token if result.status == "clarification" else None
        result.capture_state = token if result.status == "compiled" else None
    return result


def continue_request(
    request: ContinueCompilationInput, user_id: UUID, db: Session | None = None
) -> CompilationResult:
    row = None
    if db is not None:
        row, state = locked_state(db, request.state, user_id)
        if state.status != ClarificationStatus.ACTIVE:
            raise StateError("CLARIFICATION_EXPIRED")
    else:
        state = decode_state(request.state, user_id, get_settings())
    context = CompileContext(
        current_time=datetime.now(timezone.utc),
        timezone=state.timezone,
        locale=state.locale,
    )
    turn = compiler_service.continue_expectation_compilation(
        state, request.answer, context
    )
    result = public_turn(turn, user_id)
    if db is not None:
        token = save_turn(db, turn, user_id, row)
        result.state = token if result.status == "clarification" else None
        result.capture_state = token if result.status == "compiled" else None
    return result


def explain_request(
    db: Session, request: ExplainMismatchInput, user_id: UUID
) -> ExplanationResult:
    expectation = expectation_service.get_expectation(
        db, request.expectation_id, user_id
    )
    try:
        evaluation = evaluation_service.get_latest_evaluation(
            db, request.expectation_id, user_id
        )
    except EvaluationNotFoundError:
        return ExplanationResult(
            expectation_id=expectation.id,
            message="I'm still waiting for an evaluation of this expectation.",
            code="NO_EVALUATION",
        )
    if evaluation.result != EvaluationResult.MISMATCH:
        return ExplanationResult(
            expectation_id=expectation.id,
            result=evaluation.result,
            evaluation_id=evaluation.id,
            code="NOT_MISMATCH",
            message="It matched your expectation."
            if evaluation.result == EvaluationResult.MATCH
            else "I'm still watching. CountOn doesn't have enough evidence to say whether it matched yet.",
        )
    evidence = evidence_repository.investigation_evidence(
        db, expectation.id, evaluation
    )
    explained = investigation_service.investigate_mismatch(
        expectation=ExpectationResponse.model_validate(expectation),
        evaluation=EvaluationResponse.model_validate(evaluation),
        evidence=[EvidenceResponse.model_validate(row) for row in evidence],
        context=InvestigationContext(authenticated_user_id=user_id),
    )
    # Speech is rendered from accepted, grounded facts only. Keep provenance and
    # technical caveats available in the structured result, outside normal speech.
    speech = (
        explained.summary.split(" Recorded materiality threshold:")[0]
        .split(" There isn't enough")[0]
        .split(" The available evidence")[0]
        .replace("CountOn recorded MISMATCH:", "Your recorded result didn't match:")
    )
    contribution = next(
        (
            factor
            for factor in explained.key_factors
            if factor.strength == "possible_contribution"
        ),
        None,
    )
    for symbol, words in (
        ("≤", "at most"),
        ("≥", "at least"),
        ("≠", "not equal to"),
        ("<", "less than"),
        (">", "greater than"),
        ("=", "equal to"),
    ):
        speech = speech.replace(f"expected {symbol} ", f"expected {words} ")
    if contribution is not None:
        speech += " " + contribution.description.replace(
            "The higher rate could have contributed to the bill mismatch; these observations do not establish a net effect or cause.",
            "The higher rate could have contributed, but I can't confirm the exact cause.",
        )
    elif explained.insufficient_evidence:
        speech += " I don't have enough supporting evidence to explain why yet."
    if any("conflicting" in caveat for caveat in explained.caveats):
        speech += " The available evidence is conflicting, so I can't identify a cause."
    return ExplanationResult(
        expectation_id=expectation.id,
        result=evaluation.result,
        evaluation_id=evaluation.id,
        explanation=explained,
        message=speech,
        evidence_ids=[ref.evidence_id for ref in explained.evidence_refs],
        fallback_used=explained.generation == "deterministic",
        bedrock_used=explained.generation == "bedrock",
        code=None
        if explained.generation == "bedrock"
        else "NO_EVIDENCE"
        if not explained.evidence_refs
        else "INVESTIGATION_UNAVAILABLE",
    )
