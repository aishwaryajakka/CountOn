"""Service persistence, identity, and REST interoperability through MCP."""
from contextlib import contextmanager
from decimal import Decimal
from unittest.mock import Mock
from uuid import UUID

import pytest
from mcp import Client
from sqlalchemy.exc import OperationalError
from starlette.testclient import TestClient

from app.core.auth import AuthenticatedUser
from app.core.exceptions import AuthenticationError
from app.mcp import auth
from app.mcp.server import create_server
from app.services import expectation_service


@pytest.fixture
def service_server(db, users):
    @contextmanager
    def factory():
        yield db  # Existing fixture owns savepoint rollback and session close.
    return lambda user=users[0]: create_server(session_factory=factory, user_resolver=lambda ctx: user)


@pytest.mark.asyncio
async def test_capture_persistence_and_rest_get(service_server, numeric_payload, db, users, client):
    async with Client(service_server(), raise_exceptions=True) as mcp:
        result = await mcp.call_tool('capture_expectation', {'request': numeric_payload})
        assert not result.is_error
        row = result.structured_content
        assert set(row) == {'id', 'claim', 'type', 'status', 'metric', 'created_at'}
        assert row['status'] == 'monitoring' and row['claim'] == numeric_payload['claim']
        persisted = expectation_service.get_expectation(db, UUID(row['id']), users[0].id)
        assert persisted.user_id == users[0].id and persisted.baseline == Decimal(str(numeric_payload['baseline']))
        response = client.get(f"/api/v1/expectations/{row['id']}")
        assert response.status_code == 200 and response.json()['id'] == row['id']


@pytest.mark.asyncio
async def test_rest_create_mcp_get_and_list(service_server, client, numeric_payload):
    response = client.post('/api/v1/expectations', json=numeric_payload)
    assert response.status_code == 201
    identity = response.json()['id']
    async with Client(service_server(), raise_exceptions=True) as mcp:
        result = await mcp.call_tool('get_expectation', {'request': {'expectation_id': identity}})
        assert not result.is_error and result.structured_content['id'] == identity
        result = await mcp.call_tool('list_expectations', {'request': {}})
        assert identity in {row['id'] for row in result.structured_content['expectations']}


@pytest.mark.asyncio
async def test_missing_and_cross_user_same_error(service_server, numeric_payload, users):
    async with Client(service_server(users[1]), raise_exceptions=True) as other:
        result = await other.call_tool('capture_expectation', {'request': numeric_payload})
        identity = result.structured_content['id']
    async with Client(service_server(), raise_exceptions=True) as mcp:
        hidden = await mcp.call_tool('get_expectation', {'request': {'expectation_id': identity}})
        missing = await mcp.call_tool('get_expectation', {'request': {'expectation_id': str(UUID(int=0))}})
        assert hidden.is_error and missing.is_error
        assert hidden.content[0].text == missing.content[0].text
        assert hidden.content[0].text.endswith('NOT_FOUND: Expectation not found.')


@pytest.mark.asyncio
async def test_list_empty_multiple_isolation_filters_pagination(service_server, numeric_payload, users):
    async with Client(service_server(), raise_exceptions=True) as mcp:
        result = await mcp.call_tool('list_expectations', {'request': {}})
        assert result.structured_content['expectations'] == []
        own = set()
        for claim in ('First bill', 'Second bill'):
            result = await mcp.call_tool('capture_expectation', {'request': dict(numeric_payload, claim=claim)})
            own.add(result.structured_content['id'])
    async with Client(service_server(users[1]), raise_exceptions=True) as mcp:
        result = await mcp.call_tool('capture_expectation', {'request': numeric_payload})
        other = result.structured_content['id']
    async with Client(service_server(), raise_exceptions=True) as mcp:
        result = await mcp.call_tool('list_expectations', {'request': {}})
        ids = {row['id'] for row in result.structured_content['expectations']}
        assert ids == own and other not in ids
        result = await mcp.call_tool('list_expectations', {'request': {'limit': 1, 'offset': 1,
            'status': 'monitoring', 'type': 'numeric_comparison'}})
        assert len(result.structured_content['expectations']) == 1
        assert result.structured_content['limit'] == 1 and result.structured_content['offset'] == 1
        result = await mcp.call_tool('list_expectations', {'request': {'status': 'fulfilled'}})
        assert result.structured_content['expectations'] == []


