"""Deployment configuration and edge-compatible HTTP behavior; no live Alexa."""
from unittest.mock import Mock

import pytest
from pydantic import ValidationError
from starlette.testclient import TestClient

from tests.test_auth import verifier, token
from app.core.config import Settings
from app.mcp import auth
from app.mcp.server import create_app
from db.scripts.mcp_smoke import CORE_TOOLS
from db.scripts.mcp_remote_smoke import https_url, run


def config(**kwargs):
    return Settings(_env_file=None, database_target='local',
        local_database_url='postgresql+psycopg://fixture@localhost/fixture', **kwargs)


def test_host_port_startup_uses_existing_settings(monkeypatch):
    from app.mcp import __main__ as startup
    settings = config(mcp_host='0.0.0.0', mcp_port=9007)
    monkeypatch.setattr(startup, 'get_settings', lambda: settings)
    launch = Mock()
    monkeypatch.setattr(startup.uvicorn, 'run', launch)
    startup.main()
    launch.assert_called_once_with('app.mcp.server:app', host='0.0.0.0', port=9007,
        proxy_headers=False, access_log=False)


@pytest.mark.parametrize('changes', [
    {'mcp_host': 'http://secret@host'}, {'mcp_port': 0}, {'mcp_port': 65536},
    {'mcp_public_url': 'http://remote.example/mcp'}, {'mcp_public_url': 'https://remote.example/'},
    {'mcp_public_url': 'https://user:secret@remote.example/mcp'},
    {'mcp_public_url': 'https://remote.example/mcp?secret=value'},
    {'mcp_public_url': 'https://remote.example/mcp#secret'},
    {'mcp_public_url': 'https://bad host/mcp'}, {'mcp_public_url': 'https://remote.example:0/mcp'},
    {'mcp_allowed_origins': ['*']}, {'mcp_allowed_origins': ['https://*.example']},
    {'mcp_allowed_origins': ['https://example/path']},
])
def test_invalid_mcp_configuration_hides_values(changes):
    with pytest.raises(ValidationError) as error:
        config(**changes)
    assert 'secret@' not in str(error.value) and 'secret=value' not in str(error.value)


def test_public_url_and_environment_overrides(monkeypatch):
    monkeypatch.setenv('MCP_HOST', '0.0.0.0')
    monkeypatch.setenv('MCP_PORT', '9080')
    monkeypatch.setenv('MCP_PUBLIC_URL', 'https://mcp.counton.example/mcp')
    settings = config()
    assert (settings.mcp_host, settings.mcp_port, settings.mcp_public_url) == (
        '0.0.0.0', 9080, 'https://mcp.counton.example/mcp')
    assert settings.mcp_allowed_origins == []


def production(**changes):
    values = dict(_env_file=None, environment='production', database_target='supabase',
        supabase_database_url='postgresql+psycopg://fixture@cloud.example/postgres?sslmode=require',
        supabase_url='https://auth.example', supabase_publishable_key='public-fixture',
        allowed_origins=['https://frontend.example'])
    return Settings(**(values | changes))


def test_production_mcp_requires_public_https():
    # FastAPI-only deployments remain valid; starting production MCP needs URL.
    with pytest.raises(ValueError, match='MCP_PUBLIC_URL'):
        create_app(settings=production())
    for url in ('http://remote.example/mcp', 'https://localhost/mcp'):
        with pytest.raises(ValidationError):
            production(mcp_public_url=url)
    app = create_app(settings=production(mcp_public_url='https://mcp.example/mcp'))
    assert not app.debug
    with pytest.raises(ValidationError):
        production(mcp_allowed_origins=['http://localhost:3000'])


