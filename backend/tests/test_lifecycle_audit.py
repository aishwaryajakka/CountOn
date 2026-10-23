"""Canonical audit lifecycle: trusted channels, linked records and no private text."""

import json
from uuid import UUID

import pytest
from sqlalchemy import select

from app.db.models import AuditEvent
from tests import test_agent, test_agent_api
from tests.test_clarification import decision, initial, patch

settings = test_agent.settings
real_adapter = test_agent.real_adapter
wire_engine = test_agent.wire_engine
wired = test_agent_api.wired


def rows(db):
    return list(db.scalars(select(AuditEvent).order_by(AuditEvent.created_at, AuditEvent.id)))


def test_manual_creation_is_web_and_untrusted_origin_is_rejected(client, db, numeric_payload):
    for field in ("compiler_metadata", "source_provider", "actor_type", "user_id"):
        response = client.post('/api/v1/expectations', json={
            **numeric_payload, field: {"creation_source": "alexa_skill"},
        })
        assert response.status_code == 422
    response = client.post('/api/v1/expectations', json=numeric_payload)
    identity = UUID(response.json()['id'])
    assert response.json()['compiler_metadata']['creation_source'] == 'web'
    event = next(row for row in rows(db) if row.expectation_id == identity)
    assert event.event_type == 'EXPECTATION_CREATED'
    assert event.actor_type == 'USER' and event.source_provider == 'WEB'
    assert event.audit_metadata == {'channel':'web', 'status':'SUCCESS'}
    assert event.created_at is not None


def test_rejected_capture_audits_only_safe_failure(client, db, numeric_payload):
    response = client.post('/api/v1/expectations', json={
        **numeric_payload, 'baseline':None, 'claim':'private-claim-never-audit',
    })
    assert response.status_code == 422
    event = next(row for row in rows(db) if row.event_type == 'EXPECTATION_CREATION_FAILED')
    assert event.event_type == 'EXPECTATION_CREATION_FAILED'
    assert event.expectation_id is None and event.source_provider == 'WEB'
    assert event.audit_metadata == {'channel':'web', 'status':'FAILED'}
    assert 'private-claim-never-audit' not in json.dumps(event.audit_metadata)


@pytest.mark.parametrize('outcome', ['capture', 'cancel', 'failure'])
def test_clarification_audits_pending_completed_cancelled_and_failure(wired, db, wire_engine, outcome):
    if outcome == 'failure':
        wire_engine('not JSON', 'not JSON')
    else:
        wire_engine(initial('MISSING_BASELINE', 'baseline'),
            decision(patch('baseline', 142.1, '$142.10')))
    turn = test_agent_api.converse(wired,
        "I'm counting on my electricity bill being lower than my last bill when my next bill arrives")
    handles = [turn['session_reference']]
    if outcome != 'failure':
        assert not turn['captured']
        if outcome == 'capture':
            turn = test_agent_api.converse(wired, 'My last bill was $142.10', turn['session_reference'])
            handles.append(turn['session_reference'])
            assert not turn['captured']
        turn = test_agent_api.converse(wired, 'Yes' if outcome == 'capture' else 'Never mind', turn['session_reference'])
    events = rows(db)
    lifecycle = [event for event in events if event.event_type == 'CLARIFICATION_UPDATED']
    assert {
        'capture':'completed', 'cancel':'cancelled', 'failure':'failed',
    }[outcome] in {event.audit_metadata['status'] for event in lifecycle}
    if outcome != 'failure':
        assert any(event.audit_metadata['status'] == 'pending' for event in lifecycle)
    assert all(event.audit_metadata['channel'] == 'alexa_web' for event in lifecycle)
    assert all(event.source_reference.startswith('sha256:') for event in lifecycle)
    if outcome == 'capture':
        assert len({event.source_reference for event in lifecycle}) == 1
    assert len(wired.get('/api/v1/expectations').json()) == (1 if outcome == 'capture' else 0)
    encoded = json.dumps([event.audit_metadata for event in events])
    assert all(not handle or handle not in encoded for handle in handles)
    assert 'My last bill was' not in encoded and 'not JSON' not in encoded
    assert 'capture_state' not in encoded and 'clarification_state' not in encoded


def test_evidence_linkage_status_transitions_and_private_metadata(client, db, numeric_payload, bill_payload):
    identity = client.post('/api/v1/expectations', json=numeric_payload).json()['id']
    evidence = client.post(f'/api/v1/expectations/{identity}/evidence', json={
        **bill_payload,
        'raw_data':{'provenance':'LIVE_BEE_CLI', 'Authorization':'Bearer private-jwt-sentinel',
            'aws_secret_access_key':'private-aws-sentinel', 'transcript':'private-voice-sentinel'},
    }).json()
    evaluation = client.post(f'/api/v1/expectations/{identity}/evaluate').json()
    notification = client.get('/api/v1/notifications').json()[0]
    for status in ('read', 'dismissed', 'read', 'read'):
        assert client.patch(f"/api/v1/notifications/{notification['id']}", json={'status':status}).status_code == 200
    events = rows(db)
    ingested = next(event for event in events if event.event_type == 'EVIDENCE_INGESTED')
    assert str(ingested.evidence_id) == evidence['id']
    assert ingested.source_provenance == 'USER_SUBMITTED' and ingested.actor_type == 'USER'
    for kind in ('EVALUATION_COMPLETED', 'MISMATCH_DETECTED', 'NOTIFICATION_CREATED', 'NOTIFICATION_ACKNOWLEDGED'):
        linked = [event for event in events if event.event_type == kind]
        assert linked
        assert all(str(event.expectation_id) == identity and str(event.evaluation_id) == evaluation['id'] for event in linked)
        assert all(str(event.evidence_id) == evidence['id'] for event in linked)
        if kind.startswith('NOTIFICATION'):
            assert all(event.audit_metadata['notification_id'] == notification['id'] for event in linked)
    acknowledged = [event for event in events if event.event_type == 'NOTIFICATION_ACKNOWLEDGED']
    assert {event.audit_metadata['status'] for event in acknowledged} == {'read', 'dismissed'}
    assert len(acknowledged) == 3
    encoded = json.dumps([{
        'metadata':event.audit_metadata, 'provider':event.source_provider,
        'provenance':event.source_provenance, 'reference':event.source_reference,
    } for event in events])
    assert all(secret not in encoded for secret in (
        'private-jwt-sentinel', 'private-aws-sentinel', 'private-voice-sentinel',
        'Authorization', 'LIVE_BEE_CLI',
    ))


def test_unknown_source_text_cannot_leak_into_audit_provider(client, db, numeric_payload, bill_payload):
    identity = client.post('/api/v1/expectations', json=numeric_payload).json()['id']
    client.post(f'/api/v1/expectations/{identity}/evidence', json={
        **bill_payload, 'source':'private-source-sentinel',
    })
    evidence = next(event for event in rows(db) if event.event_type == 'EVIDENCE_INGESTED')
    assert evidence.source_provider == 'DECLARED_SOURCE'
    assert 'private-source-sentinel' not in str(evidence.audit_metadata)
