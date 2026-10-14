"""Utterance-only auth boundary and real Streamable HTTP integration."""

from contextlib import contextmanager
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.agent.actions import CapabilityTool
from app.agent.adapters import StreamableMcpAdapter
from app.api import dependencies
from app.api.v1 import agent as route
from app.main import app
from app.mcp import auth
from app.mcp.server import create_app, create_server
from app.schemas.evidence import EvidenceCreate
from app.services import evaluation_service, evidence_service, expectation_service
from tests import test_agent as shared
from tests import test_auth as signed
from tests.test_mcp_network import live_server

settings, real_adapter, wire_engine = (
    shared.settings,
    shared.real_adapter,
    shared.wire_engine,
)
verifier = signed.verifier


@pytest.fixture
def wired(client, real_adapter, settings, monkeypatch):
    from app.agent import orchestrator

    monkeypatch.setattr(orchestrator, "get_settings", lambda: settings)
    app.dependency_overrides[route.remote_adapter] = lambda: real_adapter
    try:
        yield client
    finally:
        app.dependency_overrides.pop(route.remote_adapter, None)


def converse(client, text, reference=None):
    response = client.post(
        "/api/v1/agent/converse",
        json={"text": text, "session_reference": reference},
        headers={"Accept-Language": "en-US"},
    )
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    return response.json()


@pytest.mark.parametrize(
    "field",
    [
        "tool",
        "user_id",
        "plan",
        "action",
        "result",
        "expectation_id",
        "clarification_state",
        "aws_credentials",
    ],
)
def test_route_rejects_client_execution_and_identity_injection(wired, field):
    response = wired.post(
        "/api/v1/agent/converse",
        json={"text": "Hello", "session_reference": None, field: "private-sentinel"},
    )
    assert response.status_code == 422
    assert "private-sentinel" not in response.text


def test_api_list_get_context_why_and_filtered_output(wired, db, users):
    row = expectation_service.create_expectation(db, shared.payload(), users[0].id)
    listed = converse(wired, "What am I counting on?")
    assert listed["rows"][0]["id"] == str(row.id)
    selected = converse(
        wired, "Tell me about my electricity bill", listed["session_reference"]
    )
    why = converse(wired, "Why did it fail?", selected["session_reference"])
    assert why["status"] == "SUCCESS" and "evaluation" in why["answer"]
    assert why["saved_id"] is None and not why["captured"]
    forbidden = {
        "compiled_expectation",
        "clarification_state",
        "capture_state",
        "explanation",
        "evaluation_id",
        "evidence_ids",
        "user_id",
        "bedrock_used",
        "fallback_used",
    }
    assert not set(why).intersection(forbidden)
    assert why["traces"][-1] == {
        "layer": "MCP",
        "label": "explain_expectation_mismatch",
    }


@pytest.mark.parametrize(
    "amount,result_name", [(130, "MATCH"), (None, "UNKNOWN"), (162, "MISMATCH")]
)
def test_api_evaluation_gate_and_fallback(
    wired, db, users, settings, monkeypatch, amount, result_name
):
    from app.ai.mismatch_investigator import BedrockMismatchInvestigator
    from app.mcp import intelligence

    row = expectation_service.create_expectation(db, shared.payload(), users[0].id)
    if amount is not None:
        evidence_service.add_evidence(
            db,
            row.id,
            EvidenceCreate(
                source="utility_bill",
                metric="total_cost",
                value={"amount": amount},
                unit="USD",
                observed_at=datetime.now(timezone.utc),
                confidence=1,
            ),
            users[0].id,
        )
    evaluation_service.evaluate_expectation(db, row.id, users[0].id)
    calls = []
    original = intelligence.investigation_service.investigate_mismatch

    def investigate(**kwargs):
        calls.append(True)
        investigator = BedrockMismatchInvestigator(
            settings=settings.model_copy(update={"bedrock_enabled": False})
        )
        try:
            return original(**kwargs, investigator=investigator)
        finally:
            investigator.close()

    monkeypatch.setattr(
        intelligence.investigation_service, "investigate_mismatch", investigate
    )
    selected = converse(wired, "Tell me about my electricity bill")
    why = converse(wired, "Why did it fail?", selected["session_reference"])
    assert len(calls) == (1 if result_name == "MISMATCH" else 0)
    assert why["status"] == "SUCCESS"
    assert all(event["layer"] != "Bedrock" for event in why["traces"])


