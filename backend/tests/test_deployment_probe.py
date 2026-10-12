"""Remote smoke contracts are isolated from cloud accounts and never mutate rows."""

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest

from db.scripts import deployment_probe as probe

API = "https://api.example"
MCP = "https://mcp.example/mcp"
ORIGIN = "https://web.example"
TOKEN = "private-test-token"
ID = str(uuid4())
PATHS = ["/api/v1/agent/converse", "/api/v1/alexa", "/api/v1/expectations/{expectation_id}/monitoring"]


class MCPClient:
    def __init__(self, *, tools=None, empty=False, invalid_list=False, invalid_schema=False):
        self.names = probe.TOOLS if tools is None else tools
        self.empty = empty
        self.invalid_list = invalid_list
        self.invalid_schema = invalid_schema
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def list_tools(self):
        return SimpleNamespace(tools=[SimpleNamespace(name=name, input_schema={"properties": {"user_id" if self.invalid_schema else "request": {}}}) for name in self.names])

    async def call_tool(self, name, arguments):
        self.calls.append((name, arguments))
        row = {"id": ID, "claim": "private user claim"}
        return SimpleNamespace(is_error=self.invalid_list, structured_content={"expectations": [] if self.empty else [row]} if name == "list_expectations" else row)


def network(*, ready=200, missing_routes=False, foreign=False):
    calls = []

    def respond(request):
        calls.append(request)
        path = request.url.path
        if request.method == "OPTIONS":
            allowed = request.headers["origin"] == ORIGIN
            return httpx.Response(200 if allowed else 400, headers={"access-control-allow-origin": ORIGIN} if allowed else {})
        if path in ("/health", "/ready"):
            return httpx.Response(200 if path == "/health" else ready)
        if path == "/openapi.json":
            return httpx.Response(200, json={"paths": {} if missing_routes else dict.fromkeys(PATHS)})
        if path == "/mcp":
            return httpx.Response(401, json={"error": "private model output"})
        if request.headers.get("authorization") != "Bearer " + TOKEN:
            return httpx.Response(401)
        if path.endswith(ID):
            return httpx.Response(404 if foreign else 200, json={"id": ID, "claim": "private user claim"})
        return httpx.Response(200, headers={"access-control-allow-origin": ORIGIN}, json=[{"id": ID}])

    return httpx.MockTransport(respond), calls


def test_read_only_protocol_shared_row_nested_shape_and_redaction(capsys):
    http, calls = network()
    mcp = MCPClient()
    assert asyncio.run(probe.run(API, MCP, ORIGIN, TOKEN, http=http, mcp_factory=lambda: mcp)) == 0
    assert mcp.calls == [("list_expectations", {"request": {"limit": 1}}), ("get_expectation", {"request": {"expectation_id": ID}})]
    assert all(r.method in {"GET", "OPTIONS"} or r.url.path == "/mcp" for r in calls)
    text = capsys.readouterr().out
    assert "private" not in text and ID not in text
    assert "REMOTE MCP initialize" in text and "capture/worker/provider/browser/device/backup/edge-load acceptance: NOT RUN" in text


def test_missing_token_is_blocked_never_interactively_requested(capsys):
    http, _ = network()
    assert asyncio.run(probe.run(API, MCP, ORIGIN, http=http)) == 2
    assert "BLOCKED REMOTE" in capsys.readouterr().out


@pytest.mark.parametrize("options", [{"ready": 503}, {"missing_routes": True}, {"foreign": True}])
def test_failed_remote_readiness_contract_or_ownership_not_hidden(options):
    http, _ = network(**options)
    assert asyncio.run(probe.run(API, MCP, ORIGIN, TOKEN, http=http, mcp_factory=MCPClient)) == 1


@pytest.mark.parametrize("options", [{"tools": {"list_expectations"}}, {"invalid_schema": True}, {"invalid_list": True}])
def test_six_tool_contract_and_validation_failures(options):
    http, _ = network()
    assert asyncio.run(probe.run(API, MCP, ORIGIN, TOKEN, http=http, mcp_factory=lambda: MCPClient(**options))) == 1


def test_empty_list_cannot_claim_shared_persistence(capsys):
    http, _ = network()
    assert asyncio.run(probe.run(API, MCP, ORIGIN, TOKEN, http=http, mcp_factory=lambda: MCPClient(empty=True))) == 2
    assert "BLOCKED REMOTE get/shared-row" in capsys.readouterr().out


def test_transport_exception_does_not_echo_token_or_response(capsys):
    def broken(request):
        raise httpx.ConnectError("Authorization: " + TOKEN)
    assert asyncio.run(probe.run(API, MCP, ORIGIN, http=httpx.MockTransport(broken))) == 1
    assert TOKEN not in capsys.readouterr().out
