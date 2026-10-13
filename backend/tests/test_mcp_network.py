"""Real loopback HTTP with signed fixture JWTs and isolated PostgreSQL."""
import json
import logging
import socket
import threading
import time
from contextlib import contextmanager

import pytest
import uvicorn
from app.api import dependencies
from app.core.logging import StructuredFormatter
from app.core.observability import request_id
from app.main import app as api_app
from app.mcp import auth
from app.mcp.server import create_app, create_server
from db.scripts.mcp_smoke import loopback_url, smoke

# Reuse the existing signature/claim-verifying Auth fixture and token builder.
from tests.test_auth import token, verifier  # noqa: F401 — pytest fixture registration


@contextmanager
def live_server(app):
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    sock.listen(128)
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port,
        log_level='warning', access_log=False, log_config=None))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert server.started, 'Loopback server did not start'
        yield f'http://127.0.0.1:{port}'
    finally:
        server.should_exit = True
        thread.join(timeout=5)
        sock.close()
        assert not thread.is_alive(), 'Loopback server did not stop'


@pytest.mark.asyncio
async def test_full_network_smoke_signed_jwt_and_cleanup(db, users, verifier, monkeypatch):  # noqa: F811 — pytest fixture parameter
    verified, key = verifier
    encoded, _ = token(verified, key, sub=str(users[0].id))
    monkeypatch.setattr(auth, 'get_token_verifier', lambda: verified)
    monkeypatch.setattr(dependencies, 'get_token_verifier', lambda: verified)
    @contextmanager
    def factory():
        yield db
    def api_db():
        yield db
    api_app.dependency_overrides[dependencies.get_db] = api_db
    try:
        with live_server(create_app(create_server(session_factory=factory))) as mcp_url, live_server(api_app) as api_url:
            await smoke(mcp_url + '/mcp', api_url, encoded)
        from app.services import expectation_service
        assert expectation_service.list_expectations(db, users[0].id) == []
    finally:
        api_app.dependency_overrides.pop(dependencies.get_db, None)


def test_http_health_readiness_request_ids_and_failure(monkeypatch):
    from app.mcp import server as module
    from starlette.testclient import TestClient
    @contextmanager
    def broken():
        raise RuntimeError('password token SQL secret-sentinel')
        yield
    app = create_app(create_server(session_factory=broken))
    with TestClient(app, base_url='http://127.0.0.1:8003') as client:
        health = client.get('/health')
        assert health.status_code == 200 and health.json() == {'status': 'ok', 'service': 'counton-mcp'}
        failed = client.get('/ready')
        assert failed.status_code == 503 and 'secret' not in failed.text
        assert health.headers['x-request-id'] != failed.headers['x-request-id']
        assert request_id.get() is None
    @contextmanager
    def factory():
        yield object()
    monkeypatch.setattr(module, 'database_ready', lambda db: True)
    with TestClient(create_app(create_server(session_factory=factory)), base_url='http://127.0.0.1:8003') as client:
        assert client.get('/ready').status_code == 200


def test_tool_log_fields_and_no_input_values(caplog, monkeypatch):
    from uuid import UUID

    from app.core.auth import AuthenticatedUser
    from starlette.testclient import TestClient
    user = AuthenticatedUser(UUID(int=1))
    @contextmanager
    def factory():
        raise RuntimeError('secret-sentinel database URL password')
        yield
    monkeypatch.setattr(auth, 'authenticated_user_from_header', lambda header: user)
    app = create_app(create_server(session_factory=factory, user_resolver=lambda ctx: user))
    with caplog.at_level(logging.INFO), TestClient(app, base_url='http://127.0.0.1:8003') as client:
        response = client.post('/mcp', headers={'Accept': 'application/json, text/event-stream',
            'MCP-Protocol-Version': '2025-06-18'}, json={'jsonrpc': '2.0', 'id': 1,
            'method': 'tools/call', 'params': {'name': 'list_expectations', 'arguments': {'request': {}}}})
        assert response.status_code == 200
    records = [record for record in caplog.records if record.name == 'app.mcp.tools']
    assert len(records) == 1
    record = records[0]
    assert record.tool_name == 'list_expectations' and record.user_id == str(user.id)
    assert record.result_status == 'error' and record.duration_ms >= 0
    # Formatter includes safe MCP fields along with the existing log convention.
    formatted = json.loads(StructuredFormatter().format(record))
    assert formatted['tool_name'] == record.tool_name
    assert formatted['result_status'] == 'error'
    assert 'secret-sentinel' not in caplog.text


@pytest.mark.parametrize('value', ['https://remote.example/mcp', 'http://user:password@localhost/mcp',
    'http://localhost/mcp?token=secret', 'http://localhost/mcp#secret'])
def test_smoke_refuses_remote_or_credential_urls(value):
    import argparse
    with pytest.raises(argparse.ArgumentTypeError):
        loopback_url(value)


def test_valid_uuid_correlation_is_preserved_without_logging_headers():
    from app.mcp.server import create_app, create_server
    from starlette.testclient import TestClient
    with TestClient(create_app(create_server())) as client:
        value='12345678-1234-4234-8234-123456789abc'
        response=client.get('/health',headers={'X-Request-ID':value})
        assert response.headers['X-Request-ID']==value
        response=client.get('/health',headers={'X-Request-ID':'Bearer private-token'})
        assert response.headers['X-Request-ID']!='Bearer private-token'
