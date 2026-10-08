"""PostgreSQL invariants, bounded queries, idempotency and atomic effects."""
from uuid import UUID,uuid4
import pytest
from sqlalchemy import func,select
from sqlalchemy.exc import IntegrityError
from app.db.models import AuditEvent,Evidence,MonitoringJob,Notification
from app.repositories.operations import ensure_job

pytestmark=pytest.mark.integration


def test_acceptance_idempotency_and_atomic_effects(client,db,users,numeric_payload,bill_payload):
    created=client.post('/api/v1/expectations',json=numeric_payload).json()
    eid=UUID(created['id']);path=f'/api/v1/expectations/{eid}'
    headers={'Idempotency-Key':'same-observation'}
    first=client.post(path+'/evidence',json=bill_payload,headers=headers)
    second=client.post(path+'/evidence',json=bill_payload,headers=headers)
    assert first.status_code==second.status_code==201
    assert first.json()['id']==second.json()['id']
    conflict=client.post(path+'/evidence',json=dict(bill_payload,value={'amount':130}),headers=headers)
    assert conflict.status_code==409
    assert conflict.json()['error']['code']=='IDEMPOTENCY_CONFLICT'
    assert len(client.get(path+'/evidence').json())==1
    assert client.post(path+'/evaluate').json()['result']=='MISMATCH'
    notices=client.get('/api/v1/notifications?status=pending&limit=1').json()
    assert len(notices)==1 and notices[0]['expectation_id']==str(eid)
    events=list(db.scalars(select(AuditEvent).where(AuditEvent.expectation_id==eid)))
    assert {e.action for e in events}=={'expectation.created','evidence.ingested','expectation.evaluated','notification.created'}
    assert len(events)==4 and all(e.request_id for e in events)
    from app.db.models import Expectation
    expectation=db.get(Expectation,eid)
    ensure_job(db,expectation);ensure_job(db,expectation);db.commit()
    assert db.scalar(select(func.count()).select_from(MonitoringJob).where(MonitoringJob.expectation_id==eid))==1
    from app.api.dependencies import get_current_user
    from app.main import app
    app.dependency_overrides[get_current_user]=lambda:users[1]
    assert client.get('/api/v1/notifications').json()==[]
    app.dependency_overrides[get_current_user]=lambda:users[0]
    assert client.delete(path).status_code==204
    assert db.scalar(select(func.count()).select_from(MonitoringJob).where(MonitoringJob.expectation_id==eid))==0
    assert db.scalar(select(func.count()).select_from(Notification))==0
    db.expire_all()
    events=list(db.scalars(select(AuditEvent).where(AuditEvent.resource_id==eid)))
    assert any(e.action=='expectation.deleted' and e.expectation_id is None for e in events)


@pytest.mark.parametrize('changes',[{'status':'invalid'},{'attempt_count':-1},{'user_id':'other'},{'status':'pending'}])
def test_jobs_enforce_contract(client,db,users,numeric_payload,changes):
    eid=UUID(client.post('/api/v1/expectations',json=numeric_payload).json()['id'])
    values=dict(expectation_id=eid,user_id=users[0].id,status='completed')
    if changes.get('user_id')=='other':changes=dict(changes,user_id=users[1].id)
    values.update(changes)
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(MonitoringJob(**values));db.flush()


def test_pagination_and_filtering(client,numeric_payload,bill_payload):
    ids=[client.post('/api/v1/expectations',json=numeric_payload).json()['id'] for _ in range(3)]
    client.post('/api/v1/expectations',json={'claim':'Boolean filter','type':'boolean'})
    all_numeric=client.get('/api/v1/expectations?type=numeric_comparison').json()
    assert len(all_numeric)==3
    p1=client.get('/api/v1/expectations?type=numeric_comparison&limit=2').json()
    p2=client.get('/api/v1/expectations?type=numeric_comparison&limit=2&offset=2').json()
    assert p1+p2==all_numeric
    path='/api/v1/expectations/'+ids[0]
    for _ in range(3):
        client.post(path+'/evidence',json=bill_payload)
        client.post(path+'/evaluate')
    for suffix in ['/evidence','/evaluations']:
        assert len(client.get(path+suffix+'?limit=1&offset=1').json())==1
        assert client.get(path+suffix+'?limit=101').status_code==422
    assert len(client.get('/api/v1/notifications?limit=1&offset=1').json())==1
    for query in ['type=invalid','status=invalid']:
        assert client.get('/api/v1/expectations?'+query).status_code==422
    assert client.get('/api/v1/notifications?status=invalid').status_code==422


