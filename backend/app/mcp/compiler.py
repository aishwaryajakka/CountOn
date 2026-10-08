"""MCP compatibility seam; interpretation is implemented by the application service."""

from dataclasses import dataclass
from datetime import datetime

from app.core.auth import AuthenticatedUser
from app.schemas.compiler import CompileContext, CompileOutcome
from app.schemas.expectation import ExpectationCreate
from app.services.compiler_service import (
    ExpectationCompiler,  # re-export canonical protocol
)

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


def compile_expectation(text: str, context: CompilationContext) -> CompileOutcome:
    """Strip ownership before interpretation. This does not capture or persist.

    Kept for orchestration callers using the original authenticated context;
    canonical compiler context excludes user identity and credentials.
    """
    from app.services.compiler_service import compile_expectation as compile_service

    return compile_service(
        text,
        CompileContext(
            current_time=context.reference_time,
            timezone=context.timezone,
        ),
    )


__all__ = [
    "CompilationContext",
    "ExpectationCompiler",
    "StructuredExpectation",
    "compile_expectation",
]
