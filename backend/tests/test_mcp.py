"""MCP foundation checks without Alexa, credentials, or database migrations."""

from importlib import import_module
from unittest.mock import Mock
from uuid import UUID

import pytest
from mcp import Client
from pydantic import ValidationError
from sqlalchemy.engine import Engine
from starlette.testclient import TestClient

from app.core.auth import AuthenticatedUser
from app.core.exceptions import AuthenticationError
from app.mcp import auth
from app.mcp.schemas import CaptureExpectationInput, GetExpectationInput, ListExpectationsInput
from app.mcp.server import create_server

DESCRIPTIONS = {
    "capture_expectation": "Stores a structured expectation the current user wants CountOn to monitor.",
    "get_expectation": "Returns one expectation and its current status.",
    "list_expectations": "Lists the current user's expectations.",
}


def test_package_imports():
    for name in ("app.mcp", "app.mcp.server", "app.mcp.tools", "app.mcp.schemas", "app.mcp.auth", "app.mcp.compiler"):
        assert import_module(name)


@pytest.mark.asyncio
async def test_registered_names_descriptions_and_schemas():
    async with Client(create_server(), raise_exceptions=True) as client:
        result = await client.list_tools()
        assert {tool.name: tool.description for tool in result.tools} == DESCRIPTIONS
        for tool in result.tools:
            schema = tool.input_schema
            assert "request" in schema["properties"]
            assert "user_id" not in str(schema)
            assert tool.output_schema is not None
            assert tool.annotations.read_only_hint == (tool.name != "capture_expectation")
            assert tool.annotations.idempotent_hint == (tool.name != "capture_expectation")
            assert tool.annotations.destructive_hint is False


def test_streamable_http_initializes_without_database_or_evaluation(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("MCP foundation must not connect, migrate, or evaluate")

    monkeypatch.setattr(Engine, "connect", forbidden)
    from alembic import command
    from app.evaluators import boolean, numeric, temporal
    monkeypatch.setattr(command, "upgrade", forbidden)
    for module in (boolean, numeric, temporal):
        monkeypatch.setattr(module, "evaluate", forbidden)

    server = create_server()
    app = server.streamable_http_app(stateless_http=True, json_response=True)
    headers = {"Accept": "application/json, text/event-stream"}
    with TestClient(app, base_url="http://127.0.0.1:8003") as client:
        response = client.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "counton-test", "version": "1"}},
        })
        assert response.status_code == 200
        assert response.json()["result"]["serverInfo"]["name"] == "CountOn"
        headers["MCP-Protocol-Version"] = "2025-06-18"
        response = client.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {},
        })
        assert response.status_code == 200
        assert {tool["name"] for tool in response.json()["result"]["tools"]} == set(DESCRIPTIONS)
        inputs = {
            "capture_expectation": {"claim": "My bill will be lower", "type": "numeric_comparison",
                                    "metric": "total_cost", "comparison": "less_than", "baseline": 142.1},
            "get_expectation": {"expectation_id": "00000000-0000-0000-0000-000000000001"},
            "list_expectations": {},
        }
        for index, (name, request) in enumerate(inputs.items(), start=3):
            response = client.post("/mcp", headers=headers, json={
                "jsonrpc": "2.0", "id": index, "method": "tools/call",
                "params": {"name": name, "arguments": {"request": request}},
            })
            assert response.status_code == 200
            result = response.json()["result"]
            assert result["isError"] is True
            assert "UNAUTHORIZED" in result["content"][0]["text"]


@pytest.mark.parametrize("model,payload", [
    (CaptureExpectationInput, {"claim": "Watch my bill", "type": "numeric_comparison"}),
    (GetExpectationInput, {"expectation_id": "00000000-0000-0000-0000-000000000001"}),
    (ListExpectationsInput, {}),
])
def test_inputs_reject_supplied_identity(model, payload):
    with pytest.raises(ValidationError):
        model.model_validate(dict(payload, user_id="00000000-0000-0000-0000-000000000001"))


@pytest.mark.parametrize("payload", [{"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_list_bounds(payload):
    with pytest.raises(ValidationError):
        ListExpectationsInput.model_validate(payload)


@pytest.mark.parametrize("header", [None, "", "Basic value", "Bearer", "Bearer one two"])
def test_auth_seam_rejects_missing_or_malformed_header(header, monkeypatch):
    verifier_factory = Mock()
    monkeypatch.setattr(auth, "get_token_verifier", verifier_factory)
    with pytest.raises(AuthenticationError):
        auth.authenticated_user_from_header(header)
    verifier_factory.assert_not_called()


def test_auth_seam_delegates_to_existing_verifier(monkeypatch):
    identity = AuthenticatedUser(UUID("00000000-0000-0000-0000-000000000001"))
    verifier = Mock()
    verifier.verify.return_value = identity
    monkeypatch.setattr(auth, "get_token_verifier", lambda: verifier)
    assert auth.authenticated_user_from_header("bearer test-token") is identity
    verifier.verify.assert_called_once_with("test-token")
    verifier.verify.side_effect = AuthenticationError()
    with pytest.raises(AuthenticationError):
        auth.authenticated_user_from_header("Bearer rejected-token")
