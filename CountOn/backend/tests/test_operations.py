"""Operational behavior without network services or secret-bearing responses."""
from types import SimpleNamespace
from uuid import UUID,uuid4
import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError
from app.main import app
from app.api.dependencies import get_db
from app.core.config import Settings
from app.core.http_client import ExternalHTTPClient
from app.core.rate_limit import MemoryRateLimiter


def config(**changes):
    return Settings(_env_file=None,database_target='local',local_database_url='postgresql+psycopg://fixture@localhost/fixture',**changes)


@pytest.mark.parametrize('ready',[True,False])
def test_ready(ready,monkeypatch):
    monkeypatch.setattr('app.main.database_ready',lambda db:ready)
    with TestClient(app) as client:
        response=client.get('/ready')
    assert response.status_code==(200 if ready else 503)
    if not ready:
        assert response.json()['error']==dict(code='NOT_READY',message='Service dependencies are not ready',request_id=response.headers['x-request-id'])


def test_database_ready_failure():
    from app.services.readiness import database_ready
    class Broken:
        rolled_back=False
        def execute(self,*args): raise OperationalError('private SQL',{},Exception('private URL'))
        def rollback(self): self.rolled_back=True
    db=Broken()
    assert not database_ready(db)
    assert db.rolled_back


def test_unknown_errors_validation_and_cors_are_redacted(monkeypatch):
    def fail(_):raise RuntimeError('secret_password')
    monkeypatch.setattr('app.main.database_ready',fail)
    rid=str(uuid4())
    with TestClient(app) as client:
        response=client.get('/ready',headers={'X-Request-ID':rid,'Origin':'http://localhost:3000'})
        assert response.status_code==500
        assert response.headers['access-control-allow-origin']=='http://localhost:3000'
        assert response.json()['error']['request_id']==rid
        assert 'secret_password' not in response.text
        response=client.get('/nonexistent',headers={'X-Request-ID':'invalid'})
        assert response.status_code==404
        UUID(response.headers['x-request-id'])
        assert response.json()['error']['code']=='NOT_FOUND'
        preflight=client.options('/api/v1/expectations',headers={'Origin':'http://localhost:3000','Access-Control-Request-Method':'POST','Access-Control-Request-Headers':'Authorization,Idempotency-Key'})
        assert preflight.status_code==200
        rejected=client.options('/api/v1/expectations',headers={'Origin':'https://other.example','Access-Control-Request-Method':'POST'})
        assert rejected.status_code==400
        assert rejected.json()['error']['code']=='CORS_REJECTED'
        assert 'access-control-allow-origin' not in rejected.headers


def test_limiter_budgets_reset_and_capacity():
    now=[0]
    limiter=MemoryRateLimiter(config(rate_limit_requests=3,rate_limit_writes=1,rate_limit_max_keys=1),clock=lambda:now[0])
    assert limiter.check('a',True)==0
    assert limiter.check('a',True)==60
    assert limiter.check('a',False)==0
    assert limiter.check('a',False)==0
    assert limiter.check('a',False)==60
    assert limiter.check('b',False)==60
    now[0]=61
    assert limiter.check('b',True)==0


def test_rate_limit_response():
    with TestClient(app) as client:
        app.state.rate_limiter=MemoryRateLimiter(config(rate_limit_requests=1,rate_limit_writes=1))
        assert client.get('/api/v1/expectations').status_code==401
        response=client.get('/api/v1/expectations',headers={'Origin':'http://localhost:3000'})
        assert response.status_code==429
        assert response.headers['retry-after']=='60'
        assert response.headers['access-control-allow-origin']=='http://localhost:3000'
        assert response.json()['error']['code']=='RATE_LIMITED'
        assert client.get('/health').status_code==200


