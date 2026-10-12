"""Real MCP integration, mocked inference, owned PostgreSQL persistence and REST."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import UUID

import pytest
from mcp import Client
from pydantic import SecretStr

from app.ai.clarification import ClarificationEngine
from app.core.config import get_settings
from app.mcp import compilation_lifecycle, intelligence
from app.mcp.conversation_state import StateError, decode_state, encode_state
from app.mcp.server import create_server
from app.schemas.clarification import (
    ClarificationState,
    ClarificationStatus,
    ClarificationTurn,
)
from app.services import compiler_service
from tests.test_expectation_compiler import adapter as compiler_adapter
from tests.test_expectation_compiler import compiled


@pytest.fixture
def server(db, users):
    @contextmanager
    def factory():
        yield db

    return lambda user=users[0]: create_server(
        session_factory=factory, user_resolver=lambda ctx: user
    )


@pytest.fixture
def enabled(monkeypatch):
    settings = get_settings().model_copy(
        update={
            "bedrock_enabled": True,
            "counton_clarification_signing_key": SecretStr("test-signing-key-" * 4),
        }
    )
    monkeypatch.setattr(intelligence, "get_settings", lambda: settings)
    monkeypatch.setattr(compilation_lifecycle, "get_settings", lambda: settings)
    return settings


def active_state():
    now = datetime.now(timezone.utc)
    return ClarificationState(
        original_utterance="I'm counting on my bill being lower",
        created_at=now,
        expires_at=now + timedelta(minutes=15),
        timezone="UTC",
        locale="en-US",
        max_turns=3,
        status=ClarificationStatus.ACTIVE,
        question="Which bill?",
        unresolved_fields=["subject"],
    )


def test_signed_state_bound_to_principal_and_integrity(enabled, users):
    state = active_state()
    token = encode_state(state, users[0].id, enabled)
    assert decode_state(token, users[0].id, enabled) == state
    for changed, user in [
        (token, users[1].id),
        (token[:-1] + ("0" if token[-1] != "0" else "1"), users[0].id),
    ]:
        with pytest.raises(StateError):
            decode_state(changed, user, enabled)
    assert str(users[0].id) not in token


def test_production_requires_dedicated_signing_key(enabled):
    from app.mcp.conversation_state import signing_key

    with pytest.raises(StateError):
        signing_key(
            enabled.model_copy(
                update={
                    "environment": "production",
                    "counton_clarification_signing_key": None,
                }
            )
        )


@pytest.mark.asyncio
async def test_compile_mcp_capture_shared_rest(
    server, enabled, monkeypatch, client, db, users
):
    compiler, _ = compiler_adapter(compiled(target=120, quote="$120"))
    engine = ClarificationEngine(
        client=compiler.client, compiler=compiler, settings=enabled
    )
    original = compiler_service.start_expectation_compilation
    monkeypatch.setattr(
        compiler_service,
        "start_expectation_compilation",
        lambda text, context: original(text, context, engine=engine),
    )
    async with Client(server(), raise_exceptions=True) as mcp:
        response = await mcp.call_tool(
            "compile_expectation",
            {
                "request": {
                    "text": "My grocery bill should stay under $120 this week.",
                    "timezone": "America/Chicago",
                    "locale": "en-US",
                }
            },
        )
        assert not response.is_error
        result = response.structured_content
        assert (
            result["status"] == "compiled"
            and result["expectation"]["target_value"] == 120
        )
        assert client.get("/api/v1/expectations").json() == []
        captured = await mcp.call_tool(
            "capture_expectation", {"request": result["expectation"]}
        )
        assert not captured.is_error
        identity = captured.structured_content["id"]
        assert (
            client.get(f"/api/v1/expectations/{identity}").json()["target_value"] == 120
        )
        assert identity in {
            row["id"] for row in client.get("/api/v1/expectations").json()
        }
        assert client.get(f"/api/v1/expectations/{identity}").status_code == 200


@pytest.mark.asyncio
async def test_disabled_compile_leaves_list_working(server, monkeypatch, enabled):
    monkeypatch.setattr(
        intelligence,
        "get_settings",
        lambda: enabled.model_copy(update={"bedrock_enabled": False}),
    )
    async with Client(server(), raise_exceptions=True) as mcp:
        result = await mcp.call_tool(
            "compile_expectation", {"request": {"text": "My bill lower"}}
        )
        assert result.structured_content["code"] == "BEDROCK_DISABLED"
        assert result.structured_content["expectation"] is None
        listed = await mcp.call_tool("list_expectations", {"request": {}})
        assert not listed.is_error


@pytest.mark.asyncio
async def test_continuation_cancellation_does_not_mutate(
    server, enabled, client, users, db
):
    token = compilation_lifecycle.save_turn(
        db,
        ClarificationTurn(
            state=active_state(), message="Which bill?", interaction="initial"
        ),
        users[0].id,
    )
    async with Client(server(), raise_exceptions=True) as mcp:
        result = await mcp.call_tool(
            "continue_expectation_compilation",
            {"request": {"state": token, "answer": "Never mind"}},
        )
        assert (
            not result.is_error and result.structured_content["status"] == "cancelled"
        )
        assert result.structured_content["expectation"] is None
    assert client.get("/api/v1/expectations").json() == []


@pytest.mark.asyncio
async def test_expired_continuation(server, enabled, users, db):
    state = active_state()
    state.created_at -= timedelta(hours=1)
    state.expires_at -= timedelta(hours=1)
    token = compilation_lifecycle.save_turn(
        db,
        ClarificationTurn(state=state, message=state.question, interaction="initial"),
        users[0].id,
    )
    async with Client(server(), raise_exceptions=True) as mcp:
        result = await mcp.call_tool(
            "continue_expectation_compilation",
            {"request": {"state": token, "answer": "My electricity bill"}},
        )
        assert result.structured_content["code"] == "CLARIFICATION_EXPIRED"


@pytest.mark.asyncio
async def test_cross_user_continuation_rejected(server, enabled, users, db):
    token = compilation_lifecycle.save_turn(
        db,
        ClarificationTurn(
            state=active_state(), message="Which bill?", interaction="initial"
        ),
        users[0].id,
    )
    async with Client(server(users[1]), raise_exceptions=True) as mcp:
        result = await mcp.call_tool(
            "continue_expectation_compilation",
            {"request": {"state": token, "answer": "My electricity bill"}},
        )
        assert result.is_error and token not in result.content[0].text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "amount,result", [(162, "MISMATCH"), (130, "MATCH"), (None, "UNKNOWN")]
)
async def test_explain_real_evaluation_only(
    server, client, numeric_payload, monkeypatch, amount, result
):
    row = client.post("/api/v1/expectations", json=numeric_payload).json()
    identity = row["id"]
    if amount is not None:
        response = client.post(
            f"/api/v1/expectations/{identity}/evidence",
            json={
                "source": "utility_bill",
                "metric": "total_cost",
                "value": {"amount": amount},
                "unit": "USD",
                "observed_at": "2026-10-01T20:00:00Z",
            },
        )
        assert response.status_code == 201
    assert (
        client.post(f"/api/v1/expectations/{identity}/evaluate").json()["result"]
        == result
    )
    if result != "MISMATCH":
        monkeypatch.setattr(
            intelligence.investigation_service,
            "investigate_mismatch",
            Mock(side_effect=AssertionError("Must not investigate")),
        )
    async with Client(server(), raise_exceptions=True) as mcp:
        explained = await mcp.call_tool(
            "explain_expectation_mismatch", {"request": {"expectation_id": identity}}
        )
        assert not explained.is_error
        output = explained.structured_content
        assert output["result"] == result
        if result == "MISMATCH":
            assert output["explanation"]["observed"]["value"] == 162
            assert output["explanation"]["generation"] == "deterministic"
        else:
            assert output["explanation"] is None and output["code"] == "NOT_MISMATCH"
    assert (
        client.get(f"/api/v1/expectations/{identity}/evaluations").json()[0]["result"]
        == result
    )


@pytest.mark.asyncio
async def test_no_evaluation_and_other_owner(server, client, numeric_payload, users):
    row = client.post("/api/v1/expectations", json=numeric_payload).json()
    async with Client(server(), raise_exceptions=True) as mcp:
        output = await mcp.call_tool(
            "explain_expectation_mismatch", {"request": {"expectation_id": row["id"]}}
        )
        assert output.structured_content["code"] == "NO_EVALUATION"
    async with Client(server(users[1]), raise_exceptions=True) as other:
        hidden = await other.call_tool(
            "explain_expectation_mismatch", {"request": {"expectation_id": row["id"]}}
        )
        missing = await other.call_tool(
            "explain_expectation_mismatch",
            {"request": {"expectation_id": str(UUID(int=0))}},
        )
        assert hidden.is_error and hidden.content[0].text == missing.content[0].text


@pytest.mark.asyncio
async def test_new_tools_reject_supplied_identity_and_flattened_input(server):
    async with Client(server(), raise_exceptions=True) as mcp:
        for arguments in [
            {"text": "Private text"},
            {"request": {"text": "Private text", "user_id": str(UUID(int=1))}},
        ]:
            result = await mcp.call_tool("compile_expectation", arguments)
            assert result.is_error and "Private text" not in result.content[0].text


@pytest.mark.asyncio
async def test_real_clarification_and_correction_over_mcp(
    server, enabled, monkeypatch, client
):
    from tests.test_clarification import decision, engine, initial, patch

    selected, runtime = engine(
        initial(),
        decision(patch("subject", "electricity bill", "My electricity bill")),
        decision(patch("operand", "baseline", "Last month")),
        decision(patch("baseline", 150, "$150")),
    )
    initial_fn = compiler_service.start_expectation_compilation
    continue_fn = compiler_service.continue_expectation_compilation
    monkeypatch.setattr(
        compiler_service,
        "start_expectation_compilation",
        lambda text, context: initial_fn(text, context, engine=selected),
    )
    monkeypatch.setattr(
        compiler_service,
        "continue_expectation_compilation",
        lambda state, answer, context: continue_fn(
            state, answer, context, engine=selected
        ),
    )
    async with Client(server(), raise_exceptions=True) as mcp:
        response = await mcp.call_tool(
            "compile_expectation",
            {
                "request": {
                    "text": "I'm counting on my bill being lower.",
                    "timezone": "UTC",
                    "locale": "en-US",
                }
            },
        )
        assert response.structured_content["status"] == "clarification"
        assert client.get("/api/v1/expectations").json() == []
        for answer in ["My electricity bill.", "Last month.", "$150"]:
            response = await mcp.call_tool(
                "continue_expectation_compilation",
                {
                    "request": {
                        "state": response.structured_content["state"],
                        "answer": answer,
                    }
                },
            )
            assert not response.is_error
            assert client.get("/api/v1/expectations").json() == []
        assert response.structured_content["status"] == "compiled"
        assert response.structured_content["expectation"]["baseline"] == 150
        capture = await mcp.call_tool(
            "capture_expectation",
            {"request": response.structured_content["expectation"]},
        )
        assert not capture.is_error
        assert len(client.get("/api/v1/expectations").json()) == 1
    assert runtime.converse.call_count == 4


def test_compile_through_streamable_http(server, enabled, monkeypatch, client):
    from starlette.testclient import TestClient

    compiler, _ = compiler_adapter(compiled(target=120, quote="$120"))
    selected = ClarificationEngine(
        client=compiler.client, compiler=compiler, settings=enabled
    )
    original = compiler_service.start_expectation_compilation
    monkeypatch.setattr(
        compiler_service,
        "start_expectation_compilation",
        lambda text, context: original(text, context, engine=selected),
    )
    app = server().streamable_http_app(stateless_http=True, json_response=True)
    headers = {
        "Accept": "application/json, text/event-stream",
        "Authorization": "Bearer test-only-token",
    }
    with TestClient(app, base_url="http://127.0.0.1:8003") as http:
        response = http.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "integration", "version": "1"},
                },
            },
        )
        assert response.status_code == 200
        headers["MCP-Protocol-Version"] = "2025-06-18"
        response = http.post(
            "/mcp",
            headers=headers,
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "compile_expectation",
                    "arguments": {
                        "request": {
                            "text": "My grocery bill should stay under $120 this week.",
                            "timezone": "UTC",
                            "locale": "en-US",
                        }
                    },
                },
            },
        )
        assert response.status_code == 200
        output = response.json()["result"]["structuredContent"]
        assert (
            output["status"] == "compiled"
            and output["expectation"]["target_value"] == 120
        )
        assert "test-only-token" not in response.text
        assert client.get("/api/v1/expectations").json() == []


@pytest.mark.asyncio
async def test_explicit_correction_is_signed_before_capture(
    server, enabled, monkeypatch, users, client, db
):
    from datetime import datetime, timedelta, timezone

    from tests.test_clarification import active, decision, engine, patch

    state = active()
    state.created_at = datetime.now(timezone.utc)
    state.expires_at = state.created_at + timedelta(minutes=15)
    selected, _ = engine(
        decision(patch("target_value", 150, "$150"), kind="correction"),
        decision(patch("currency", "USD", "USD")),
    )
    original = compiler_service.continue_expectation_compilation
    monkeypatch.setattr(
        compiler_service,
        "continue_expectation_compilation",
        lambda state, answer, context: original(
            state, answer, context, engine=selected
        ),
    )
    token = compilation_lifecycle.save_turn(
        db,
        ClarificationTurn(state=state, message=state.question, interaction="initial"),
        users[0].id,
    )
    async with Client(server(), raise_exceptions=True) as mcp:
        result = await mcp.call_tool(
            "continue_expectation_compilation",
            {"request": {"state": token, "answer": "Actually make it $150, not $120."}},
        )
        assert result.structured_content["status"] == "clarification"
        token = result.structured_content["state"]
        assert (
            decode_state(token, users[0].id, enabled).partial_interpretation.values[
                "target_value"
            ]
            == 150
        )
        assert client.get("/api/v1/expectations").json() == []
        result = await mcp.call_tool(
            "continue_expectation_compilation",
            {"request": {"state": token, "answer": "USD"}},
        )
        assert (
            result.structured_content["status"] == "compiled"
            and result.structured_content["expectation"]["target_value"] == 150
        )


@pytest.mark.asyncio
async def test_grounded_bedrock_explanation_over_mcp(
    server, client, numeric_payload, monkeypatch
):
    from app.ai.investigation_evidence import normalize
    from tests.test_mismatch_investigator import adapter

    row = client.post("/api/v1/expectations", json=numeric_payload).json()
    identity = row["id"]
    for metric, value, source, unit in [
        ("total_cost", {"amount": 162}, "utility_bill", "USD"),
        ("energy_usage_change", {"percentage": -18}, "utility_usage", "percent"),
        ("rate_change", {"percentage": 22}, "utility_tariff", "percent"),
    ]:
        assert (
            client.post(
                f"/api/v1/expectations/{identity}/evidence",
                json={
                    "source": source,
                    "metric": metric,
                    "value": value,
                    "unit": unit,
                    "observed_at": "2026-10-01T20:00:00Z",
                },
            ).status_code
            == 201
        )
    assert (
        client.post(f"/api/v1/expectations/{identity}/evaluate").json()["result"]
        == "MISMATCH"
    )
    original = intelligence.investigation_service.investigate_mismatch

    def grounded(**kwargs):
        facts = normalize(**kwargs, max_evidence=6)
        values = {item.ref: item.value for item in facts.evidence}
        draft = {
            "expected": facts.expected.model_dump(mode="json"),
            "observed": facts.observed.model_dump(mode="json"),
            "summary_kind": "possible_contribution",
            "key_factors": [
                {
                    "kind": "possible_rate_offset",
                    "evidence_refs": list(values),
                    "values": values,
                }
            ],
        }
        selected, _ = adapter(draft)
        return original(**kwargs, investigator=selected)

    monkeypatch.setattr(
        intelligence.investigation_service, "investigate_mismatch", grounded
    )
    async with Client(server(), raise_exceptions=True) as mcp:
        response = await mcp.call_tool(
            "explain_expectation_mismatch", {"request": {"expectation_id": identity}}
        )
        assert not response.is_error
        output = response.structured_content
        assert output["bedrock_used"] is True and output["result"] == "MISMATCH"
        assert (
            "could have contributed"
            in output["explanation"]["key_factors"][0]["description"]
        )
        assert len(output["explanation"]["evidence_refs"]) == 3
    assert len(client.get(f"/api/v1/expectations/{identity}/evaluations").json()) == 1


@pytest.mark.asyncio
async def test_conversational_capture_replay_and_stale_continuation(
    server, enabled, monkeypatch, client, db, users
):
    from app.mcp.compilation_lifecycle import capture_compiled
    from app.schemas.expectation import ExpectationCreate
    from tests.test_clarification import decision, initial, patch
    from tests.test_clarification import engine as clarification_engine

    engine, runtime = clarification_engine(
        initial(),
        decision(patch("subject", "electricity bill", "electricity bill")),
        decision(
            patch("operand", "baseline", "last bill"),
            patch("baseline", 142.1, "$142.10"),
        ),
        decision(
            patch("deadline", "When my next bill arrives", "When my next bill arrives")
        ),
    )
    start = compiler_service.start_expectation_compilation
    continue_ = compiler_service.continue_expectation_compilation
    monkeypatch.setattr(
        compiler_service,
        "start_expectation_compilation",
        lambda text, context, **kwargs: start(text, context, engine=engine, **kwargs),
    )
    monkeypatch.setattr(
        compiler_service,
        "continue_expectation_compilation",
        lambda state, answer, context: continue_(state, answer, context, engine=engine),
    )
    async with Client(server(), raise_exceptions=True) as mcp:
        response = await mcp.call_tool(
            "compile_expectation",
            {
                "request": {
                    "text": "I'm counting on my bill being lower.",
                    "timezone": "UTC",
                    "locale": "en-US",
                    "conversational": True,
                }
            },
        )
        current = response.structured_content
        first = current["state"]
        assert current["status"] == "clarification"
        for answer in [
            "My electricity bill",
            "My last bill was $142.10",
            "When my next bill arrives",
        ]:
            assert client.get("/api/v1/expectations").json() == []
            response = await mcp.call_tool(
                "continue_expectation_compilation",
                {"request": {"state": current["state"], "answer": answer}},
            )
            assert not response.is_error
            current = response.structured_content
        assert current["status"] == "compiled"
        payload = current["expectation"]
        arguments = {
            "request": {**payload, "compilation_state": current["capture_state"]}
        }
        saved = await mcp.call_tool("capture_expectation", arguments)
        replay = await mcp.call_tool("capture_expectation", arguments)
        assert saved.structured_content["id"] == replay.structured_content["id"]
        rows = client.get("/api/v1/expectations").json()
        assert len(rows) == 1 and rows[0]["baseline"] == 142.1
        assert (
            client.get(f"/api/v1/expectations/{rows[0]['id']}").json()["deadline"]
            is None
        )
        with pytest.raises(StateError):
            capture_compiled(
                db,
                ExpectationCreate.model_validate(payload),
                current["capture_state"],
                users[1].id,
            )
        async with Client(server(), raise_exceptions=False) as safe_client:
            stale = await safe_client.call_tool(
                "continue_expectation_compilation",
                {"request": {"state": first, "answer": "My electricity bill"}},
            )
            assert stale.is_error
        assert runtime.converse.call_count == 4


@pytest.mark.parametrize(
    "case", ["valid", "unavailable", "invalid_citation", "no_evidence"]
)
def test_why_grounding_fallback_and_provenance(monkeypatch, case):
    from botocore.exceptions import EndpointConnectionError

    from tests.test_mismatch_investigator import adapter, draft, inputs

    expectation, evaluation, evidence = data = inputs()
    if case == "no_evidence":
        evidence.clear()
    output = draft(data)
    if case == "invalid_citation":
        output["key_factors"][0]["evidence_refs"] = ["E99"]
    if case == "unavailable":
        output = EndpointConnectionError(endpoint_url="https://private-provider.test")
    selected, runtime = adapter(output)
    monkeypatch.setattr(
        intelligence.expectation_service,
        "get_expectation",
        Mock(return_value=expectation),
    )
    monkeypatch.setattr(
        intelligence.evaluation_service,
        "get_latest_evaluation",
        Mock(return_value=evaluation),
    )
    monkeypatch.setattr(
        intelligence.evidence_repository,
        "investigation_evidence",
        Mock(return_value=evidence),
    )
    original = intelligence.investigation_service.investigate_mismatch
    monkeypatch.setattr(
        intelligence.investigation_service,
        "investigate_mismatch",
        lambda **kwargs: original(**kwargs, investigator=selected),
    )
    result = intelligence.explain_request(
        Mock(),
        intelligence.ExplainMismatchInput(expectation_id=expectation.id),
        expectation.user_id,
    )
    assert result.result == "MISMATCH"
    assert (
        result.expectation_id == expectation.id
        and result.evaluation_id == evaluation.id
    )
    assert set(result.evidence_ids) <= {item.id for item in evidence}
    assert result.bedrock_used == (case == "valid")
    assert result.fallback_used == (case != "valid")
    assert "private-provider" not in result.model_dump_json()
    assert "Energy markets" not in result.message
    assert str(expectation.id) not in result.message
    assert str(evaluation.id) not in result.message
    if case == "valid":
        assert "18%" in result.message and "22%" in result.message
        assert "could have contributed" in result.message
        assert len(result.evidence_ids) == 3
    else:
        assert "enough supporting evidence" in result.message
    if case == "no_evidence":
        runtime.converse.assert_not_called()


@pytest.mark.parametrize("result", ["MATCH", "UNKNOWN"])
def test_why_non_mismatch_never_reads_evidence_or_invokes_investigator(
    monkeypatch, result
):
    from tests.test_mismatch_investigator import inputs

    expectation, evaluation, _ = inputs()
    evaluation.result = result
    monkeypatch.setattr(
        intelligence.expectation_service,
        "get_expectation",
        Mock(return_value=expectation),
    )
    monkeypatch.setattr(
        intelligence.evaluation_service,
        "get_latest_evaluation",
        Mock(return_value=evaluation),
    )
    evidence = Mock(side_effect=AssertionError("No evidence read expected"))
    investigator = Mock(side_effect=AssertionError("No investigator expected"))
    monkeypatch.setattr(
        intelligence.evidence_repository, "investigation_evidence", evidence
    )
    monkeypatch.setattr(
        intelligence.investigation_service, "investigate_mismatch", investigator
    )
    output = intelligence.explain_request(
        Mock(),
        intelligence.ExplainMismatchInput(expectation_id=expectation.id),
        expectation.user_id,
    )
    assert output.result == result and output.evaluation_id == evaluation.id
    assert output.bedrock_used is False and output.fallback_used is False
    assert output.evidence_ids == []
    assert (
        "matched your expectation" in output.message
        if result == "MATCH"
        else "still watching" in output.message
    )
    evidence.assert_not_called()
    investigator.assert_not_called()


def test_why_other_owner_denied_before_any_intelligence(monkeypatch):
    from uuid import uuid4

    from app.core.exceptions import ExpectationNotFoundError

    identity = uuid4()
    monkeypatch.setattr(
        intelligence.expectation_service,
        "get_expectation",
        Mock(side_effect=ExpectationNotFoundError(identity)),
    )
    latest = Mock()
    investigator = Mock()
    monkeypatch.setattr(
        intelligence.evaluation_service, "get_latest_evaluation", latest
    )
    monkeypatch.setattr(
        intelligence.investigation_service, "investigate_mismatch", investigator
    )
    with pytest.raises(ExpectationNotFoundError):
        intelligence.explain_request(
            Mock(), intelligence.ExplainMismatchInput(expectation_id=identity), uuid4()
        )
    latest.assert_not_called()
    investigator.assert_not_called()


@pytest.mark.asyncio
async def test_intelligence_acceptance_compile_capture_evaluate_explain_then_match(
    server, enabled, monkeypatch, client, db
):
    from app.ai.investigation_evidence import normalize
    from tests.test_clarification import decision, engine, initial, patch
    from tests.test_mismatch_investigator import adapter

    selected, _ = engine(
        initial("MISSING_BASELINE", "baseline"),
        decision(patch("baseline", 142.1, "$142.10")),
        decision(
            patch("deadline", "When my next bill arrives", "When my next bill arrives")
        ),
    )
    start = compiler_service.start_expectation_compilation
    continue_ = compiler_service.continue_expectation_compilation
    monkeypatch.setattr(
        compiler_service,
        "start_expectation_compilation",
        lambda text, context, **kwargs: start(text, context, engine=selected, **kwargs),
    )
    monkeypatch.setattr(
        compiler_service,
        "continue_expectation_compilation",
        lambda state, answer, context: continue_(
            state, answer, context, engine=selected
        ),
    )
    original = intelligence.investigation_service.investigate_mismatch

    def explain(**kwargs):
        facts = normalize(**kwargs, max_evidence=6)
        values = {fact.ref: fact.value for fact in facts.evidence}
        draft = {
            "expected": facts.expected.model_dump(mode="json"),
            "observed": facts.observed.model_dump(mode="json"),
            "summary_kind": "possible_contribution",
            "key_factors": [
                {
                    "kind": "possible_rate_offset",
                    "evidence_refs": list(values),
                    "values": values,
                }
            ],
        }
        investigator, _ = adapter(draft)
        return original(**kwargs, investigator=investigator)

    spy = Mock(side_effect=explain)
    monkeypatch.setattr(intelligence.investigation_service, "investigate_mismatch", spy)
    async with Client(server(), raise_exceptions=True) as mcp:
        result = await mcp.call_tool(
            "compile_expectation",
            {
                "request": {
                    "text": "I'm counting on my electricity bill being lower than my last bill.",
                    "timezone": "UTC",
                    "locale": "en-US",
                    "conversational": True,
                }
            },
        )
        turn = result.structured_content
        for answer in ["My last bill was $142.10", "When my next bill arrives"]:
            assert client.get("/api/v1/expectations").json() == []
            result = await mcp.call_tool(
                "continue_expectation_compilation",
                {"request": {"state": turn["state"], "answer": answer}},
            )
            assert not result.is_error
            turn = result.structured_content
        assert turn["status"] == "compiled"
        result = await mcp.call_tool(
            "capture_expectation",
            {
                "request": {
                    **turn["expectation"],
                    "compilation_state": turn["capture_state"],
                }
            },
        )
        identity = result.structured_content["id"]
        assert (
            client.get(f"/api/v1/expectations/{identity}").json()["baseline"] == 142.1
        )
        evidence_ids = []
        for metric, value, unit in [
            ("total_cost", {"amount": 162}, "USD"),
            ("energy_usage_change", {"percentage": -18}, "percent"),
            ("rate_change", {"percentage": 22}, "percent"),
        ]:
            response = client.post(
                f"/api/v1/expectations/{identity}/evidence",
                json={
                    "source": "utility_bill",
                    "metric": metric,
                    "value": value,
                    "unit": unit,
                    "observed_at": "2026-10-01T20:00:00Z",
                },
            )
            assert response.status_code == 201
            evidence_ids.append(response.json()["id"])
        evaluation = client.post(f"/api/v1/expectations/{identity}/evaluate").json()
        assert evaluation["result"] == "MISMATCH"
        response = await mcp.call_tool(
            "explain_expectation_mismatch", {"request": {"expectation_id": identity}}
        )
        why = response.structured_content
        assert why["bedrock_used"] and not why["fallback_used"]
        assert (
            why["evaluation_id"] == evaluation["id"]
            and why["expectation_id"] == identity
        )
        assert set(why["evidence_ids"]) == set(evidence_ids)
        assert "could have contributed" in why["message"]
        assert spy.call_count == 1
        response = client.post(
            f"/api/v1/expectations/{identity}/evidence",
            json={
                "source": "utility_bill",
                "metric": "total_cost",
                "value": {"amount": 130},
                "unit": "USD",
                "observed_at": "2026-10-02T20:00:00Z",
            },
        )
        assert response.status_code == 201
        match = client.post(f"/api/v1/expectations/{identity}/evaluate").json()
        assert match["result"] == "MATCH"
        from app.db.models import Evaluation

        # Both commits are savepoints within a single test transaction, so now()
        # is shared. Give the history an explicit later timestamp for this case.
        matched = db.get(Evaluation, UUID(match["id"]))
        matched.created_at += timedelta(seconds=1)
        db.flush()
        response = await mcp.call_tool(
            "explain_expectation_mismatch", {"request": {"expectation_id": identity}}
        )
        assert response.structured_content["message"] == "It matched your expectation."
        assert response.structured_content["evaluation_id"] == match["id"]
        assert not response.structured_content["bedrock_used"]
        assert spy.call_count == 1  # Latest MATCH overrides the historical mismatch.