@pytest.mark.parametrize("mode", ["oneshot", "clarification", "correction", "cancel"])
def test_api_capture_conversation_dashboard_persistence(wired, wire_engine, mode):
    from tests.test_clarification import decision, initial, patch
    from tests.test_expectation_compiler import compiled

    if mode == "oneshot":
        wire_engine(compiled())
        turn = converse(
            wired, "I'm counting on my grocery bill staying under $120 this week"
        )
    else:
        outputs = [
            initial(),
            decision(patch("subject", "electricity bill", "electricity bill")),
            decision(
                patch("operand", "baseline", "last bill"),
                patch("baseline", 142, "$142"),
            ),
        ]
        answers = ["My electricity bill", "My last bill was $142"]
        if mode == "correction":
            outputs.append(decision(patch("baseline", 150, "$150"), kind="correction"))
            answers.append("Actually make that $150")
        if mode == "cancel":
            answers.append("Never mind")
        else:
            outputs.append(
                decision(
                    patch(
                        "deadline",
                        "When my next bill arrives",
                        "When my next bill arrives",
                    )
                )
            )
            answers.append("When my next bill arrives")
        wire_engine(*outputs)
        turn = converse(wired, "I'm counting on my bill being lower")
        for answer in answers:
            assert (
                turn["clarification_required"]
                and wired.get("/api/v1/expectations").json() == []
            )
            turn = converse(wired, answer, turn["session_reference"])
    if mode != "cancel":
        assert turn["clarification_required"] and not turn["captured"]
        assert "Should I save it?" in turn["answer"]
        assert wired.get("/api/v1/expectations").json() == []
        pending = turn["session_reference"]
        assert not any(step["label"] == "capture_expectation" for step in turn["traces"])
        turn = converse(wired, "Yes", pending)
        assert sum(step["label"] == "capture_expectation" for step in turn["traces"]) == 1
        assert converse(wired, "Yes", pending)["code"] == "STATE_REJECTED"
    assert turn["captured"] == (mode != "cancel")
    records = wired.get("/api/v1/expectations").json()
    assert len(records) == (0 if mode == "cancel" else 1)
    if mode != "cancel":
        assert records[0]["id"] == turn["saved_id"]
        assert (
            wired.get("/api/v1/expectations/" + turn["saved_id"]).json()["claim"]
            == turn["rows"][0]["claim"]
        )
        assert not any(
            key in turn
            for key in ("capture_state", "clarification_state", "compiled_expectation")
        )


def test_web_capture_confirmation_can_be_declined_without_persistence(wired, wire_engine):
    from tests.test_expectation_compiler import compiled

    wire_engine(compiled())
    pending = converse(wired, "I'm counting on my grocery bill staying under $120 this week")
    assert pending["clarification_required"] and not pending["captured"]
    declined = converse(wired, "No", pending["session_reference"])
    assert not declined["captured"]
    assert wired.get("/api/v1/expectations").json() == []
    replay = converse(wired, "Yes", pending["session_reference"])
    assert replay["code"] == "STATE_REJECTED" and not replay["captured"]


def test_invalid_auth_never_reaches_orchestrator(monkeypatch):
    from app.core.exceptions import AuthenticationError

    class Reject:
        def verify(self, token):
            raise AuthenticationError()

    monkeypatch.setattr(dependencies, "get_token_verifier", lambda: Reject())
    app.dependency_overrides[dependencies.get_db] = lambda: None
    try:
        with TestClient(app) as client:
            for headers in ({}, {"Authorization": "Bearer invalid-private-token"}):
                response = client.post(
                    "/api/v1/agent/converse",
                    headers=headers,
                    json={"text": "Hello", "session_reference": None},
                )
                assert (
                    response.status_code == 401
                    and "invalid-private-token" not in response.text
                )
    finally:
        app.dependency_overrides.pop(dependencies.get_db, None)


