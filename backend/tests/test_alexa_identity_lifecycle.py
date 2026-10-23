"""Signed ASK + linked-client JWT + real MCP HTTP + owned PostgreSQL acceptance.

Only signing/JWKS and model inference use local fixtures. Supabase's actual
authorization-code issuance and Alexa device recognition remain external tests.
"""

import json
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from app.api import dependencies
from app.api.v1 import alexa as route
from app.core.auth import AuthenticatedUser
from app.main import app
from app.mcp import auth
from app.mcp.server import create_app, create_server
from tests import test_agent, test_alexa, test_auth
from tests.test_clarification import decision, initial, patch
from tests.test_mcp_network import live_server

settings = test_agent.settings
wire_engine = test_agent.wire_engine
verifier = test_auth.verifier
signing = test_alexa.signing
CLIENT = "alexa-linked-fixture-client"


@pytest.mark.parametrize("client_claim", [None, "other-approved-client"])
def test_alexa_rejects_nonlinked_client_before_profile_access(
    verifier, signing, settings, monkeypatch, client_claim
):
    checked, key = verifier
    checked.allowed_client_ids = {CLIENT, "other-approved-client"}
    changes = {"client_id": client_claim} if client_claim else {}
    token, _ = test_auth.token(checked, key, **changes)
    monkeypatch.setattr(route, "get_token_verifier", lambda: checked)
    monkeypatch.setattr(route, "get_settings", lambda: settings.model_copy(update={
        "alexa_skill_id": test_alexa.SKILL, "alexa_oauth_client_id": CLIENT,
    }))
    monkeypatch.setattr(route, "SessionLocal", lambda: pytest.fail("Wrong linked client reached persistence"))
    _, sign = signing
    with TestClient(app) as client:
        response = test_alexa.post(client, sign, test_alexa.event_body(token=token))
    assert response["response"]["card"] == {"type": "LinkAccount"}
    assert response["sessionAttributes"] == {}
    assert token not in json.dumps(response)


