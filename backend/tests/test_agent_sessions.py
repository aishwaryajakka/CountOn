"""Minimal server context, canonical clarification, and owned MCP references."""

import asyncio
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError

from app.agent.actions import (
    AgentAction,
    AgentStatus,
    CapabilityTool,
    FailureCode,
    ReasonCode,
)
from app.agent.models import AgentInput
from app.agent.orchestrator import AgentOrchestrator
from app.agent.session import AgentSessionState, AgentSessionStore, SessionMarker
from app.core.auth import AuthenticatedUser
from app.mcp.schemas import CompilationResult, ExpectationListResult, ExplanationResult
from app.services import expectation_service
from tests import test_agent as shared

RecordingAdapter = shared.RecordingAdapter
compact, payload, state = shared.compact, shared.payload, shared.state
settings, user = shared.settings, shared.user
real_adapter, wire_engine = shared.real_adapter, shared.wire_engine


async def snapshot(agent, user, reference):
    async with agent.sessions.turn(user, reference) as entry:
        return entry.state


def question(settings, user):
    return CompilationResult(
        status="clarification",
        message="Which bill?",
        state=state(settings, user),
        prompt_version="v2",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "it",
        "this",
        "that",
        "that expectation",
        "what happened with that",
        "check it again",
        "Tell me about this",
        "Why did it fail?",
        "Why didn't this match?",
    ],
)
async def test_contextual_reference_reauthorizes_selection(text, settings, user):
    row = compact()
    why = text.lower().startswith("why")
    outputs = [row, row]
    if why:
        outputs.append(
            ExplanationResult(
                expectation_id=row.id, message="It matched.", result="MATCH"
            )
        )
    adapter = RecordingAdapter(outputs)
    agent = AgentOrchestrator(adapter, settings=settings)
    first = await agent.handle_session(
        user,
        AgentInput(text="Tell me about my electricity bill", expectation_id=row.id),
    )
    follow = await agent.handle_session(
        user, AgentInput(text=text), first.session_reference
    )
    assert follow.result.expectation_id == row.id
    assert follow.result.status == AgentStatus.SUCCESS
    assert [call[1] for call in adapter.calls] == [
        CapabilityTool.GET,
        CapabilityTool.GET,
    ] + ([CapabilityTool.EXPLAIN] if why else [])
    assert follow.session_reference != first.session_reference
    selected = await snapshot(agent, user, follow.session_reference)
    assert selected.selected_expectation_id == row.id


@pytest.mark.asyncio
async def test_no_context_never_guesses(settings, user):
    adapter = RecordingAdapter()
    agent = AgentOrchestrator(adapter, settings=settings)
    result = await agent.handle_session(user, AgentInput(text="Why did it fail?"))
    assert result.result.clarification_required
    assert result.result.code == ReasonCode.MISSING_REFERENCE
    assert not adapter.calls


@pytest.mark.asyncio
async def test_failed_ownership_recheck_clears_selection_before_why(settings, user):
    from app.agent.adapters import CapabilityError

    row = compact()
    adapter = RecordingAdapter([row, CapabilityError(FailureCode.NOT_FOUND)])
    agent = AgentOrchestrator(adapter, settings=settings)
    first = await agent.handle_session(
        user, AgentInput(text="Check that expectation", expectation_id=row.id)
    )
    second = await agent.handle_session(
        user, AgentInput(text="Why did it fail?"), first.session_reference
    )
    assert second.result.code == FailureCode.NOT_FOUND
    assert all(call[1] == CapabilityTool.GET for call in adapter.calls)
    assert (
        await snapshot(agent, user, second.session_reference)
    ).selected_expectation_id is None


