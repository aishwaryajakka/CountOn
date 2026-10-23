"""Official Bee CLI parsing and authenticated, consent-gated import regressions."""

from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.api.dependencies import get_current_user
from app.db.models import BeeExpectationBinding, BeeImportCandidate, Evidence
from app.integrations.bee import cli_bridge
from app.main import app
from tests import test_monitoring

monitoring_sessions = test_monitoring.monitoring_sessions

pytestmark = pytest.mark.integration


def test_cli_unavailable_and_documented_fixture_parsing(monkeypatch):
    monkeypatch.setattr(cli_bridge.shutil, "which", lambda _: None)
    assert cli_bridge.detect() == {
        "installed": False,
        "authenticated": False,
        "guidance": "npm install -g @beeai/cli",
    }
    rows, cursor = cli_bridge.normalize_changes(
        {
            "meta": {"until": 1_770_759_786_309, "next_cursor": "v1-1770759786309"},
            "facts": [{"id": 8, "text": "Prefers morning meetings", "confirmed": True}],
            "todos": [{"id": 9, "text": "Call the plumber", "completed": True}],
            "conversations": [{"id": 10, "short_summary": "Landlord promised a Friday visit", "state": "COMPLETED"}],
            "journals": [{"id": "j1", "text": "Remember to call"}],
        }
    )
    assert cursor == "v1-1770759786309"
    assert {row["category"] for row in rows} == {"fact", "todo", "conversation", "journal"}
    assert next(row for row in rows if row["category"] == "todo")["completed"] is True
    assert all("transcript" not in row and "audio" not in row for row in rows)


def _pair(client):
    pairing = client.post("/api/v1/integrations/bee-cli/pairings").json()
    response = client.post(
        "/api/v1/integrations/bee-cli/pair",
        json={
            "pairing_code": pairing["pairing_code"],
            "cli_version": "1.2.3",
            "bee_account_ref": "bee-user-fixture",
        },
    )
    assert response.status_code == 200
    return response.json()


def test_pairing_is_single_use_and_bridge_requires_credential(client):
    pairing = client.post("/api/v1/integrations/bee-cli/pairings").json()
    payload = {"pairing_code": pairing["pairing_code"], "cli_version": "1.2.3", "bee_account_ref": "bee-user-fixture"}
    assert client.post("/api/v1/integrations/bee-cli/pair", json=payload).status_code == 200
    bee_connection = client.get("/api/v1/integrations?provider=bee").json()[0]
    assert bee_connection["credential_state"] == "configured"
    assert client.post("/api/v1/integrations/bee-cli/pair", json=payload).status_code == 404
    assert client.post("/api/v1/integrations/bee-cli/bridge/candidates", json={"candidates": []}).status_code == 401
    assert client.post("/api/v1/integrations/bee-cli/bridge/candidates", headers={"Authorization": "Bearer invalid"}, json={"candidates": []}).status_code == 401


