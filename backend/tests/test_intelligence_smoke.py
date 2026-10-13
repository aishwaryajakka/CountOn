"""Safety of opt-in tagged write/cleanup tooling, including lost acknowledgements."""

from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import httpx
import pytest
from db.scripts import intelligence_smoke as script
from db.scripts.mcp_smoke import SmokeFailure


@pytest.mark.asyncio
@pytest.mark.parametrize("lost_ack", [False, True])
async def test_cleanup_only_exact_run_tag_and_recover_lost_ack(monkeypatch, lost_ack):
    claim = "My grocery bill should stay under $120 this week. [counton-intelligence-smoke:00000000-0000-0000-0000-000000000001]"
    calls = []
    deleted = []

    class Api:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, **kwargs):
            if url.endswith("/expectations"):
                return httpx.Response(
                    200,
                    json=[
                        {"id": "00000000-0000-0000-0000-000000000002", "claim": claim},
                        {"id": "unrelated", "claim": "Keep unrelated data"},
                    ],
                )
            if url.endswith("/00000000-0000-0000-0000-000000000002"):
                return httpx.Response(
                    404 if deleted else 200, json={} if deleted else {"claim": claim}
                )
            return httpx.Response(200, json={"claim": claim})

        async def delete(self, url):
            deleted.append(url.rsplit("/", 1)[-1])
            return httpx.Response(204)

    class Mcp:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def list_tools(self):
            return SimpleNamespace(
                tools=[SimpleNamespace(name=name) for name in script.TOOLS]
            )

        async def call_tool(self, name, arguments):
            calls.append((name, arguments))
            if name == "compile_expectation":
                data = {
                    "status": "compiled",
                    "expectation": {
                        "claim": claim,
                        "type": "numeric_comparison",
                        "metric": "total_cost",
                        "comparison": "less_than",
                        "target_value": 120,
                    },
                }
            elif name == "capture_expectation":
                if lost_ack:
                    raise SmokeFailure("Lost acknowledgement")
                data = {"id": "00000000-0000-0000-0000-000000000002"}
            elif name == "get_expectation":
                data = {"claim": claim}
            else:
                data = {"expectations": []}
            return SimpleNamespace(is_error=False, structured_content=data)

    api = Api()
    monkeypatch.setattr(script, "uuid4", lambda: UUID(int=1))
    monkeypatch.setattr(script.httpx, "AsyncClient", lambda **kwargs: api)
    monkeypatch.setattr(script.httpx2, "AsyncClient", lambda **kwargs: Api())
    monkeypatch.setattr(script, "streamable_http_client", lambda *args, **kwargs: None)
    monkeypatch.setattr(script, "Client", lambda *args, **kwargs: Mcp())
    if lost_ack:
        with pytest.raises(SmokeFailure):
            await script.probe(
                "https://mcp.test/mcp",
                "https://api.test",
                "private-token",
                compile_=True,
                capture=True,
            )
    else:
        await script.probe(
            "https://mcp.test/mcp",
            "https://api.test",
            "private-token",
            compile_=True,
            capture=True,
        )
    assert (
        "unrelated" not in deleted and "00000000-0000-0000-0000-000000000002" in deleted
    )
    assert all(set(arguments) == {"request"} for _, arguments in calls)


@pytest.mark.asyncio
async def test_tagless_compilation_cannot_capture(monkeypatch):
    class Context:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def list_tools(self):
            return SimpleNamespace(
                tools=[SimpleNamespace(name=name) for name in script.TOOLS]
            )

        async def call_tool(self, name, arguments):
            assert name != "capture_expectation"
            return SimpleNamespace(
                is_error=False,
                structured_content={
                    "status": "compiled",
                    "expectation": {"claim": "No run tag"},
                },
            )

    monkeypatch.setattr(script.httpx, "AsyncClient", lambda **kwargs: Context())
    monkeypatch.setattr(script.httpx2, "AsyncClient", lambda **kwargs: Context())
    monkeypatch.setattr(script, "streamable_http_client", Mock())
    monkeypatch.setattr(script, "Client", lambda *args, **kwargs: Context())
    with pytest.raises(SmokeFailure):
        await script.probe(
            "https://mcp.test/mcp",
            "https://api.test",
            "private-token",
            compile_=True,
            capture=True,
        )
