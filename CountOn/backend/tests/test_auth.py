"""Verify real signatures and claims; auth overrides exist only inside tests."""
from time import time
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from fastapi.testclient import TestClient

from app.core.auth import TokenVerifier
from app.core.config import Settings
from app.core.exceptions import AuthenticationError
from app.main import app


@pytest.fixture
def verifier(monkeypatch):
    settings = Settings(_env_file=None, database_target='local',
        local_database_url='postgresql+psycopg://fixture@localhost/fixture',
        supabase_url='https://auth.example.test', supabase_publishable_key='public-fixture')
    verifier = TokenVerifier(settings)
    key = ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setattr(verifier.jwks, 'get_signing_key_from_jwt', lambda _: SimpleNamespace(key=key.public_key()))
    return verifier, key


def token(verifier, key, **changes):
    claims = dict(iss=verifier.issuer, aud='authenticated', sub=str(uuid4()), role='authenticated',
                  iat=int(time())-1, exp=int(time())+300)
    claims.update(changes)
    return jwt.encode(claims, key, algorithm='ES256', headers={'kid':'test-key'}), claims


def test_valid_signature(verifier):
    verifier, key = verifier
    encoded, claims = token(verifier, key)
    assert str(verifier.verify(encoded).id) == claims['sub']


@pytest.fixture
def fixed_jwt_clock(monkeypatch):
    timestamp = 2_000_000_000
    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime.fromtimestamp(timestamp, timezone.utc)
    monkeypatch.setattr('jwt.api_jwt.datetime', FixedDatetime)
    return timestamp


@pytest.mark.parametrize('algorithm', ['ES256', 'HS256'])
def test_one_second_issuer_clock_skew(verifier, monkeypatch, fixed_jwt_clock, algorithm):
    verifier, key = verifier
    _, claims = token(verifier, key, iat=fixed_jwt_clock+1, nbf=fixed_jwt_clock+1, exp=fixed_jwt_clock+300)
    if algorithm == 'HS256':
        key = 'fixture-secret-at-least-32-characters'
        checked = []
        def check(*args, **kwargs):
            checked.append(True)
            return SimpleNamespace(status_code=200, json=lambda: {'id': claims['sub']})
        monkeypatch.setattr('app.core.auth.httpx.get', check)
    encoded = jwt.encode(claims, key, algorithm=algorithm, headers={'kid': 'test-key'})
    assert str(verifier.verify(encoded).id) == claims['sub']
    if algorithm == 'HS256':
        assert checked == [True]


@pytest.mark.parametrize('algorithm', ['ES256', 'HS256'])
@pytest.mark.parametrize('claim,offset', [('iat', 6), ('nbf', 6), ('exp', -6)])
def test_clock_skew_window_is_bounded(verifier, monkeypatch, fixed_jwt_clock, algorithm, claim, offset):
    verifier, key = verifier
    changes = dict(iat=fixed_jwt_clock-1, exp=fixed_jwt_clock+300)
    changes[claim] = fixed_jwt_clock+offset
    _, claims = token(verifier, key, **changes)
    if algorithm == 'HS256':
        key = 'fixture-secret-at-least-32-characters'
        def unexpected_auth_call(*args, **kwargs):
            pytest.fail('Invalid time claims must fail before contacting Auth')
        monkeypatch.setattr('app.core.auth.httpx.get', unexpected_auth_call)
    encoded = jwt.encode(claims, key, algorithm=algorithm, headers={'kid': 'test-key'})
    with pytest.raises(AuthenticationError):
        verifier.verify(encoded)


@pytest.mark.parametrize('changes', [
    {'exp':int(time())-60}, {'iss':'https://other.example/auth/v1'}, {'aud':'other'},
    {'sub':'not-a-uuid'}, {'role':'service_role'}, {'role':'anon'}, {'iat':int(time())+300},
    {'nbf':int(time())+300},
])
def test_invalid_claims(verifier, changes):
    verifier, key = verifier
    encoded, _ = token(verifier, key, **changes)
    with pytest.raises(AuthenticationError):
        verifier.verify(encoded)


def test_wrong_signature(verifier):
    verifier, _ = verifier
    encoded, _ = token(verifier, ec.generate_private_key(ec.SECP256R1()))
    with pytest.raises(AuthenticationError):
        verifier.verify(encoded)


@pytest.mark.parametrize('missing', ['exp','iat','iss','aud','sub','role'])
def test_required_claims(verifier, missing):
    verifier, key = verifier
    _, claims = token(verifier,key)
    del claims[missing]
    with pytest.raises(AuthenticationError):
        verifier.verify(jwt.encode(claims,key,algorithm='ES256',headers={'kid':'test-key'}))


def test_unsigned_and_no_kid_rejected(verifier):
    verifier, key = verifier
    _, claims = token(verifier,key)
    for encoded in [jwt.encode(claims, key=None, algorithm='none'), jwt.encode(claims,key,algorithm='ES256')]:
        with pytest.raises(AuthenticationError): verifier.verify(encoded)


@pytest.mark.parametrize('status,matching', [(401,True),(200,False),(200,True)])
def test_legacy_hs256_requires_auth_server(verifier, monkeypatch, status, matching):
    verifier, key = verifier
    _, claims = token(verifier,key)
    encoded=jwt.encode(claims,'fixture-secret-at-least-32-characters',algorithm='HS256')
    def check(url, headers, **kwargs):
        assert url == verifier.issuer+'/user'
        assert headers['Authorization']==f'Bearer {encoded}'
        assert headers['apikey']=='public-fixture'
        return SimpleNamespace(status_code=status,json=lambda:{'id':claims['sub'] if matching else str(uuid4())})
    monkeypatch.setattr('app.core.auth.httpx.get',check)
    if status==200 and matching:
        assert str(verifier.verify(encoded).id)==claims['sub']
    else:
        with pytest.raises(AuthenticationError): verifier.verify(encoded)


@pytest.mark.parametrize('headers', [{},{'Authorization':'Bearer invalid-token'},{'Authorization':'Basic invalid'}])
def test_unauthenticated_api_returns_401(headers):
    with TestClient(app) as client:
        response=client.get('/api/v1/expectations',headers=headers)
    assert response.status_code==401
    assert response.headers['www-authenticate']=='Bearer'
    assert response.json()['error'] == {'code':'UNAUTHORIZED','message':'Authentication required or token invalid','request_id':response.headers['x-request-id']}


@pytest.mark.parametrize('changes',[{'exp':int(time())-60},{'iss':'https://wrong.example/auth/v1'},{'aud':'wrong'}])
def test_invalid_signed_token_api_returns_401(verifier,monkeypatch,changes):
    verifier,key=verifier
    encoded,_=token(verifier,key,**changes)
    monkeypatch.setattr('app.api.dependencies.get_token_verifier',lambda:verifier)
    with TestClient(app) as client:
        response=client.get('/api/v1/expectations',headers={'Authorization':f'Bearer {encoded}'})
    assert response.status_code==401
    assert encoded not in response.text


def test_jwks_failure_fails_closed(verifier,monkeypatch):
    verifier,key=verifier
    encoded,_=token(verifier,key)
    def fail(_):
        raise jwt.PyJWKClientConnectionError('Sensitive network details')
    monkeypatch.setattr(verifier.jwks,'get_signing_key_from_jwt',fail)
    with pytest.raises(AuthenticationError,match='token invalid'):
        verifier.verify(encoded)