def test_evaluation_selects_metric_before_pagination(client,db,numeric_payload):
    from datetime import datetime,timezone
    eid=UUID(client.post('/api/v1/expectations',json=numeric_payload).json()['id'])
    db.add_all([Evidence(expectation_id=eid,source='usage',metric='unrelated',value={'amount':999},observed_at=datetime(2030,1,1,tzinfo=timezone.utc)) for _ in range(105)])
    db.add(Evidence(expectation_id=eid,source='bill',metric='total_cost',value={'amount':130},observed_at=datetime(2026,1,1,tzinfo=timezone.utc)))
    db.add(Evidence(expectation_id=eid,source='late_bill',metric='total_cost',value={'amount':162},observed_at=datetime(2025,1,1,tzinfo=timezone.utc)))
    db.commit()
    path=f'/api/v1/expectations/{eid}'
    assert len(client.get(path+'/evidence').json())==100
    assert client.post(path+'/evaluate').json()['result']=='MATCH'


def test_concurrent_evidence_retries_create_one_row(postgres_engine,bill_payload,numeric_payload):
    from concurrent.futures import ThreadPoolExecutor
    from sqlalchemy.orm import sessionmaker
    from app.db.models import Expectation,Profile
    from app.schemas.expectation import ExpectationCreate
    from app.schemas.evidence import EvidenceCreate
    from app.services import expectation_service,evidence_service
    factory=sessionmaker(bind=postgres_engine,expire_on_commit=False)
    owner=uuid4()
    try:
        with factory() as db:
            eid=expectation_service.create_expectation(db,ExpectationCreate(**numeric_payload),owner).id
        def ingest(_):
            with factory() as db:
                return evidence_service.add_evidence(db,eid,EvidenceCreate(**bill_payload),owner,'concurrent-key').id
        with ThreadPoolExecutor(max_workers=2) as executor:
            ids=list(executor.map(ingest,range(2)))
        assert ids[0]==ids[1]
        with factory() as db:
            assert db.scalar(select(func.count()).select_from(Evidence).where(Evidence.expectation_id==eid))==1
            assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.expectation_id==eid,AuditEvent.action=='evidence.ingested'))==1
    finally:
        with factory() as db:
            profile=db.get(Profile,owner)
            if profile:
                db.delete(profile);db.commit()


def test_audit_failure_rolls_back_evidence(client,db,numeric_payload,bill_payload,monkeypatch):
    from app.repositories import operations
    eid=UUID(client.post('/api/v1/expectations',json=numeric_payload).json()['id'])
    def fail(*args):raise RuntimeError('secret operational failure')
    monkeypatch.setattr(operations,'audit',fail)
    response=client.post(f'/api/v1/expectations/{eid}/evidence',json=bill_payload)
    assert response.status_code==500
    assert 'secret' not in response.text
    assert db.scalar(select(func.count()).select_from(Evidence).where(Evidence.expectation_id==eid))==0


def test_cleanup_preserves_other_records_for_same_owner(client,db,users,numeric_payload):
    from db.scripts._cleanup import cleanup_expectations
    from app.db.models import Expectation
    target=UUID(client.post('/api/v1/expectations',json=numeric_payload).json()['id'])
    other=UUID(client.post('/api/v1/expectations',json=numeric_payload).json()['id'])
    cleanup_expectations(db,users[0].id,[target])
    assert db.get(Expectation,other) is not None
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.resource_id==other))==1
    assert db.scalar(select(func.count()).select_from(MonitoringJob).where(MonitoringJob.expectation_id==other))==1
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.resource_id==target))==0
