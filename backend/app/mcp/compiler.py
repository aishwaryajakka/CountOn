"""Person 2 compiler contract only; no compiler implementation or MCP tool."""
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.core.auth import AuthenticatedUser
from app.schemas.expectation import ExpectationCreate

# Reuse the actual persistence input; never introduce a competing schema.
StructuredExpectation = ExpectationCreate


@dataclass(frozen=True)
class CompilationContext:
    """Trusted orchestration context, never extracted from tool arguments.

    reference_time must be timezone-aware; timezone is the verified user's
    IANA timezone. No credentials or raw provider data belong in this object.
    """
    user: AuthenticatedUser
    reference_time: datetime
    timezone: str


class ExpectationCompiler(Protocol):
    def compile_expectation(
        self, text: str, context: CompilationContext,
    ) -> StructuredExpectation:
        """Compile without persisting; ask for clarification if facts are missing.

        Person 2 supplies this implementation. The orchestrator validates the
        returned model and submits it to capture under the same verified user.
        Compiler output never controls ownership or authentication.
        """
        ...