@pytest.mark.parametrize('authorization', [None, 'Bearer invalid-token', 'Basic invalid-token'])
def test_http_401_no_challenge_no_token_leak(authorization, verifier, monkeypatch):
    verified, _ = verifier
    monkeypatch.setattr(auth, 'get_token_verifier', lambda: verified)
    settings = config(mcp_public_url='https://mcp.example/mcp')
    with TestClient(create_app(settings=settings), base_url='https://mcp.example') as client:
        headers = {'Authorization': authorization} if authorization else {}
        response = client.post('/mcp', headers=headers, json={'jsonrpc': '2.0', 'id': 1, 'method': 'initialize'})
        assert response.status_code == 401 and 'www-authenticate' not in response.headers
        assert response.json()['error']['code'] == 'UNAUTHORIZED'
        assert 'invalid-token' not in response.text
        assert response.headers['x-request-id']
        assert client.get('/health').status_code == 200
        # OAuth discovery is not invented or advertised.
        assert client.get('/.well-known/oauth-protected-resource').status_code == 404


def test_remote_host_initialization_discovery_and_origin_policy(verifier, monkeypatch):
    verified, key = verifier
    encoded, _ = token(verified, key)
    check = Mock(wraps=verified.verify)
    monkeypatch.setattr(verified, 'verify', check)
    monkeypatch.setattr(auth, 'get_token_verifier', lambda: verified)
    settings = config(mcp_public_url='https://mcp.example/mcp',
        mcp_allowed_origins=['https://client.example'])
    headers = {'Authorization': f'Bearer {encoded}', 'Accept': 'application/json, text/event-stream'}
    with TestClient(create_app(settings=settings), base_url='https://mcp.example') as client:
        initialized = client.post('/mcp', headers=headers, json={
            'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {
                'protocolVersion': '2025-06-18', 'capabilities': {},
                'clientInfo': {'name': 'external-agent-test', 'version': '1'}}})
        assert initialized.status_code == 200
        assert initialized.json()['result']['serverInfo']['name'] == 'CountOn'
        headers['MCP-Protocol-Version'] = '2025-06-18'
        payload = {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list', 'params': {}}
        response = client.post('/mcp', headers=headers, json=payload)
        tools = response.json()['result']['tools']
        assert {tool['name'] for tool in tools} == CORE_TOOLS
        for tool in tools:
            assert tool['inputSchema']['required'] == ['request']
            assert 'user_id' not in str(tool['inputSchema'])
            assert tool['outputSchema']['type'] == 'object'
        allowed = client.post('/mcp', headers=dict(headers, Origin='https://client.example'), json=payload)
        assert allowed.status_code == 200
        assert allowed.headers['access-control-allow-origin'] == 'https://client.example'
        assert client.post('/mcp', headers=dict(headers, Origin='https://evil.example'), json=payload).status_code == 403
        assert client.post('/mcp', headers=dict(headers, Host='evil.example'), json=payload).status_code == 421
        check.assert_called()


@pytest.mark.parametrize('url', ['http://remote.example/mcp', 'https://user:secret@example/mcp',
    'https://example/mcp?token=secret', 'https://example/mcp#secret',
    'https://REPLACE_WITH_YOUR_PUBLIC_CountOn_HOST/mcp'])
def test_remote_smoke_rejects_insecure_urls(url):
    import argparse
    with pytest.raises(argparse.ArgumentTypeError):
        https_url(url)


@pytest.mark.asyncio
async def test_remote_read_only_without_cleanup_api(monkeypatch, capsys):
    from db.scripts import mcp_remote_smoke as module
    from types import SimpleNamespace
    calls = []
    async def discover(url, token):
        calls.append('discover')
    async def call(url, token, name, request):
        calls.append(name)
        return SimpleNamespace(is_error=False, structured_content={'expectations': []})
    monkeypatch.setattr(module, 'discover', discover)
    monkeypatch.setattr(module, 'call', call)
    await run('https://mcp.example/mcp', None, 'fixture-token')
    assert calls == ['discover', 'list_expectations']
    assert 'NOT RUN capture/get' in capsys.readouterr().out