@pytest.mark.asyncio
@pytest.mark.parametrize('payload', [
    {'claim': '', 'type': 'numeric_comparison'},
    {'claim': 'Missing numeric fields', 'type': 'numeric_comparison'},
    {'claim': 'Invalid enum', 'type': 'secret-sentinel'}, 'secret-sentinel',
])
async def test_invalid_capture_does_not_persist(service_server, payload, db, users):
    async with Client(service_server(), raise_exceptions=True) as mcp:
        result = await mcp.call_tool('capture_expectation', {'request': payload})
        assert result.is_error and 'secret-sentinel' not in result.content[0].text
    assert expectation_service.list_expectations(db, users[0].id) == []


@pytest.mark.asyncio
@pytest.mark.parametrize('field', ['user_id', 'owner_id', 'profile_id'])
async def test_identity_arguments_rejected(field):
    request = {'claim': 'Bill', 'type': 'numeric_comparison', field: 'secret-sentinel'}
    async with Client(create_server(), raise_exceptions=True) as mcp:
        for arguments in ({'request': request}, {'request': {}, field: 'secret-sentinel'}):
            result = await mcp.call_tool('capture_expectation', arguments)
            assert result.is_error and 'secret-sentinel' not in result.content[0].text


@pytest.mark.asyncio
@pytest.mark.parametrize('failure,code', [
    (RuntimeError('secret-sentinel'), 'SERVICE_ERROR'), (AuthenticationError(), 'UNAUTHORIZED'),
])
async def test_auth_failure_prevents_session(failure, code):
    def resolver(ctx):
        raise failure
    factory = Mock()
    async with Client(create_server(session_factory=factory, user_resolver=resolver), raise_exceptions=True) as mcp:
        result = await mcp.call_tool('list_expectations', {'request': {}})
        assert result.is_error and code in result.content[0].text
        assert 'secret-sentinel' not in result.content[0].text
    factory.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure,code', [
    (OperationalError('secret SQL', {}, Exception('secret-sentinel password')), 'DATABASE_ERROR'),
    (RuntimeError('secret-sentinel stack'), 'SERVICE_ERROR'),
])
async def test_service_failures_sanitized_session_closed(failure, code, monkeypatch):
    closed = []
    @contextmanager
    def factory():
        try:
            yield Mock()
        finally:
            closed.append(True)
    monkeypatch.setattr(expectation_service, 'list_expectations', Mock(side_effect=failure))
    user = AuthenticatedUser(UUID(int=1))
    async with Client(create_server(session_factory=factory, user_resolver=lambda ctx: user), raise_exceptions=True) as mcp:
        result = await mcp.call_tool('list_expectations', {'request': {}})
        assert result.is_error and code in result.content[0].text
        assert 'secret' not in result.content[0].text
    assert closed == [True]


def test_http_bearer_identity_per_request(db, users, numeric_payload, monkeypatch):
    @contextmanager
    def factory():
        yield db
    verifier = Mock()
    verifier.verify.side_effect = lambda token: users[0] if token == 'first' else users[1]
    monkeypatch.setattr(auth, 'get_token_verifier', lambda: verifier)
    app = create_server(session_factory=factory).streamable_http_app(stateless_http=True, json_response=True)
    headers = {'Accept': 'application/json, text/event-stream', 'MCP-Protocol-Version': '2025-06-18'}
    with TestClient(app, base_url='http://127.0.0.1:8003') as client:
        def call(name, request, token):
            response = client.post('/mcp', headers=dict(headers, Authorization=f'Bearer {token}'), json={
                'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                'params': {'name': name, 'arguments': {'request': request}},
            })
            assert response.status_code == 200
            return response.json()['result']
        created = call('capture_expectation', numeric_payload, 'first')
        assert not created.get('isError')
        identity = created['structuredContent']['id']
        own = call('get_expectation', {'expectation_id': identity}, 'first')
        assert own['structuredContent']['id'] == identity
        other = call('get_expectation', {'expectation_id': identity}, 'second')
        assert other['isError'] and 'NOT_FOUND' in other['content'][0]['text']
        assert call('list_expectations', {}, 'second')['structuredContent']['expectations'] == []
        verifier.verify.side_effect = AuthenticationError()
        denied = call('list_expectations', {}, 'invalid')
        assert denied['isError'] and 'UNAUTHORIZED' in denied['content'][0]['text']