def test_real_http_adapter_full_agent_path_and_shared_dashboard(
    db, users, verifier, settings, monkeypatch, wire_engine
):
    from app.agent import orchestrator
    from tests.test_expectation_compiler import compiled

    verified, key = verifier
    encoded, _ = signed.token(verified, key, sub=str(users[0].id))
    monkeypatch.setattr(auth, "get_token_verifier", lambda: verified)
    monkeypatch.setattr(dependencies, "get_token_verifier", lambda: verified)

    @contextmanager
    def factory():
        yield db

    def api_db():
        yield db

    app.dependency_overrides[dependencies.get_db] = api_db
    wire_engine(compiled())
    try:
        with live_server(create_app(create_server(session_factory=factory))) as base:
            configured = settings.model_copy(update={"mcp_public_url": base + "/mcp"})
            monkeypatch.setattr(route, "get_settings", lambda: configured)
            monkeypatch.setattr(orchestrator, "get_settings", lambda: configured)
            with TestClient(app) as client:
                client.headers.update({"Authorization": "Bearer " + encoded})
                listed = converse(client, "What am I counting on?")
                assert listed["rows"] == []
                saved = converse(
                    client,
                    "I'm counting on my grocery bill staying under $120 this week",
                    listed["session_reference"],
                )
                assert not saved["captured"]
                assert client.get("/api/v1/expectations").json() == []
                saved = converse(client, "Yes", saved["session_reference"])
                assert saved["captured"] and saved["saved_id"]
                assert (
                    client.get("/api/v1/expectations").json()[0]["id"]
                    == saved["saved_id"]
                )
                viewed = converse(
                    client, "Tell me about my grocery bill", saved["session_reference"]
                )
                why = converse(client, "Why did it fail?", viewed["session_reference"])
                assert why["status"] == "SUCCESS"
                for response in (listed, saved, viewed, why):
                    assert encoded not in str(response)
                repeated = converse(
                    client,
                    "I'm counting on my grocery bill staying under $120 this week",
                    listed["session_reference"],
                )
                assert repeated["code"] == "STATE_REJECTED"
                assert len(client.get("/api/v1/expectations").json()) == 1
    finally:
        app.dependency_overrides.pop(dependencies.get_db, None)


@pytest.mark.asyncio
async def test_http_adapter_invalid_token_is_safe_unauthorized(
    db, users, settings, verifier, monkeypatch
):
    from app.agent.actions import FailureCode
    from app.agent.adapters import CapabilityError
    from app.mcp.schemas import ListExpectationsInput

    verified, _ = verifier
    monkeypatch.setattr(auth, "get_token_verifier", lambda: verified)

    @contextmanager
    def factory():
        yield db

    with live_server(create_app(create_server(session_factory=factory))) as base:
        adapter = StreamableMcpAdapter(
            settings.model_copy(update={"mcp_public_url": base + "/mcp"}),
            SecretStr("invalid-private-token"),
        )
        with pytest.raises(CapabilityError) as caught:
            await adapter.call(users[0], CapabilityTool.LIST, ListExpectationsInput())
        assert caught.value.code == FailureCode.UNAUTHORIZED
        assert "invalid-private-token" not in str(caught.value)


@pytest.mark.parametrize(
    "text", ["What's being monitored?", "What is being monitored?"]
)
def test_existing_list_aliases_remain_supported(wired, text):
    output = converse(wired, text)
    assert output["action"] == "LIST_EXPECTATIONS"
    assert output["status"] == "SUCCESS"


def test_bedrock_failure_is_distinct_from_mcp_unreachability(wired, wire_engine):
    wire_engine("not JSON", "not JSON")
    output = converse(wired, "I'm counting on my grocery bill under $120 this week")
    assert output["status"] == "FAILED"
    assert output["code"] == "INTELLIGENCE_UNAVAILABLE"
    assert not output["captured"]
    assert any(step["layer"] == "MCP" for step in output["traces"])