@pytest.mark.asyncio
async def test_session_retains_existing_signed_reference_only(settings, user):
    adapter = RecordingAdapter([question(settings, user), question(settings, user)])
    agent = AgentOrchestrator(adapter, settings=settings)
    first = await agent.handle_session(
        user, AgentInput(text="I'm counting on my bill being lower")
    )
    second = await agent.handle_session(
        user, AgentInput(text="My electricity bill"), first.session_reference
    )
    assert second.result.clarification_required and not second.result.captured
    assert adapter.calls[1][1] == CapabilityTool.CONTINUE
    assert (
        adapter.calls[1][2].state == first.result.clarification_state.get_secret_value()
    )
    assert adapter.calls[1][2].answer == "My electricity bill"
    saved = await snapshot(agent, user, second.session_reference)
    assert saved.clarification_reference == second.result.clarification_state
    assert "My electricity bill" not in saved.model_dump_json()
    assert "bill being lower" not in saved.model_dump_json()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "Actually make that $150",
        "Change that to $150",
        "Make it $150",
        "Actually I'm counting on my package arriving Friday",
    ],
)
async def test_correction_and_new_topic_delegate_without_rewriting(
    text, settings, user
):
    adapter = RecordingAdapter([question(settings, user), question(settings, user)])
    agent = AgentOrchestrator(adapter, settings=settings)
    first = await agent.handle_session(
        user, AgentInput(text="I'm counting on my bill being lower")
    )
    second = await agent.handle_session(
        user, AgentInput(text=text), first.session_reference
    )
    assert second.result.action == AgentAction.CONTINUE_CLARIFICATION
    assert adapter.calls[1][2].answer == text
    assert len(adapter.calls) == 2 and not second.result.captured


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["Never mind", "Cancel that", "Forget it"])
async def test_cancel_closes_draft_and_session_stays_usable(text, settings, user):
    adapter = RecordingAdapter(
        [
            question(settings, user),
            CompilationResult(
                status="cancelled", message="Cancelled", prompt_version="v2"
            ),
            ExpectationListResult(expectations=[], limit=50, offset=0),
        ]
    )
    agent = AgentOrchestrator(adapter, settings=settings)
    first = await agent.handle_session(
        user, AgentInput(text="I'm counting on my bill being lower")
    )
    cancelled = await agent.handle_session(
        user, AgentInput(text=text), first.session_reference
    )
    saved = await snapshot(agent, user, cancelled.session_reference)
    assert (
        saved.marker == SessionMarker.CANCELLED
        and saved.clarification_reference is None
    )
    assert saved.selected_expectation_id is None and not cancelled.result.captured
    next_turn = await agent.handle_session(
        user, AgentInput(text="What am I counting on?"), cancelled.session_reference
    )
    assert next_turn.result.status == AgentStatus.SUCCESS
    assert all(call[1] != CapabilityTool.CAPTURE for call in adapter.calls)


@pytest.mark.asyncio
async def test_pending_selection_bounded_and_does_not_reuse_old_context(settings, user):
    rows = [compact() for _ in range(30)]
    adapter = RecordingAdapter(
        [ExpectationListResult(expectations=rows, limit=100, offset=0), rows[1]]
    )
    agent = AgentOrchestrator(adapter, settings=settings)
    first = await agent.handle_session(
        user, AgentInput(text="Tell me about my electricity bill")
    )
    saved = await snapshot(agent, user, first.session_reference)
    assert saved.pending_disambiguation_ids == tuple(row.id for row in rows[:10])
    assert saved.selected_expectation_id is None
    ambiguous = await agent.handle_session(
        user, AgentInput(text="Why did it fail?"), first.session_reference
    )
    assert ambiguous.result.clarification_required and len(adapter.calls) == 1
    chosen = await agent.handle_session(
        user, AgentInput(text="the second one"), ambiguous.session_reference
    )
    assert chosen.result.expectation_id == rows[1].id
    assert adapter.calls[-1][2].expectation_id == rows[1].id
    assert not (
        await snapshot(agent, user, chosen.session_reference)
    ).pending_disambiguation_ids


