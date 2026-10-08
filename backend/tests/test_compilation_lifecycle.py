"""Durable lifecycle tests on an isolated SQLite ledger; no external database."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models.compilation_session import CompilationSession
from app.mcp import compilation_lifecycle as lifecycle
from app.mcp import intelligence
from app.mcp.conversation_state import StateError
from app.mcp.schemas import CompileExpectationInput, ContinueCompilationInput
from app.schemas.clarification import (
    ClarificationState,
    ClarificationStatus,
    ClarificationTurn,
)
from app.schemas.expectation import ExpectationCreate


@pytest.fixture
def ledger(monkeypatch):
    engine = create_engine("sqlite://")
    with engine.connect() as connection:
        connection.connection.driver_connection.create_function(
            "pg_advisory_xact_lock", 1, lambda _: None
        )
    CompilationSession.__table__.create(engine)
    settings = Settings(
        _env_file=None,
        bedrock_enabled=True,
        database_target="local",
        local_database_url="postgresql+psycopg://localhost/test",
        counton_clarification_signing_key=SecretStr("isolated-lifecycle-test-key-" * 3),
    )
    monkeypatch.setattr(lifecycle, "get_settings", lambda: settings)
    monkeypatch.setattr(intelligence, "get_settings", lambda: settings)
    with Session(engine) as db:
        yield db
    engine.dispose()


def turn(status="ACTIVE", **changes):
    now = datetime.now(timezone.utc)
    payload = ExpectationCreate(
        claim="My electricity bill lower than the previous bill; previous bill was $142.10 when my next bill arrives.",
        type="numeric_comparison",
        metric="total_cost",
        comparison="less_than",
        baseline=142.1,
    )
    state = ClarificationState(
        original_utterance="My bill lower",
        created_at=now,
        expires_at=now + timedelta(minutes=15),
        timezone="UTC",
        status=status,
        question="Which bill?" if status == "ACTIVE" else None,
        unresolved_fields=["subject"] if status == "ACTIVE" else [],
        compiled_expectation=payload if status == "COMPILED" else None,
        **changes,
    )
    return ClarificationTurn(
        state=state, message=state.question or "Ready", interaction="initial"
    )


def test_completed_capture_replay_creates_once_and_rejects_mutation(
    ledger, monkeypatch
):
    user = uuid4()
    compiled = turn("COMPILED")
    token = lifecycle.save_turn(ledger, compiled, user)
    persisted = SimpleNamespace(id=uuid4())
    create = Mock(return_value=persisted)
    get = Mock(return_value=persisted)
    monkeypatch.setattr(lifecycle.expectation_service, "create_expectation", create)
    monkeypatch.setattr(lifecycle.expectation_service, "get_expectation", get)
    payload = compiled.state.compiled_expectation
    assert lifecycle.capture_compiled(ledger, payload, token, user) == persisted
    assert lifecycle.capture_compiled(ledger, payload, token, user) == persisted
    create.assert_called_once_with(ledger, payload, user, commit=False)
    with pytest.raises(StateError):
        lifecycle.capture_compiled(
            ledger, payload.model_copy(update={"baseline": 999}), token, user
        )
    with pytest.raises(StateError):
        lifecycle.capture_compiled(ledger, payload, token, uuid4())
    assert (
        ledger.get(CompilationSession, compiled.state.session_id).expectation_id
        == persisted.id
    )


@pytest.mark.parametrize("status", ["CANCELLED", "FAILED", "EXPIRED", "COMPILED"])
def test_old_active_state_cannot_continue_after_terminal(ledger, status):
    user = uuid4()
    active = turn()
    token = lifecycle.save_turn(ledger, active, user)
    row, state = lifecycle.locked_state(ledger, token, user)
    closed = turn(status)
    closed.state.session_id = state.session_id
    lifecycle.save_turn(ledger, closed, user, row)
    with pytest.raises(StateError):
        lifecycle.locked_state(ledger, token, user)


def test_next_active_turn_consumes_previous_handle(ledger):
    user = uuid4()
    active = turn()
    token = lifecycle.save_turn(ledger, active, user)
    row, state = lifecycle.locked_state(ledger, token, user)
    updated = turn()
    updated.state.session_id = state.session_id
    updated.state.question = "What should I compare it against?"
    new = lifecycle.save_turn(ledger, updated, user, row)
    assert new != token
    with pytest.raises(StateError):
        lifecycle.locked_state(ledger, token, user)
    assert (
        lifecycle.locked_state(ledger, new, user)[1].question == updated.state.question
    )


def test_start_replay_uses_same_compiled_session_not_compiler(ledger, monkeypatch):
    user = uuid4()
    compiled = turn("COMPILED")
    lifecycle.save_turn(ledger, compiled, user)
    start = Mock()
    monkeypatch.setattr(
        intelligence.compiler_service, "start_expectation_compilation", start
    )
    result = intelligence.compile_request(
        CompileExpectationInput(
            text="Repeated request", compilation_id=compiled.state.session_id
        ),
        user,
        ledger,
    )
    assert result.status == "compiled" and result.capture_state
    start.assert_not_called()
    with pytest.raises(StateError):
        intelligence.compile_request(
            CompileExpectationInput(
                text="Repeated request", compilation_id=compiled.state.session_id
            ),
            uuid4(),
            ledger,
        )


def test_expired_state_skips_model_and_cannot_capture(ledger, monkeypatch):
    user = uuid4()
    now = datetime.now(timezone.utc)
    active = turn()
    active.state.created_at = now - timedelta(hours=1)
    active.state.expires_at = now - timedelta(minutes=1)
    token = lifecycle.save_turn(ledger, active, user)
    from app.ai.clarification import ClarificationEngine

    engine = ClarificationEngine(client=Mock(), settings=lifecycle.get_settings())
    original = intelligence.compiler_service.continue_expectation_compilation
    monkeypatch.setattr(
        intelligence.compiler_service,
        "continue_expectation_compilation",
        lambda state, answer, context: original(state, answer, context, engine=engine),
    )
    result = intelligence.continue_request(
        ContinueCompilationInput(state=token, answer="My electricity bill"),
        user,
        ledger,
    )
    assert result.status == "expired" and result.capture_state is None
    engine.client.converse_json.assert_not_called()
    with pytest.raises(StateError):
        intelligence.continue_request(
            ContinueCompilationInput(state=token, answer="Again"), user, ledger
        )


def test_replaced_topic_closes_old_session(ledger):
    user = uuid4()
    active = turn()
    old = lifecycle.save_turn(ledger, active, user)
    row, state = lifecycle.locked_state(ledger, old, user)
    replacement = turn()
    replacement.replaced_state = state.model_copy(
        update={
            "status": ClarificationStatus.CANCELLED,
            "question": None,
            "unresolved_fields": [],
        }
    )
    new = lifecycle.save_turn(ledger, replacement, user, row)
    with pytest.raises(StateError):
        lifecycle.locked_state(ledger, old, user)
    assert (
        lifecycle.locked_state(ledger, new, user)[1].session_id
        == replacement.state.session_id
    )
