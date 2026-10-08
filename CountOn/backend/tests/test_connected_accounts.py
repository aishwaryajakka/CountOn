"""Metadata-only connected accounts, notification policy and ownership."""
from uuid import UUID
import pytest
from sqlalchemy import select
from app.api.dependencies import get_current_user
from app.db.models import AuditEvent,Notification
from app.main import app

pytestmark=pytest.mark.integration


@pytest.mark.parametrize('provider,kind',[('google','email'),('google','calendar'),('microsoft','email'),('microsoft','calendar'),('ring','camera'),('bee','wearable'),('utility','utility'),('delivery','delivery')])
def test_supported_provider_models(client,provider,kind):
    response=client.post('/api/v1/integrations',json={'provider':provider,'connection_type':kind,'status':'connected','metadata':{'mock':True}})
    assert response.status_code==201
    assert response.json()['credential_state']=='not_configured'
    assert response.json()['metadata']['mock'] is True


def test_crud_multiple_accounts_filters_and_audit(client,db,users):
    payload={'provider':'google','connection_type':'calendar','display_name':'Personal Calendar','scopes':['calendar.read']}
    first=client.post('/api/v1/integrations',json=payload)
    assert first.status_code==201
    iid=first.json()['id'];path=f'/api/v1/integrations/{iid}'
    assert first.json()['user_id']==str(users[0].id)
    assert client.get(path).json()==first.json()
    assert client.post('/api/v1/integrations',json=dict(payload,display_name='Family Calendar')).status_code==201
    assert client.post('/api/v1/integrations',json={'provider':'microsoft','connection_type':'email'}).status_code==201
    assert len(client.get('/api/v1/integrations?provider=google&connection_type=calendar&status=pending').json())==2
    assert len(client.get('/api/v1/integrations?provider=google&limit=1&offset=1').json())==1
    assert client.patch(path,json={'status':'disconnected'}).json()['status']=='disconnected'
    assert client.delete(path).status_code==204
    assert client.get(path).status_code==404
    events=list(db.scalars(select(AuditEvent).where(AuditEvent.resource_id==UUID(iid))))
    assert {e.action for e in events}=={'integration.created','integration.updated','integration.deleted'}
    assert all(e.entity_type=='integration' and e.request_id for e in events)


def test_integration_and_notification_isolation(client,users,numeric_payload,bill_payload):
    connection=client.post('/api/v1/integrations',json={'provider':'google','connection_type':'email'}).json()
    eid=client.post('/api/v1/expectations',json=numeric_payload).json()['id']
    client.post(f'/api/v1/expectations/{eid}/evidence',json=bill_payload)
    client.post(f'/api/v1/expectations/{eid}/evaluate')
    notice=client.get('/api/v1/notifications').json()[0]
    app.dependency_overrides[get_current_user]=lambda:users[1]
    assert client.get('/api/v1/integrations').json()==[]
    path=f"/api/v1/integrations/{connection['id']}"
    assert client.get(path).status_code==404
    assert client.patch(path,json={'status':'error'}).status_code==404
    assert client.delete(path).status_code==404
    path=f"/api/v1/notifications/{notice['id']}"
    assert client.get(path).status_code==404
    assert client.patch(path,json={'status':'dismissed'}).status_code==404
    assert client.get('/api/v1/notifications').json()==[]


@pytest.mark.parametrize('changes',[{'provider':'invalid'},{'connection_type':'invalid'},{'provider':'ring','connection_type':'email'},
    {'status':'invalid'},{'user_id':'10000000-0000-4000-8000-000000000002'},
    {'metadata':{'access_token':'secret-placeholder'}},{'metadata':{'nested':{'refresh_token':'secret-placeholder'}}},
    {'access_token':'secret-placeholder'}])
def test_invalid_or_credential_fields_rejected(client,changes):
    response=client.post('/api/v1/integrations',json={'provider':'google','connection_type':'email'}|changes)
    assert response.status_code==422
    assert 'secret-placeholder' not in response.text


@pytest.mark.parametrize('amount,result,count',[(162,'MISMATCH',1),(130,'MATCH',0),(None,'UNKNOWN',0)])
def test_explicit_notification_policy(client,db,numeric_payload,bill_payload,amount,result,count):
    eid=client.post('/api/v1/expectations',json=numeric_payload).json()['id']
    path=f'/api/v1/expectations/{eid}'
    if amount is not None:client.post(path+'/evidence',json=dict(bill_payload,value={'amount':amount}))
    assert client.post(path+'/evaluate').json()['result']==result
    items=client.get('/api/v1/notifications').json()
    assert len(items)==count
    if count:
        item=items[0];nid=item['id']
        assert item['channel']=='in_app' and item['sent_at'] is None and item['message']
        assert client.get('/api/v1/notifications/'+nid).json()==item
        changed=client.patch('/api/v1/notifications/'+nid,json={'status':'dismissed'})
        assert changed.status_code==200 and changed.json()['status']=='dismissed'
        assert client.patch('/api/v1/notifications/'+nid,json={'status':'sent'}).status_code==422
        assert any(e.action=='notification.created' for e in db.scalars(select(AuditEvent).where(AuditEvent.expectation_id==UUID(eid))))


def test_external_event_replay_conflict_source_scope(client,numeric_payload,bill_payload):
    eid=client.post('/api/v1/expectations',json=numeric_payload).json()['id']
    path=f'/api/v1/expectations/{eid}/evidence'
    payload=dict(bill_payload,external_event_id='provider-event-42')
    first=client.post(path,json=payload)
    retry=client.post(path,json=payload)
    assert first.status_code==retry.status_code==201
    assert first.json()['id']==retry.json()['id']
    assert client.post(path,json=dict(payload,value={'amount':130})).status_code==409
    assert client.post(path,json=dict(payload,source='other_provider')).status_code==201
    assert len(client.get(path).json())==2
    other=client.post('/api/v1/expectations',json=numeric_payload).json()['id']
    assert client.post(f'/api/v1/expectations/{other}/evidence',json=payload).status_code==201


def test_notification_creation_idempotent_for_same_evaluation(client,db,numeric_payload,bill_payload):
    from app.db.models import Expectation,Evaluation
    from app.services.notification_service import for_evaluation
    eid=UUID(client.post('/api/v1/expectations',json=numeric_payload).json()['id'])
    client.post(f'/api/v1/expectations/{eid}/evidence',json=bill_payload)
    vid=UUID(client.post(f'/api/v1/expectations/{eid}/evaluate').json()['id'])
    expectation=db.get(Expectation,eid);evaluation=db.get(Evaluation,vid)
    assert for_evaluation(db,expectation,evaluation) is None
    assert for_evaluation(db,expectation,evaluation) is None
    db.commit()
    assert len(list(db.scalars(select(Notification).where(Notification.evaluation_id==vid))))==1
    assert len(list(db.scalars(select(AuditEvent).where(AuditEvent.expectation_id==eid,AuditEvent.action=='notification.created'))))==1