@pytest.mark.asyncio
async def test_pending_why_selection_survives_list_interruption(settings, user):
    rows = [compact(), compact()]
    adapter = RecordingAdapter(
        [
            ExpectationListResult(expectations=rows, limit=100, offset=0),
            ExpectationListResult(expectations=[], limit=50, offset=0),
            rows[0],
            ExplanationResult(
                expectation_id=rows[0].id, message="Still waiting", code="NO_EVALUATION"
            ),
        ]
    )
    agent = AgentOrchestrator(adapter, settings=settings)
    first = await agent.handle_session(
        user, AgentInput(text="Why did my electricity bill fail?")
    )
    listed = await agent.handle_session(
        user, AgentInput(text="What am I counting on?"), first.session_reference
    )
    chosen = await agent.handle_session(
        user, AgentInput(text="first"), listed.session_reference
    )
    assert chosen.result.explanation.code == "NO_EVALUATION"
    assert [call[1] for call in adapter.calls][-2:] == [
        CapabilityTool.GET,
        CapabilityTool.EXPLAIN,
    ]


@pytest.mark.asyncio
async def test_expired_handle_does_not_start_new_capture(settings, user):
    now = [datetime.now(timezone.utc)]
    store = AgentSessionStore(ttl_seconds=60, clock=lambda: now[0])
    adapter = RecordingAdapter()
    agent = AgentOrchestrator(adapter, settings=settings, session_store=store)
    first = await agent.handle_session(user, AgentInput(text="Why did it fail?"))
    now[0] += timedelta(seconds=60)
    expired = await agent.handle_session(
        user,
        AgentInput(text="I'm counting on my grocery bill under $120 this week"),
        first.session_reference,
    )
    assert expired.result.code == FailureCode.STATE_REJECTED
    assert expired.session_reference is None and not adapter.calls


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["tampered", "other_user", "version"])
async def test_invalid_session_fails_closed(case, settings, user):
    adapter = RecordingAdapter()
    agent = AgentOrchestrator(adapter, settings=settings)
    first = await agent.handle_session(user, AgentInput(text="Why did it fail?"))
    reference = first.session_reference
    caller = user
    if case == "tampered":
        reference = SecretStr("A" * 43)
    elif case == "other_user":
        caller = AuthenticatedUser(uuid4())
    else:
        async with agent.sessions.turn(user, reference) as entry:
            entry.state = entry.state.model_copy(update={"version": "v999"})
    result = await agent.handle_session(
        caller, AgentInput(text="What am I counting on?"), reference
    )
    assert result.result.code == FailureCode.STATE_REJECTED
    assert result.session_reference is None and not adapter.calls


@pytest.mark.asyncio
async def test_client_cannot_supply_trusted_state_or_clarification_reference(
    settings, user
):
    agent = AgentOrchestrator(RecordingAdapter(), settings=settings)
    with pytest.raises(ValidationError):
        AgentInput.model_validate(
            {"text": "it", "selected_expectation_id": uuid4(), "user_id": uuid4()}
        )
    rejected = await agent.handle_session(
        user,
        AgentInput(
            text="My electricity bill",
            clarification_state=SecretStr(state(settings, user)),
        ),
    )
    assert rejected.result.status == AgentStatus.REJECTED
    assert rejected.session_reference is None


@pytest.mark.parametrize(
    "field",
    [
        "transcript",
        "bearer_token",
        "supabase_token",
        "aws_credentials",
        "database_url",
        "raw_prompt",
        "raw_model_output",
        "provider_payload",
        "chain_of_thought",
        "user_id",
    ],
)
def test_state_has_no_transcript_credentials_or_arbitrary_payloads(field):
    now = datetime.now(timezone.utc)
    with pytest.raises(ValidationError):
        AgentSessionState.model_validate(
            {
                "created_at": now,
                "expires_at": now + timedelta(minutes=15),
                field: "private-sentinel",
            }
        )


