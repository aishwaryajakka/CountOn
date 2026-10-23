"""Cold imports, ASGI startup and SDK registration without cloud or database I/O."""

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import httpx2
import pytest
from mcp import Client
from pydantic import SecretStr
from starlette.testclient import TestClient

from app.agent.adapters import StreamableMcpAdapter
from app.core.auth import AuthenticatedUser
from app.core.config import Settings
from app.db import models
from app.db.base import Base
from app.main import app
from app.mcp.server import create_server

TOOLS = {
    "capture_expectation",
    "get_expectation",
    "list_expectations",
    "compile_expectation",
    "continue_expectation_compilation",
    "explain_expectation_mismatch",
}


@pytest.mark.parametrize("reverse", [False, True])
def test_all_application_modules_import_in_fresh_process(reverse):
    backend = Path(__file__).resolve().parents[1]
    # No production environment, .env.local, network, AWS or DB dependency at import.
    environment = {
        k: v for k, v in os.environ.items() if k in ("PATH", "SYSTEMROOT", "LANG")
    }
    environment.update(
        ENVIRONMENT="test",
        DATABASE_TARGET="local",
        LOCAL_DATABASE_URL="postgresql+psycopg://fixture@localhost/startup_test",
        AWS_EC2_METADATA_DISABLED="true",
    )
    script = """
import importlib, pathlib, socket, sys
import pydantic_settings, sqlalchemy, boto3
def sources(cls, settings_cls, init_settings, env_settings, dotenv_settings, file_secret_settings):
    return init_settings, env_settings
pydantic_settings.BaseSettings.settings_customise_sources = classmethod(sources)
def forbidden(*a, **k):
    raise AssertionError('Startup attempted external I/O')
socket.create_connection = forbidden
sqlalchemy.engine.Engine.connect = forbidden
boto3.client = forbidden
names = sorted('app.' + '.'.join(p.with_suffix('').parts[1:])
               for p in pathlib.Path('app').rglob('*.py')
               if p.name not in ('__init__.py', '__main__.py'))
if sys.argv[1] == 'True': names.reverse()
for name in names:
    try: importlib.import_module(name)
    except Exception as error:
        print(name, type(error).__name__)
        sys.exit(1)
print('All application modules imported')
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(reverse)],
        cwd=backend,
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    assert "All application modules imported" in result.stdout


def test_fastapi_lifespan_health_and_openapi_without_external_io(monkeypatch):
    def forbidden(*a, **k):
        pytest.fail("Startup must not connect to external services")

    monkeypatch.setattr("sqlalchemy.engine.Engine.connect", forbidden)
    monkeypatch.setattr("boto3.client", forbidden)
    with TestClient(app) as client:
        assert client.get("/health").json() == {
            "status": "ok",
            "service": "counton-api",
        }
        assert client.get("/docs").status_code == 200
        schema = client.get("/openapi.json")
        assert schema.status_code == 200
        assert "/api/v1/agent/converse" in schema.json()["paths"]
        assert (
            client.post("/api/v1/agent/converse", json={"text": "Hello"}).status_code
            == 401
        )


@pytest.mark.asyncio
async def test_exact_mcp_registration_contract():
    async with Client(create_server()) as client:
        registered = (await client.list_tools()).tools
        assert {tool.name for tool in registered} == TOOLS
        for tool in registered:
            assert set(tool.input_schema["properties"]) == {"request"}
            assert tool.input_schema["required"] == ["request"]
            assert tool.output_schema is not None


def test_every_public_model_is_exported_and_registered():
    assert {
        "AuditEvent",
        "MonitoringJob",
        "Notification",
        "IntegrationConnection",
        "CompilationSession",
    } <= set(models.__all__)
    for name in models.__all__:
        model = getattr(models, name)
        if hasattr(model, "__tablename__"):
            assert model.__tablename__ in Base.metadata.tables


@pytest.mark.asyncio
async def test_streamable_adapter_owns_sdk_httpx2_client_with_bounded_connect(
    monkeypatch,
):
    from contextlib import asynccontextmanager

    from app.agent import adapters

    settings = Settings(
        _env_file=None,
        database_target="local",
        local_database_url="postgresql+psycopg://fixture@localhost/startup_test",
        mcp_public_url="http://127.0.0.1:8003/mcp",
    )
    inspected = []

    def transport(url, *, http_client):
        assert isinstance(http_client, httpx2.AsyncClient)
        assert http_client.timeout.connect == settings.http_connect_timeout
        assert http_client.timeout.pool == settings.http_connect_timeout
        assert http_client.timeout.read == 180
        assert http_client.follow_redirects is False
        inspected.append(http_client)
        return object()

    @asynccontextmanager
    async def client(*args, **kwargs):
        async def list_tools():
            return SimpleNamespace(tools=[SimpleNamespace(name=name) for name in TOOLS])

        yield SimpleNamespace(list_tools=list_tools)

    monkeypatch.setattr(adapters, "streamable_http_client", transport)
    monkeypatch.setattr(adapters, "Client", client)
    adapter = StreamableMcpAdapter(settings, SecretStr("private-fixture"))
    async with adapter._client(AuthenticatedUser(uuid4())):
        assert len(inspected) == 1
    assert inspected[0].is_closed