@pytest.mark.integration
@pytest.mark.parametrize("outcome", ["confirm", "cancel"])
def test_linked_identity_full_clarification_confirmation_and_web_visibility(
    db, users, verifier, signing, settings, wire_engine, monkeypatch, outcome, caplog
):
    checked, key = verifier
    checked.allowed_client_ids = {CLIENT}
    linked_token, _ = test_auth.token(checked, key, sub=str(users[0].id), client_id=CLIENT)
    web_token, _ = test_auth.token(checked, key, sub=str(users[0].id))
    other_token, _ = test_auth.token(checked, key, sub=str(users[1].id))
    other_linked_token, _ = test_auth.token(checked, key, sub=str(users[1].id), client_id=CLIENT)
    for module in (route, auth, dependencies):
        monkeypatch.setattr(module, "get_token_verifier", lambda: checked)

    @contextmanager
    def sessions():
        yield db

    monkeypatch.setattr(route, "SessionLocal", sessions)
    app.dependency_overrides[dependencies.get_db] = lambda: db
    runtime = wire_engine(
        initial(),
        decision(patch("subject", "electricity bill", "electricity bill")),
        decision(patch("operand", "baseline", "last bill")),
        decision(patch("baseline", 142.1, "$142.10")),
        decision(patch("baseline", 150, "$150"), kind="correction"),
        decision(patch("deadline", "When my next bill arrives", "When my next bill arrives")),
    )
    _, sign = signing

    def body(intent="CaptureExpectationIntent", text=None, attributes=None):
        data = test_alexa.event_body(intent=intent, text=text, attributes=attributes, token=linked_token)
        # Even a syntactically valid foreign CountOn UUID in Alexa's transport
        # userId cannot select the owner. Only the linked JWT sub authenticates.
        data["session"]["user"]["userId"] = str(users[1].id)
        data["context"]["System"]["user"]["userId"] = str(users[1].id)
        return data

    try:
        with live_server(create_app(create_server(session_factory=sessions), settings=settings)) as base:
            configured = settings.model_copy(update={
                "alexa_skill_id": test_alexa.SKILL, "alexa_oauth_client_id": CLIENT,
                "oauth_allowed_client_ids": [CLIENT], "alexa_require_confirmation": True,
                "mcp_public_url": base + "/mcp",
            })
            monkeypatch.setattr(route, "get_settings", lambda: configured)
            with TestClient(app) as client:
                client.headers.update({"Authorization": "Bearer " + web_token})
                assert route.authenticated_context(linked_token)[0] == AuthenticatedUser(users[0].id, CLIENT)
                turn = test_alexa.post(client, sign, body(text="I'm counting on my bill being lower."))
                assert "bill" in test_alexa.speech(turn).lower()
                foreign = body(text="My electricity bill.", attributes=turn["sessionAttributes"])
                foreign["context"]["System"]["user"]["accessToken"] = other_linked_token
                foreign["session"]["user"]["accessToken"] = other_linked_token
                raw, headers = sign(foreign)
                denied = client.post("/api/v1/alexa", content=raw, headers=headers)
                assert denied.status_code == 400
                assert other_linked_token not in denied.text
                for answer in ("My electricity bill.", "My last bill.", "My last bill was $142.10.", "Actually make that $150.", "When my next bill arrives"):
                    assert client.get("/api/v1/expectations").json() == []
                    current = body(text=answer, attributes=turn["sessionAttributes"])
                    turn = test_alexa.post(client, sign, current)
                    assert set(turn["sessionAttributes"]) == {"counton_session"}
                    if answer == "My electricity bill.":
                        assert "compare it against" in test_alexa.speech(turn)
                    if answer == "My last bill.":
                        assert "amount" in test_alexa.speech(turn).lower()
                        assert client.get("/api/v1/expectations").json() == []
                    calls = runtime.converse.call_count
                    assert test_alexa.post(client, sign, current) == turn
                    assert runtime.converse.call_count == calls
                assert "Should I save it?" in test_alexa.speech(turn)
                pending = turn["sessionAttributes"]
                confirmation = body(intent="AMAZON.YesIntent" if outcome == "confirm" else "AMAZON.CancelIntent", attributes=pending)
                saved = test_alexa.post(client, sign, confirmation)
                assert test_alexa.post(client, sign, confirmation) == saved
                # A new request ID carrying a consumed continuation is rejected.
                stale = test_alexa.post(client, sign, body(intent="AMAZON.YesIntent", attributes=pending))
                assert stale["response"]["shouldEndSession"] is True
                rows = client.get("/api/v1/expectations").json()
                assert len(rows) == (1 if outcome == "confirm" else 0)
                if rows:
                    assert rows[0]["user_id"] == str(users[0].id)
                    assert rows[0]["baseline"] == 150
                    assert rows[0]["compiler_metadata"]["creation_source"] == "alexa_skill"
                    assert client.get("/api/v1/expectations/" + rows[0]["id"]).json() == rows[0]
                else:
                    assert saved["sessionAttributes"] == {}
                    assert not client.app.state.agent_sessions._entries
                # Core snapshots contain references and bounded control metadata,
                # never a linked token, raw utterance, prompt or transcript.
                for entry in client.app.state.agent_sessions._entries.values():
                    state = entry.state.model_dump_json()
                    assert linked_token not in state and web_token not in state
                    assert "My electricity bill" not in state and "AWS" not in state
                client.headers.update({"Authorization": "Bearer " + other_token})
                assert client.get("/api/v1/expectations").json() == []
                for row in rows:
                    assert client.get("/api/v1/expectations/" + row["id"]).status_code == 404
                assert linked_token not in caplog.text and web_token not in caplog.text
    finally:
        app.dependency_overrides.pop(dependencies.get_db, None)