def test_consent_import_dedup_checkpoint_and_cross_user_isolation(client, db, users):
    paired = _pair(client)
    headers = {"Authorization": "Bearer " + paired["connector_token"]}
    batch = {
        "next_cursor": "v1-fixture-next",
        "candidates": [
            {
                "external_id": "todo:1001",
                "version": "fixture-v1",
                "category": "todo",
                "summary": "Plumber visit completed",
                "observed_at": "2026-10-13T12:00:00Z",
                "confidence": 0.8,
                "completed": True,
            },
            {
                "external_id": "conversation:1002",
                "version": "fixture-v1",
                "category": "conversation",
                "summary": "Landlord promised a Friday visit",
                "observed_at": "2026-10-13T11:00:00Z",
                "confidence": 0.7,
            },
        ],
    }
    staged = client.post("/api/v1/integrations/bee-cli/bridge/candidates", headers=headers, json=batch)
    assert staged.status_code == 200 and staged.json() == {"accepted": 2, "checkpoint": "v1-fixture-next"}
    assert client.post("/api/v1/integrations/bee-cli/bridge/candidates", headers=headers, json=batch).json()["accepted"] == 0
    candidates = client.get("/api/v1/integrations/bee-cli/candidates").json()
    expectation = client.post(
        "/api/v1/expectations",
        json={"claim": "The plumber will arrive", "type": "boolean", "metric": "appointment_completed", "evidence_sources": [], "materiality_threshold": 0},
    ).json()
    app.dependency_overrides[get_current_user] = lambda: users[1]
    assert client.get("/api/v1/integrations/bee-cli/candidates").json() == []
    denied = client.post("/api/v1/integrations/bee-cli/imports", json={"expectation_id": expectation["id"], "candidate_ids": [candidates[0]["id"]], "consent": True, "confirm_source_binding": True})
    assert denied.status_code == 404
    app.dependency_overrides[get_current_user] = lambda: users[0]
    result = client.post("/api/v1/integrations/bee-cli/imports", json={"expectation_id": expectation["id"], "candidate_ids": [row["id"] for row in candidates], "consent": True, "confirm_source_binding": True})
    assert result.status_code == 200 and result.json()["imported"] == 2
    evidence = client.get(f"/api/v1/expectations/{expectation['id']}/evidence").json()
    assert {row["raw_data"]["provenance"] for row in evidence} == {"LIVE_BEE_CLI"}
    promise = next(row for row in evidence if row["raw_data"]["category"] == "conversation")
    assert promise["metric"] == "bee_context" and "value" not in promise["value"]
    assert db.scalar(select(func.count()).select_from(BeeExpectationBinding).where(BeeExpectationBinding.user_id == users[0].id)) == 1
    assert db.scalar(select(func.count()).select_from(Evidence).where(Evidence.expectation_id == UUID(expectation["id"]))) == 2
    retained = list(
        db.scalars(
            select(BeeImportCandidate).where(
                BeeImportCandidate.user_id == users[0].id
            )
        )
    )
    assert retained and all(row.summary == "" and row.fact == {} for row in retained)
    replay = client.post("/api/v1/integrations/bee-cli/imports", json={"expectation_id": expectation["id"], "candidate_ids": [candidates[0]["id"]], "consent": True, "confirm_source_binding": True})
    assert replay.status_code == 404
    disconnected = client.post("/api/v1/integrations/bee-cli/disconnect", json={"revoke": True})
    assert disconnected.status_code == 200
    db.expire_all()
    assert (
        db.scalar(
            select(func.count())
            .select_from(BeeImportCandidate)
            .where(BeeImportCandidate.user_id == users[0].id)
        )
        == 0
    )
    assert client.post("/api/v1/integrations/bee-cli/bridge/candidates", headers=headers, json=batch).status_code == 401


def test_unsupported_bee_changed_schema_is_rejected():
    with pytest.raises(cli_bridge.BridgeError):
        cli_bridge.normalize_changes({"meta": {}, "facts": "not-a-list"})


@pytest.mark.parametrize('metric,result', [('appointment_completed', 'UNKNOWN'), ('todo_completed', 'MATCH')])
def test_completed_todo_cannot_prove_an_unrelated_appointment(client, metric, result):
    paired = _pair(client)
    staged = client.post('/api/v1/integrations/bee-cli/bridge/candidates',
        headers={'Authorization': 'Bearer ' + paired['connector_token']},
        json={'candidates': [{'external_id': 'todo:call-plumber', 'version': 'v1',
            'category': 'todo', 'summary': 'Call the plumber', 'completed': True,
            'observed_at': '2026-10-23T12:00:00Z', 'confidence': 0.8}]})
    assert staged.status_code == 200
    candidate = client.get('/api/v1/integrations/bee-cli/candidates').json()[0]
    expectation = client.post('/api/v1/expectations', json={
        'claim': 'The plumber appointment is complete' if metric == 'appointment_completed' else 'My selected todo is complete',
        'type': 'boolean', 'metric': metric, 'evidence_sources': ['bee'],
    }).json()
    response = client.post('/api/v1/integrations/bee-cli/imports', json={
        'expectation_id': expectation['id'], 'candidate_ids': [candidate['id']],
        'consent': True, 'confirm_source_binding': True,
    })
    assert response.status_code == 200
    latest = client.get(f"/api/v1/expectations/{expectation['id']}/evaluations/latest").json()
    assert latest['result'] == result
    evidence = client.get(f"/api/v1/expectations/{expectation['id']}/evidence").json()[0]
    if result == 'UNKNOWN':
        assert evidence['metric'] == 'bee_context'
        assert 'value' not in evidence['value']


