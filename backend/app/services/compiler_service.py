"""Expectation compilation service orchestrating AI compiler and persistence."""

from uuid import UUID
from sqlalchemy.orm import Session

from app.ai.compiler import compile_expectation
from app.ai.models.expectation import ExpectationCompilationResult
from app.db.models.expectation import Expectation as DBExpectation, ExpectationType, ComparisonType
from app.schemas.expectation import ExpectationCreate
from app.services import expectation_service


def compile_statement(text: str, mock_mode: bool | None = None) -> ExpectationCompilationResult:
    """Runs the AI compiler on natural language input."""
    return compile_expectation(text, mock_mode=mock_mode)


def compile_and_save(db: Session, text: str, user_id: UUID, mock_mode: bool | None = None) -> DBExpectation | ExpectationCompilationResult:
    """Compiles natural language statement and persists to DB if compilation is successful."""
    result = compile_expectation(text, mock_mode=mock_mode)
    if result.kind == "clarification" or not result.expectation:
        return result

    compiled = result.expectation

    # Map compiled type and comparison to DB enums
    exp_create = ExpectationCreate(
        claim=compiled.claim,
        type=ExpectationType(compiled.type) if compiled.type in ExpectationType.__members__ else ExpectationType.event,
        metric=compiled.metric,
        comparison=ComparisonType(compiled.comparison) if compiled.comparison and compiled.comparison in ComparisonType.__members__ else None,
        baseline=compiled.baseline,
        deadline=None, # ISO datetime string parsing can be added if deadline matches timestamp
        evidence_sources=compiled.evidence_sources,
        materiality_threshold=compiled.materiality_threshold,
    )
    return expectation_service.create_expectation(db, exp_create, user_id)
