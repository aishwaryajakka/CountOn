"""Amazon normalization never issues sessions or CountOn grants."""
import json
import logging
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import amazon_auth
from app.main import app

TOKEN = 'Atza|fixture-only-not-a-real-token'
SUB = 'amzn1.account.fixture'
CLIENT = 'amzn1.application-oa2-client.fixture'
INFO = {'aud': CLIENT, 'iss': 'https://www.amazon.com', 'user_id': SUB, 'exp': 3600}

@pytest.fixture
def upstream(monkeypatch):
    monkeypatch.setattr(amazon_auth, 'get_settings', lambda: SimpleNamespace(amazon_auth_enabled=True, amazon_client_id=CLIENT))
    requests, payloads = [], [INFO, {'user_id': SUB, 'email': 'private@example.test', 'name': 'Private'}]
    class Reply:
        def __enter__(self): return self
        def __exit__(self, *args): return False
        def read(self, size):
            assert size == 8193
            data = payloads.pop(0)
            if isinstance(data, Exception): raise data
            return data if isinstance(data, bytes) else json.dumps(data).encode()
    class Opener:
        def open(self, request, timeout):
            assert timeout == 5
            requests.append(request)
            return Reply()
    monkeypatch.setattr(amazon_auth, 'build_opener', lambda handler: Opener())
    return payloads, requests

def request(token=TOKEN):
    with TestClient(app) as client:
        return client.get('/api/v1/auth/amazon/userinfo', headers={'Authorization': 'Bearer ' + token})

def test_valid_subject_only_and_no_sensitive_logging(upstream, caplog):
    caplog.set_level(logging.INFO)
    response = request()
    assert response.status_code == 200 and response.json() == {'sub': SUB}
    assert response.headers['cache-control'] == 'no-store'
    _, calls = upstream
    assert parse_qs(urlparse(calls[0].full_url).query)['access_token'] == [TOKEN]
    assert calls[1].full_url == 'https://api.amazon.com/user/profile'
    assert calls[1].get_header('Authorization') == 'Bearer ' + TOKEN
    assert TOKEN not in caplog.text and 'private@example.test' not in caplog.text
    assert 'Private' not in response.text

@pytest.mark.parametrize('change', [{'aud': 'other'}, {'iss': 'https://evil.invalid'}, {'exp': 0}, {'exp': -1}, {'exp': True}, {'exp': '3600'}, {'user_id': None}, {'user_id': ''}])
def test_invalid_claims_denied(upstream, change):
    upstream[0][0] = INFO | change
    assert request().status_code == 401 and len(upstream[1]) == 1

def test_profile_must_match_introspection(upstream):
    upstream[0][1] = {'user_id': 'other'}
    assert request().status_code == 401

@pytest.mark.parametrize('payload', [b'not-json', b'[]', b'x' * 8193])
def test_bad_or_oversized_response(upstream, payload):
    upstream[0][0] = payload
    assert request().status_code == 401

@pytest.mark.parametrize('error,status', [(TimeoutError('private'), 503), (URLError('private'), 503), (HTTPError('https://private', 401, 'private', {}, None), 401), (HTTPError('https://private', 302, 'private', {}, None), 503)])
def test_failures_safe_no_retry(upstream, error, status):
    upstream[0][0] = error
    result = request()
    assert result.status_code == status and 'private' not in result.text and len(upstream[1]) == 1

def test_no_redirect_forwarding():
    assert amazon_auth.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://evil.invalid') is None

def test_unconfigured_fails_closed(monkeypatch):
    monkeypatch.setattr(amazon_auth, 'get_settings', lambda: SimpleNamespace(amazon_auth_enabled=False, amazon_client_id=None))
    assert request().status_code == 503

@pytest.mark.parametrize('token', ['eyJfake.a.supabase-jwt', 'not-amazon', ''])
def test_counton_tokens_never_forwarded(upstream, token):
    assert request(token).status_code == 401 and not upstream[1]

def test_amazon_token_is_not_counton_auth(upstream):
    with TestClient(app) as client:
        result = client.get('/api/v1/expectations', headers={'Authorization': 'Bearer ' + TOKEN})
    assert result.status_code == 401 and not upstream[1]


def test_amazon_settings_default_off_and_parse_env(monkeypatch):
    from app.core.config import Settings
    monkeypatch.delenv('AMAZON_AUTH_ENABLED', raising=False)
    monkeypatch.delenv('AMAZON_CLIENT_ID', raising=False)
    defaults = Settings(_env_file=None, environment='test', database_target='local', local_database_url='postgresql+psycopg://fixture@localhost/fixture')
    assert defaults.amazon_auth_enabled is False and defaults.amazon_client_id is None
    monkeypatch.setenv('AMAZON_AUTH_ENABLED', 'true')
    monkeypatch.setenv('AMAZON_CLIENT_ID', CLIENT)
    configured = Settings(_env_file=None, environment='test', database_target='local', local_database_url='postgresql+psycopg://fixture@localhost/fixture')
    assert configured.amazon_auth_enabled is True and configured.amazon_client_id == CLIENT