def test_state_bounds_and_version():
    now = datetime.now(timezone.utc)
    fields = {"created_at": now, "expires_at": now + timedelta(minutes=15)}
    for changes in (
        {"version": "v2"},
        {"pending_disambiguation_ids": tuple(uuid4() for _ in range(11))},
        {"expires_at": now + timedelta(hours=2)},
        {"selected_expectation_id": uuid4(), "pending_disambiguation_ids": (uuid4(),)},
        {
            "marker": SessionMarker.COMPLETED,
            "clarification_reference": SecretStr("abc." + "0" * 64),
        },
    ):
        with pytest.raises(ValidationError):
            AgentSessionState.model_validate({**fields, **changes})


@pytest.mark.asyncio
async def test_rotated_handle_concurrent_replay_executes_at_most_once(settings, user):
    adapter = RecordingAdapter(
        [ExpectationListResult(expectations=[], limit=50, offset=0)]
    )
    agent = AgentOrchestrator(adapter, settings=settings)
    first = await agent.handle_session(user, AgentInput(text="Why did it fail?"))
    results = await asyncio.gather(
        *(
            agent.handle_session(
                user, AgentInput(text="What am I counting on?"), first.session_reference
            )
            for _ in range(2)
        )
    )
    assert sum(result.result.status == AgentStatus.SUCCESS for result in results) == 1
    assert (
        sum(result.result.code == FailureCode.STATE_REJECTED for result in results) == 1
    )
    assert len(adapter.calls) == 1


@pytest.mark.asyncio
async def test_reset_closes_active_draft_and_rotates_new_session(settings, user):
    adapter = RecordingAdapter(
        [
            question(settings, user),
            CompilationResult(
                status="cancelled", message="Cancelled", prompt_version="v2"
            ),
        ]
    )
    agent = AgentOrchestrator(adapter, settings=settings)
    first = await agent.handle_session(
        user, AgentInput(text="I'm counting on my bill being lower")
    )
    old_state = await snapshot(agent, user, first.session_reference)
    reset = await agent.reset_session(user, first.session_reference)
    fresh = await snapshot(agent, user, reset.session_reference)
    assert (
        fresh.session_id != old_state.session_id
        and fresh.clarification_reference is None
    )
    assert fresh.selected_expectation_id is None and fresh.marker == SessionMarker.READY
    expired = await agent.handle_session(
        user, AgentInput(text="My electricity bill"), first.session_reference
    )
    assert expired.result.code == FailureCode.STATE_REJECTED
    assert adapter.calls[-1][2].answer == "Never mind"
    follow = await agent.handle_session(
        user, AgentInput(text="Why did it fail?"), reset.session_reference
    )
    assert follow.result.clarification_required and len(adapter.calls) == 2


@pytest.mark.asyncio
async def test_store_is_bounded_and_prunes_expired_without_eviction(user):
    from app.agent.adapters import CapabilityError

    now = [datetime.now(timezone.utc)]
    store = AgentSessionStore(max_sessions=1, ttl_seconds=60, clock=lambda: now[0])
    first = store.create(user)
    with pytest.raises(CapabilityError):
        store.create(user)
    now[0] += timedelta(seconds=60)
    second = store.create(user)
    assert second != first and len(store._entries) == 1


