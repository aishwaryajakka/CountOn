"""Regression gates for complementary main interfaces on canonical services."""
from datetime import timedelta
from unittest.mock import Mock

import pytest
from pydantic import SecretStr, ValidationError

from app.api.dependencies import get_current_user
from app.api.v1 import oauth
from app.db.models import NotificationDelivery
from app.main import app
from app.notifications.delivery import SmtpChannel
from app.notifications.worker import DeliveryWorker
from tests import test_automatic_tracking, test_monitoring

monitoring_sessions = test_monitoring.monitoring_sessions
scenario = test_monitoring.scenario


@pytest.mark.parametrize('path', ['/oauth/google/start', '/oauth/google/gmail/start',
    '/oauth/microsoft/outlook/start', '/oauth/microsoft/calendar/start'])
def test_legacy_oauth_start_requires_counton_bearer(client, path):
    app.dependency_overrides.pop(get_current_user, None)
    assert client.get('/api/v1' + path).status_code == 401


@pytest.mark.parametrize('provider,kind,path', [('google','calendar','google/start'),
    ('google','email','google/gmail/start'), ('microsoft','email','microsoft/outlook/start'),
    ('microsoft','calendar','microsoft/calendar/start')])
def test_legacy_oauth_start_uses_current_owned_grant_authority(client, users, monkeypatch, provider, kind, path):
    connection = client.post('/api/v1/integrations', json={'provider':provider,'connection_type':kind}).json()
    begin = Mock(return_value='https://provider.example/authorize')
    authority = Mock(return_value=Mock(begin=begin))
    monkeypatch.setattr(oauth, 'account_oauth', authority)
    response = client.get(f"/api/v1/oauth/{path}?connection_id={connection['id']}")
    assert response.status_code == 200 and response.json()['authorization_url'].startswith('https:')
    assert begin.call_count == 1 and begin.call_args.args[-1] == users[0].id
    app.dependency_overrides[get_current_user] = lambda: users[1]
    assert client.get(f"/api/v1/oauth/{path}?connection_id={connection['id']}").status_code == 404
    assert begin.call_count == 1


@pytest.mark.parametrize('path', ['/oauth/google/callback', '/oauth/google/gmail/callback'])
def test_old_callback_urls_still_reject_missing_or_replayed_state(client, path):
    assert client.get('/api/v1' + path, params={'code':'untrusted','state':'untrusted'}).status_code == 400


@pytest.mark.parametrize('kind', ['ring', 'bee', 'email'])
def test_manual_compatibility_does_not_bypass_source_approval(client, numeric_payload, kind):
    expectation = client.post('/api/v1/expectations', json=numeric_payload).json()
    event = {'event_id':'manual-1','event_type':'motion','metric':'total_cost','value':130,
        'message_id':'manual-mail-1','category':'billing','amount':130,
        'observed_at':'2026-10-23T12:00:00Z'}
    response = client.post(f"/api/v1/integrations/{expectation['id']}/events/{kind}", json=event)
    assert response.status_code == 422
    assert client.get(f"/api/v1/expectations/{expectation['id']}/evidence").json() == []


def test_route_registrations_are_unique():
    seen = set()
    for route in app.routes:
        for method in getattr(route, 'methods', set()):
            key = method, route.path
            assert key not in seen, key
            seen.add(key)


def test_smtp_requires_explicit_tls_and_configuration():
    values = {'notification_email_provider':'smtp', 'notification_email_enabled':True,
        'smtp_host':'smtp.example.test','smtp_username':'sender','smtp_password':'fixture-only',
        'smtp_from_email':'sender@example.test','frontend_public_url':'https://counton.test'}
    config = test_automatic_tracking.provider.settings(**values)
    assert config.notification_email_from == 'sender@example.test'
    with pytest.raises(ValidationError):
        test_automatic_tracking.provider.settings(**values, smtp_use_tls=False)