@pytest.mark.parametrize('expired', ['credential', 'candidate'])
def test_staged_import_rechecks_grant_and_candidate_expiration(client, db, expired):
    from datetime import datetime, timedelta, timezone

    from app.db.models import BeeCliCredential

    paired = _pair(client)
    response = client.post('/api/v1/integrations/bee-cli/bridge/candidates',
        headers={'Authorization': 'Bearer ' + paired['connector_token']},
        json={'candidates': [{'external_id': 'fact:expired', 'version': 'v1',
            'category': 'fact', 'summary': 'A relevant fact',
            'observed_at': '2026-10-23T12:00:00Z', 'confidence': 0.7}]})
    assert response.status_code == 200
    candidate = client.get('/api/v1/integrations/bee-cli/candidates').json()[0]
    if expired == 'credential':
        row = db.scalar(select(BeeCliCredential).where(BeeCliCredential.connection_id == UUID(paired['connection_id'])))
        row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    else:
        db.get(BeeImportCandidate, UUID(candidate['id'])).created_at = datetime.now(timezone.utc) - timedelta(days=8)
    db.commit()
    expectation = client.post('/api/v1/expectations', json={
        'claim': 'Owned explicit expectation', 'type': 'boolean', 'metric': 'confirmed',
    }).json()
    result = client.post('/api/v1/integrations/bee-cli/imports', json={
        'expectation_id': expectation['id'], 'candidate_ids': [candidate['id']],
        'consent': True, 'confirm_source_binding': True,
    })
    assert result.status_code == 404
    if expired == 'credential':
        assert client.get('/api/v1/integrations/bee-cli/status').json()['state'] == 'disconnected'
    assert client.get(f"/api/v1/expectations/{expectation['id']}/evidence").json() == []


def test_bee_import_holds_revocation_lock_until_publication(monitoring_sessions, monkeypatch):
    from datetime import datetime, timezone
    from uuid import uuid4

    from sqlalchemy.exc import DBAPIError

    from app.db.models import BeeCliCredential
    from app.repositories.profile import ensure_profile
    from app.schemas.bee_connector import CandidateBatch, ImportRequest, PairRequest
    from app.schemas.expectation import ExpectationCreate
    from app.services import bee_connector_service as service
    from app.services.expectation_service import create_expectation

    with monitoring_sessions() as db:
        owner = uuid4()
        ensure_profile(db, owner)
        expectation = create_expectation(db, ExpectationCreate(
            claim='My selected todo will be completed', type='boolean', metric='todo_completed',
        ), owner)
        code, _ = service.create_pairing(db, owner)
        token, connection_id, _ = service.pair(db, PairRequest(
            pairing_code=code, cli_version='1.2.3', bee_account_ref='fixture-bee-account',
        ))
        service.stage(db, service.authenticate_connector(db, token), CandidateBatch(candidates=[{
            'external_id': 'todo:locked', 'version': 'v1', 'category': 'todo',
            'summary': 'Selected todo completed', 'completed': True,
            'observed_at': datetime.now(timezone.utc),
        }]))
        candidate = db.scalar(select(BeeImportCandidate).where(BeeImportCandidate.connection_id == connection_id))
        add = service.evidence_service.add_evidence
        locked = []

        def verify_lock(*args, **kwargs):
            # Disconnect takes this same credential lock before deleting staged data.
            # NOWAIT makes the regression deterministic, with no timing sleeps.
            with monitoring_sessions() as other:
                with pytest.raises(DBAPIError) as error:
                    other.scalar(select(BeeCliCredential).where(
                        BeeCliCredential.connection_id == connection_id,
                    ).with_for_update(nowait=True))
                assert error.value.orig.sqlstate == '55P03'
                locked.append(True)
            return add(*args, **kwargs)

        monkeypatch.setattr(service.evidence_service, 'add_evidence', verify_lock)
        result = service.import_candidates(db, owner, ImportRequest(
            expectation_id=expectation.id, candidate_ids=[candidate.id],
            consent=True, confirm_source_binding=True,
        ))
        assert result['imported'] == 1 and locked == [True]
