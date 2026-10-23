"""Replay/ownership boundary; delegates all interpretation to canonical services."""

import hashlib
import hmac
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models.compilation_session import CompilationSession
from app.db.models.expectation import Expectation
from app.mcp.conversation_state import StateError, decode_state, encode_state
from app.schemas.clarification import (
    ClarificationState,
    ClarificationStatus,
    ClarificationTurn,
)
from app.schemas.expectation import ExpectationCreate
from app.services import expectation_service


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def existing_start(
    db: Session, session_id: UUID, user_id: UUID
) -> ClarificationState | None:
    # Serialize starts across workers, including before a row exists.
    lock = int.from_bytes(
        hashlib.sha256(session_id.bytes).digest()[:8], "big", signed=True
    )
    db.execute(select(func.pg_advisory_xact_lock(lock)))
    row = db.get(CompilationSession, session_id)
    if row is None:
        return None
    if row.user_id != user_id:
        raise StateError("CLARIFICATION_EXPIRED")
    state = ClarificationState.model_validate(row.state)
    if datetime.now(timezone.utc) >= state.expires_at:
        raise StateError("CLARIFICATION_EXPIRED")
    if state.status not in (ClarificationStatus.ACTIVE, ClarificationStatus.COMPILED):
        raise StateError("CLARIFICATION_EXPIRED")
    return state


def locked_state(
    db: Session, token: str, user_id: UUID
) -> tuple[CompilationSession, ClarificationState]:
    state = decode_state(token, user_id, get_settings())
    row = db.scalar(
        select(CompilationSession)
        .where(
            CompilationSession.id == state.session_id,
            CompilationSession.user_id == user_id,
        )
        .with_for_update()
    )
    if row is None or not hmac.compare_digest(row.token_digest, digest(token)):
        raise StateError("CLARIFICATION_EXPIRED")
    return row, ClarificationState.model_validate(row.state)


def save_turn(
    db: Session,
    turn: ClarificationTurn,
    user_id: UUID,
    row: CompilationSession | None = None,
) -> str:
    state = turn.state
    if row is not None and row.id != state.session_id:
        assert turn.replaced_state is not None
        row.state = turn.replaced_state.model_dump(mode="json")
        row.token_digest = ""  # Replaced conversation cannot be resumed.
        row = None
    token = encode_state(state, user_id, get_settings())
    if row is None:
        row = CompilationSession(id=state.session_id, user_id=user_id)
        db.add(row)
    row.state = state.model_dump(mode="json")
    row.token_digest = digest(token)
    row.expires_at = state.expires_at
    db.commit()
    return token


def capture_compiled(
    db: Session, payload: ExpectationCreate, token: str, user_id: UUID
) -> Expectation:
    row, state = locked_state(db, token, user_id)
    if (
        state.status != ClarificationStatus.COMPILED
        or datetime.now(timezone.utc) >= state.expires_at
    ):
        raise StateError("CLARIFICATION_EXPIRED")
    if state.compiled_expectation != payload:
        raise StateError()
    if row.expectation_id is not None:
        return expectation_service.get_expectation(db, row.expectation_id, user_id)
    try:
        expectation = expectation_service.create_expectation(
            db, payload, user_id, commit=False
        )
        row.expectation_id = expectation.id
        db.commit()  # One atomic transaction: row + lifecycle consumption.
        return expectation
    except Exception:
        db.rollback()
        raise