def test_smtp_outbox_recovery_never_replays_an_uncertain_send(scenario):
    sessions, _, _, now, config = test_automatic_tracking.outbox(scenario)
    config = config.model_copy(update={'notification_email_provider':'smtp',
        'smtp_host':'smtp.example.test','smtp_username':'sender','smtp_password':SecretStr('fixture-only')})
    channel = Mock()
    worker = DeliveryWorker(sessions, config, channel=channel, now=lambda:now)
    claim = worker.claim()
    channel.send(claim[2], claim[0])  # SMTP accepted; process dies before SQL acknowledgement.
    restarted = DeliveryWorker(sessions, config, channel=channel, now=lambda:now+timedelta(seconds=61))
    assert restarted.once() and not restarted.once()
    assert channel.send.call_count == 1
    with sessions() as db:
        delivery = db.get(NotificationDelivery, claim[0])
        assert delivery.status == 'failed' and delivery.last_error == 'DELIVERY_UNCERTAIN'


def test_smtp_transport_errors_are_sanitized_and_not_automatically_retried(monkeypatch):
    from app.integrations.provider import ProviderError
    config = test_monitoring.settings()
    send = Mock(side_effect=RuntimeError('private recipient and credentials'))
    monkeypatch.setattr('app.services.email_delivery.send_smtp', send)
    with pytest.raises(ProviderError) as error:
        SmtpChannel(config).send({}, 'stable-id')
    assert not error.value.retryable and 'private' not in str(error.value)


@pytest.mark.parametrize("kind,path", [("email", "outlook/sync"), ("calendar", "microsoft-calendar/sync")])
def test_legacy_sync_queues_only_owned_selected_stream(client, db, users, monkeypatch, kind, path):
    from uuid import UUID

    from app.api.v1 import manual_events
    from app.db.models import ProviderSyncState
    connection = client.post('/api/v1/integrations', json={
        'provider': 'microsoft', 'connection_type': kind,
    }).json()
    state = ProviderSyncState(connection_id=UUID(connection['id']), user_id=users[0].id, stream='selected')
    db.add(state)
    db.commit()
    queue = Mock()
    monkeypatch.setattr(manual_events.provider_sync_service, 'queue', queue)
    monkeypatch.setattr(manual_events, 'projected_items', Mock(return_value=[]))
    response = client.post(f"/api/v1/integrations/{connection['id']}/{path}")
    assert response.status_code == 200 and response.json()['queued'] is True
    assert response.json()['sync_id'] == str(state.id)
    assert queue.call_args.args[1:] == (state.id, users[0].id)
    if kind == 'email':
        assert response.json()['messages_processed'] == response.json()['evidence_created'] == 0
    app.dependency_overrides[get_current_user] = lambda: users[1]
    assert client.post(f"/api/v1/integrations/{connection['id']}/{path}").status_code == 404
    assert queue.call_count == 1


def test_legacy_gmail_read_uses_owned_minimal_projections(client, db, users, monkeypatch):
    from uuid import UUID

    from app.api.v1 import manual_events
    from app.db.models import ProviderSyncState
    connection = client.post('/api/v1/integrations', json={'provider':'google','connection_type':'email'}).json()
    state = ProviderSyncState(connection_id=UUID(connection['id']), user_id=users[0].id, stream='inbox')
    db.add(state)
    db.commit()
    projection = Mock(return_value=[{'id':'safe-reference', 'facts':{'status':'shipped'}}])
    monkeypatch.setattr(manual_events, 'projected_items', projection)
    response = client.get('/api/v1/integrations/google/gmail/messages?max_results=1')
    assert response.status_code == 200
    assert response.json()['messages'] == projection.return_value
    assert projection.call_args.args[1:] == (users[0].id, state, 1)
    app.dependency_overrides[get_current_user] = lambda: users[1]
    assert client.get('/api/v1/integrations/google/gmail/messages').status_code == 409
    assert projection.call_count == 1