@pytest.mark.parametrize('method,status,count',[('GET',503,3),('POST',503,1),('GET',401,1),('GET',422,1),('GET',429,1)])
def test_http_retries_only_safe_transients(method,status,count):
    calls=[];delays=[]
    def respond(request):
        calls.append(request)
        return httpx.Response(status)
    with ExternalHTTPClient(config(),transport=httpx.MockTransport(respond),sleep=delays.append) as client:
        assert client.request(method,'https://external.example').status_code==status
        assert client.client.timeout.connect==3
        assert client.client.timeout.read==10
    assert len(calls)==count
    assert delays==([0.1,0.2] if count==3 else [])


@pytest.mark.parametrize('method,count',[('GET',3),('POST',1)])
def test_transport_timeouts_have_bounded_attempts(method,count):
    calls=[]
    def fail(request):
        calls.append(request)
        raise httpx.ConnectTimeout('sensitive transport error',request=request)
    with ExternalHTTPClient(config(),transport=httpx.MockTransport(fail),sleep=lambda _:None) as client:
        with pytest.raises(httpx.ConnectTimeout):client.request(method,'https://external.example')
    assert len(calls)==count


@pytest.mark.parametrize('changes',[{'environment':'unknown'},{'log_level':'verbose'},{'allowed_origins':['*']},
    {'rate_limit_writes':301},{'rate_limit_requests':0},{'http_read_timeout':0},
    {'supabase_url':'http://insecure.example'},{'environment':'production'}])
def test_invalid_configuration(changes):
    with pytest.raises(ValidationError):config(**changes)


def test_production_configuration():
    base=dict(_env_file=None,environment='production',database_target='supabase',
        supabase_database_url='postgresql+psycopg://fixture@cloud.example/postgres?sslmode=require',supabase_url='https://auth.example',supabase_publishable_key='public-fixture',allowed_origins=['https://counton.example'])
    assert Settings(**base).environment=='production'
    for changes in [{'supabase_database_url':'postgresql+psycopg://fixture@cloud.example/postgres'},{'rate_limit_enabled':False},{'allowed_origins':['http://localhost:3000']},{'supabase_publishable_key':None}, {'allowed_origins':[]}, {'supabase_jwks_url':'https://other.example/jwks'}]:
        with pytest.raises(ValidationError):Settings(**(base|changes))


def test_metrics_count_success_failure_and_latency(monkeypatch):
    from app.core import observability
    sink=observability.MemoryMetrics()
    monkeypatch.setattr(observability,'metrics',sink)
    monkeypatch.setattr('app.main.database_ready',lambda _:False)
    with TestClient(app) as client:
        client.get('/health');client.get('/ready')
    values=sink.snapshot()
    assert values[('requests','/health')]==1
    assert values[('server_errors','/ready')]==1
    assert values[('request_latency_seconds','/health')]>=0
    assert all('secret' not in str(label) for label in values)


def test_failed_metric_exporter_does_not_break_api(monkeypatch,caplog):
    from app.core import observability
    class BrokenMetrics:
        def increment(self,*args):raise RuntimeError('secret exporter credentials')
    monkeypatch.setattr(observability,'metrics',BrokenMetrics())
    with TestClient(app) as client:
        assert client.get('/health').status_code==200
    assert 'secret exporter credentials' not in caplog.text
    assert 'Metric sink unavailable' in caplog.text


def test_structured_logs_include_context_without_tokens():
    import json,logging
    from app.core.logging import StructuredFormatter
    from app.core.observability import request_id
    token=request_id.set('10000000-0000-4000-8000-000000000001')
    try:
        record=logging.LogRecord('counton.requests',logging.INFO,'',0,'HTTP request',(),None)
        record.method='GET';record.route='/api/v1/integrations/{id}';record.status_code=200
        record.authorization='Bearer secret-placeholder' # formatter only emits explicit safe fields
        payload=json.loads(StructuredFormatter().format(record))
        assert payload['request_id']==request_id.get()
        assert payload['route']=='/api/v1/integrations/{id}'
        assert 'secret-placeholder' not in str(payload)
    finally:request_id.reset(token)