@pytest.mark.asyncio
async def test_real_contextual_reference_cannot_reuse_other_users_row(
    real_adapter, db, users, settings
):
    row = expectation_service.create_expectation(db, payload(), users[1].id)
    agent = AgentOrchestrator(real_adapter, settings=settings)
    first = await agent.handle_session(users[0], AgentInput(text="Why did it fail?"))
    async with agent.sessions.turn(users[0], first.session_reference) as entry:
        entry.state = entry.state.model_copy(update={"selected_expectation_id": row.id})
    blocked = await agent.handle_session(
        users[0], AgentInput(text="Why did it fail?"), first.session_reference
    )
    assert blocked.result.code == FailureCode.NOT_FOUND
    assert blocked.result.explanation is None
    assert (
        await snapshot(agent, users[0], blocked.session_reference)
    ).selected_expectation_id is None


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["complete", "correction", "cancel", "topic"])
async def test_real_session_canonical_clarification_and_completed_replay(
    mode, real_adapter, users, client, settings, wire_engine
):
    from tests.test_clarification import decision, initial, patch
    from tests.test_expectation_compiler import temporal

    outputs = [
        initial(),
        decision(patch("subject", "electricity bill", "electricity bill")),
        decision(
            patch("operand", "baseline", "last bill"), patch("baseline", 142, "$142")
        ),
    ]
    answers = ["My electricity bill", "My last bill was $142"]
    if mode == "correction":
        outputs.append(decision(patch("baseline", 150, "$150"), kind="correction"))
        answers.append("Actually make that $150")
    if mode == "cancel":
        answers.append("Never mind")
    elif mode == "topic":
        outputs.append(temporal())
        answers.append("Actually I'm counting on my package arriving Friday")
    else:
        outputs.append(
            decision(
                patch(
                    "deadline", "When my next bill arrives", "When my next bill arrives"
                )
            )
        )
        answers.append("When my next bill arrives")
    runtime = wire_engine(*outputs)
    agent = AgentOrchestrator(real_adapter, settings=settings)
    turn = await agent.handle_session(
        users[0], AgentInput(text="I'm counting on my bill being lower", locale="en-US")
    )
    old_reference = None
    for answer in answers:
        assert turn.result.clarification_required and not turn.result.captured
        assert client.get("/api/v1/expectations").json() == []
        old_reference = turn.session_reference
        turn = await agent.handle_session(
            users[0], AgentInput(text=answer), old_reference
        )
    rows = client.get("/api/v1/expectations").json()
    count = 0 if mode == "cancel" else 1
    assert len(rows) == count and turn.result.captured == bool(count)
    saved = await snapshot(agent, users[0], turn.session_reference)
    assert saved.clarification_reference is None
    assert saved.marker == (
        SessionMarker.CANCELLED if mode == "cancel" else SessionMarker.COMPLETED
    )
    if mode == "topic":
        assert rows[0]["type"] == "temporal"
        assert rows[0]["baseline"] is None and "electricity" not in rows[0]["claim"]
    elif count:
        assert rows[0]["baseline"] == (150 if mode == "correction" else 142)
    calls = runtime.converse.call_count
    replay = await agent.handle_session(
        users[0], AgentInput(text=answers[-1]), old_reference
    )
    assert (
        replay.result.code == FailureCode.STATE_REJECTED
        and replay.session_reference is None
    )
    assert len(client.get("/api/v1/expectations").json()) == count
    assert runtime.converse.call_count == calls
    terminal_reply = await agent.handle_session(
        users[0], AgentInput(text=answers[-1]), turn.session_reference
    )
    assert not terminal_reply.result.captured
    assert len(client.get("/api/v1/expectations").json()) == count
    assert runtime.converse.call_count == calls
    follow = await agent.handle_session(
        users[0], AgentInput(text="Why did it fail?"), terminal_reply.session_reference
    )
    assert (
        follow.result.clarification_required
        if mode == "cancel"
        else follow.result.explanation.code == "NO_EVALUATION"
    )
    assert runtime.converse.call_count == calls


@pytest.mark.asyncio
async def test_invalid_pending_choice_cannot_select_an_unlisted_id(settings, user):
    rows = [compact(), compact()]
    adapter = RecordingAdapter(
        [ExpectationListResult(expectations=rows, limit=100, offset=0)]
    )
    agent = AgentOrchestrator(adapter, settings=settings)
    first = await agent.handle_session(
        user, AgentInput(text="Tell me about my electricity bill")
    )
    rejected = await agent.handle_session(
        user,
        AgentInput(text="that one", expectation_id=uuid4()),
        first.session_reference,
    )
    assert rejected.result.clarification_required and len(adapter.calls) == 1
    saved = await snapshot(agent, user, rejected.session_reference)
    assert saved.pending_disambiguation_ids == tuple(row.id for row in rows)
    assert saved.selected_expectation_id is None


