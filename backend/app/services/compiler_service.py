"""Pure application entry point; no SDK, MCP, database or mutation orchestration."""

from typing import TYPE_CHECKING, Protocol

from app.ai.expectation_compiler import BedrockExpectationCompiler
from app.schemas.clarification import ClarificationState, ClarificationTurn
from app.schemas.compiler import CompileContext, CompileOutcome

if TYPE_CHECKING:
    from app.ai.clarification import ClarificationEngine


class ExpectationCompiler(Protocol):
    def compile_expectation(
        self, text: str, context: CompileContext
    ) -> CompileOutcome: ...


def compile_expectation(
    text: str, context: CompileContext, *, compiler: ExpectationCompiler | None = None
) -> CompileOutcome:
    """Return interpretation only. Future orchestration captures via authenticated MCP.

    Inject a compiler for tests; otherwise the lazy Bedrock adapter is owned and
    closed here. No route or MCP tool is introduced by this service.
    """
    if compiler is not None:
        return compiler.compile_expectation(text, context)
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
    """Trusted application state only; no browser endpoint or persistence."""
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
    """Only continue trusted state held by the application under the same user."""
    from app.ai.clarification import ClarificationEngine

    owned = engine is None
    selected = engine or ClarificationEngine()
    try:
        return selected.continue_compilation(state, user_response, context)
    finally:
        if owned:
            selected.close()
