"""Thin service adapters; services and repositories own all persistence rules."""

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from time import perf_counter
from typing import TypeVar
from uuid import UUID

from mcp.server import MCPServer
from mcp.server.mcpserver import Context
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import ToolAnnotations
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser
from app.core.exceptions import (
    AuthenticationError,
    ExpectationNotFoundError,
    InvalidExpectationError,
)
from app.db.session import SessionLocal
from app.mcp import intelligence
from app.mcp.auth import current_user
from app.mcp.compilation_lifecycle import capture_compiled
from app.mcp.conversation_state import StateError
from app.mcp.schemas import (
    CaptureExpectationInput,
    CompilationResult,
    CompileExpectationInput,
    ContinueCompilationInput,
    ExpectationListResult,
    ExpectationResult,
    ExplainMismatchInput,
    ExplanationResult,
    GetExpectationInput,
    ListExpectationsInput,
)
from app.schemas.expectation import ExpectationCreate
from app.services import expectation_service

SessionFactory = Callable[[], AbstractContextManager[Session]]
UserResolver = Callable[[Context], AuthenticatedUser]
logger = logging.getLogger(__name__)
ResultT = TypeVar("ResultT")


def register_tools(
    server: MCPServer,
    session_factory: SessionFactory = SessionLocal,
    user_resolver: UserResolver = current_user,
) -> None:
    def run(context: Context, tool_name: str, operation: Callable[[Session, UUID], ResultT]) -> ResultT:
        started = perf_counter()
        user = None
        result_status = "error"
        try:
            user = user_resolver(context)
            with session_factory() as db:
                result = operation(db, user.id)
                result_status = "success"
                return result
        except AuthenticationError:
            result_status = "unauthorized"
            raise ToolError("UNAUTHORIZED: A valid CountOn bearer token is required.") from None
        except ExpectationNotFoundError:
            result_status = "not_found"
            # Identical for nonexistent and another user's IDs.
            raise ToolError("NOT_FOUND: Expectation not found.") from None
        except InvalidExpectationError:
            result_status = "invalid_expectation"
            raise ToolError("INVALID_EXPECTATION: Numeric expectations require metric, comparison, and baseline or target_value.") from None
        except StateError as error:
            result_status = "invalid_state"
            raise ToolError(f"{error.code}: This clarification cannot continue. Please start again.") from None
        except SQLAlchemyError:
            result_status = "database_error"
            raise ToolError("DATABASE_ERROR: The operation could not be completed. Try again later.") from None
        except Exception:  # noqa: BLE001 -- transport boundary must mask private failures
            raise ToolError("SERVICE_ERROR: The operation could not be completed.") from None
        finally:
            logger.info("MCP tool completed", extra={
                "tool_name": tool_name, "user_id": str(user.id) if user else None,
                "result_status": result_status,
                "duration_ms": round((perf_counter() - started) * 1000, 2),
            })

    @server.tool(description="Stores a structured expectation the current user wants CountOn to monitor.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=False))
    def capture_expectation(request: CaptureExpectationInput, ctx: Context) -> ExpectationResult:
        def capture(db: Session, user_id: UUID) -> ExpectationResult:
            payload = ExpectationCreate.model_validate(request.model_dump(exclude={"compilation_state"}))
            row = capture_compiled(db, payload, request.compilation_state, user_id) if request.compilation_state else expectation_service.create_expectation(db, payload, user_id)
            return ExpectationResult.model_validate(row)
        return run(ctx, "capture_expectation", capture)

    @server.tool(description="Returns one expectation and its current status.",
        annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
    def get_expectation(request: GetExpectationInput, ctx: Context) -> ExpectationResult:
        return run(ctx, "get_expectation", lambda db, user_id: ExpectationResult.model_validate(
            expectation_service.get_expectation(db, request.expectation_id, user_id)))

    @server.tool(description="Lists the current user's expectations.",
        annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False))
    def list_expectations(request: ListExpectationsInput, ctx: Context) -> ExpectationListResult:
        return run(ctx, "list_expectations", lambda db, user_id: ExpectationListResult(
            expectations=[ExpectationResult.model_validate(row) for row in
                expectation_service.list_expectations(db, user_id, request.status,
                    request.limit, request.offset, request.type)],
            limit=request.limit, offset=request.offset))

    @server.tool(description="Interprets a new expectation without saving it; asks for missing information when needed.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True))
    def compile_expectation(request: CompileExpectationInput, ctx: Context) -> CompilationResult:
        return run(ctx, "compile_expectation", lambda db, user_id: intelligence.compile_request(request, user_id, db))

    @server.tool(description="Continues or cancels an expectation clarification without saving an expectation.",
        annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, idempotent_hint=False, open_world_hint=True))
    def continue_expectation_compilation(request: ContinueCompilationInput, ctx: Context) -> CompilationResult:
        return run(ctx, "continue_expectation_compilation", lambda db, user_id: intelligence.continue_request(request, user_id, db))

    @server.tool(description="Explains a recorded mismatch using available evidence; never changes the evaluation.",
        annotations=ToolAnnotations(read_only_hint=True, destructive_hint=False, idempotent_hint=False, open_world_hint=True))
    def explain_expectation_mismatch(request: ExplainMismatchInput, ctx: Context) -> ExplanationResult:
        return run(ctx, "explain_expectation_mismatch", lambda db, user_id: intelligence.explain_request(db, request, user_id))
