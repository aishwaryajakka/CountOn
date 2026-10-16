"""
Expectation compilation service orchestrating AI compiler, time parsing, persistence,
and canonical clarification & interpretation protocols.
"""

from typing import TYPE_CHECKING, Any, Protocol
from uuid import UUID
from sqlalchemy.orm import Session

from app.ai.compiler import compile_expectation as ai_compile_expectation
from app.ai.models.expectation import ExpectationCompilationResult
from app.ai.time_parser import parse_relative_deadline
from app.db.models.expectation import Expectation as DBExpectation, ExpectationType, ComparisonType, ExpectationStatus
from app.schemas.expectation import ExpectationCreate, ExpectationUpdate
from app.schemas.compiler import CompileContext, CompileOutcome
from app.schemas.clarification import ClarificationState, ClarificationTurn
from app.services import expectation_service

if TYPE_CHECKING:
    from app.ai.clarification import ClarificationEngine


class ExpectationCompiler(Protocol):
    def compile_expectation(
        self, text: str, context: CompileContext
    ) -> CompileOutcome: ...


def compile_statement(
    text: str,
    mock_mode: bool | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    draft_expectation: dict[str, Any] | None = None,
    expectation_id: UUID | str | None = None,
) -> ExpectationCompilationResult:
    """Runs the AI compiler on natural language input with multi-turn memory support."""
    return ai_compile_expectation(
        user_text=text,
        mock_mode=mock_mode,
        conversation_history=conversation_history,
        draft_expectation=draft_expectation,
        expectation_id=str(expectation_id) if expectation_id else None,
    )


def compile_and_save(
    db: Session,
    text: str,
    user_id: UUID,
    mock_mode: bool | None = None,
    conversation_history: list[dict[str, str]] | None = None,
    draft_expectation: dict[str, Any] | None = None,
    expectation_id: UUID | str | None = None,
) -> DBExpectation | ExpectationCompilationResult:
    """
    Compiles natural language statement with multi-turn history.
    Handles relative deadline parsing, corrections to existing expectations, and cancellations.
    """
    result = compile_statement(
        text=text,
        mock_mode=mock_mode,
        conversation_history=conversation_history,
        draft_expectation=draft_expectation,
        expectation_id=expectation_id,
    )

    if result.kind == "clarification":
        return result

    # 1. Handle Cancellation request
    if result.kind == "cancellation":
        target_id_str = (result.cancellation.expectation_id if result.cancellation else None) or (
            str(expectation_id) if expectation_id else None
        )
        if target_id_str:
            try:
                target_uuid = UUID(target_id_str)
                expectation_service.update_expectation(
                    db=db,
                    expectation_id=target_uuid,
                    payload=ExpectationUpdate(status=ExpectationStatus.cancelled),
                    user_id=user_id,
                )
            except Exception:
                pass
        return result

    if not result.expectation:
        return result

    compiled = result.expectation

    # 2. Parse relative or ISO deadline string into timezone-aware UTC datetime
    parsed_deadline = parse_relative_deadline(compiled.deadline)

    # 3. Handle Corrections / Updates to an existing expectation
    target_update_id = compiled.id or (str(expectation_id) if expectation_id else None)
    if result.is_correction and target_update_id:
        try:
            update_uuid = UUID(target_update_id)
            exp_update = ExpectationUpdate(
                claim=compiled.claim,
                metric=compiled.metric,
                comparison=(
                    ComparisonType(compiled.comparison)
                    if compiled.comparison and compiled.comparison in ComparisonType.__members__
                    else None
                ),
                baseline=compiled.baseline,
                deadline=parsed_deadline,
                evidence_sources=compiled.evidence_sources,
                materiality_threshold=compiled.materiality_threshold,
            )
            return expectation_service.update_expectation(db, update_uuid, exp_update, user_id)
        except Exception:
            # Fall back to creating if existing row was not found
            pass

    # 4. Standard Expectation Creation
    exp_create = ExpectationCreate(
        claim=compiled.claim,
        type=ExpectationType(compiled.type) if compiled.type in ExpectationType.__members__ else ExpectationType.event,
        metric=compiled.metric,
        comparison=(
            ComparisonType(compiled.comparison)
            if compiled.comparison and compiled.comparison in ComparisonType.__members__
            else None
        ),
        baseline=compiled.baseline,
        deadline=parsed_deadline,
        evidence_sources=compiled.evidence_sources,
        materiality_threshold=compiled.materiality_threshold,
    )
    return expectation_service.create_expectation(db, exp_create, user_id)


def compile_expectation(
    text: str, context: CompileContext, *, compiler: ExpectationCompiler | None = None
) -> CompileOutcome:
    """Return interpretation only. Canonical entry point from feature branch."""
    if compiler is not None:
        return compiler.compile_expectation(text, context)
    from app.ai.expectation_compiler import BedrockExpectationCompiler
    owned = BedrockExpectationCompiler()
    try:
        return owned.compile_expectation(text, context)
    finally:
        owned.close()


def start_expectation_compilation(
    text: str,
    context: CompileContext,
    *,
    engine: "ClarificationEngine | None" = None,
    require_timing: bool = False,
) -> ClarificationTurn:
    """Trusted application state clarification turn starter."""
    from app.ai.clarification import ClarificationEngine

    owned = engine is None
    selected = engine or ClarificationEngine()
    try:
        return selected.start(
            text, context, **({"require_timing": True} if require_timing else {})
        )
    finally:
        if owned:
            selected.close()


def continue_expectation_compilation(
    state: ClarificationState,
    user_response: str,
    context: CompileContext,
    *,
    engine: "ClarificationEngine | None" = None,
) -> ClarificationTurn:
    """Trusted application state clarification turn continuer."""
    from app.ai.clarification import ClarificationEngine

    owned = engine is None
    selected = engine or ClarificationEngine()
    try:
        return selected.continue_clarification(state, user_response, context)
    finally:
        if owned:
            selected.close()