@pytest.mark.asyncio
async def test_reset_transport_failure_keeps_active_draft_for_safe_retry(
    settings, user
):
    from app.agent.adapters import CapabilityError

    adapter = RecordingAdapter(
        [question(settings, user), CapabilityError(FailureCode.UNAVAILABLE)]
    )
    agent = AgentOrchestrator(adapter, settings=settings)
    first = await agent.handle_session(
        user, AgentInput(text="I'm counting on my bill being lower")
    )
    reset = await agent.reset_session(user, first.session_reference)
    assert reset.result.status == AgentStatus.FAILED
    assert (
        await snapshot(agent, user, reset.session_reference)
    ).clarification_reference == first.result.clarification_state
    assert all(call[1] != CapabilityTool.CAPTURE for call in adapter.calls)


@pytest.mark.asyncio
async def test_session_does_not_log_handle_or_private_state(settings, user, caplog):
    import logging

    from app.core.logging import StructuredFormatter

    adapter = RecordingAdapter(
        [
            question(settings, user),
            CompilationResult(
                status="cancelled", message="Cancelled", prompt_version="v2"
            ),
        ]
    )
    agent = AgentOrchestrator(adapter, settings=settings)
    caplog.set_level(logging.INFO, logger="app.agent.orchestrator")
    first = await agent.handle_session(
        user, AgentInput(text="I'm counting on my bill being lower")
    )
    cancelled = await agent.handle_session(
        user, AgentInput(text="Never mind"), first.session_reference
    )
    logs = " ".join(StructuredFormatter().format(record) for record in caplog.records)
    for reference in (
        first.session_reference,
        first.result.clarification_state,
        cancelled.session_reference,
    ):
        assert reference.get_secret_value() not in logs
        assert reference.get_secret_value() not in cancelled.model_dump_json()


@pytest.mark.asyncio
async def test_canonical_clarification_expiry_is_checked_before_any_reuse(
    settings, user
):
    adapter = RecordingAdapter()
    agent = AgentOrchestrator(adapter, settings=settings)
    first = await agent.handle_session(user, AgentInput(text="Why did it fail?"))
    async with agent.sessions.turn(user, first.session_reference) as entry:
        entry.state = entry.state.model_copy(
            update={
                "clarification_reference": SecretStr(
                    state(settings, user, expired=True)
                )
            }
        )
    rejected = await agent.handle_session(
        user, AgentInput(text="My electricity bill"), first.session_reference
    )
    assert rejected.result.code == FailureCode.STATE_REJECTED
    assert rejected.session_reference is None and not adapter.calls


@pytest.mark.asyncio
async def test_unclear_selection_is_not_used_as_a_compiler_answer(settings, user):
    rows = [compact(), compact()]
    adapter = RecordingAdapter(
        [
            question(settings, user),
            ExpectationListResult(expectations=rows, limit=100, offset=0),
        ]
    )
    agent = AgentOrchestrator(adapter, settings=settings)
    first = await agent.handle_session(
        user, AgentInput(text="I'm counting on my bill being lower")
    )
    choices = await agent.handle_session(
        user,
        AgentInput(text="Tell me about my electricity bill"),
        first.session_reference,
    )
    unclear = await agent.handle_session(
        user, AgentInput(text="0"), choices.session_reference
    )
    assert unclear.result.code == ReasonCode.MISSING_REFERENCE
    assert len(adapter.calls) == 2 and not unclear.result.captured
    saved = await snapshot(agent, user, unclear.session_reference)
    assert saved.clarification_reference == first.result.clarification_state
    assert len(saved.pending_disambiguation_ids) == 2
