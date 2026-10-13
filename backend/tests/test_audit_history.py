"""User-visible audit history is linked, redacted, idempotent, and owner scoped."""

from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.api.dependencies import get_current_user
from app.db.models import AuditEvent
from app.main import app

pytestmark = pytest.mark.integration


def _expectation(client, *, source="ring_simulator", metric="package_detected"):
    response = client.post(
        "/api/v1/expectations",
        json={
            "claim": "Audit contract demo",
            "type": "boolean",
            "metric": metric,
            "evidence_sources": [source],
            "materiality_threshold": 0,
        },
    )
    assert response.status_code == 201
    return response.json()


def test_ring_audit_links_real_evaluator_result_and_suppresses_replay(client, db):
    expectation = _expectation(client)
    identity = UUID(expectation["id"])
    path = f"/api/v1/simulators/ring/expectations/{identity}/events"
    event = {
        "simulated": True,
        "event_id": "ring_sim_audit-0001",
        "kind": "package_detected",
        "device": "front_door",
        "timestamp": "2026-10-13T12:00:00Z",
        "confidence": 0.95,
        "metric": "package_detected",
    }
    first = client.post(path, json=event)
    replay = client.post(path, json=event)
    assert first.status_code == replay.status_code == 200
    evidence_id = first.json()["evidence"]["id"]
    evaluation_id = first.json()["evaluation"]["id"]

    history = client.get(
        f"/api/v1/audit-events?expectation_id={identity}&source_provider=RING"
        "&result_status=MATCH"
    )
    assert history.status_code == 200
    rows = history.json()
    evaluation = next(row for row in rows if row["event_type"] == "EVALUATION_COMPLETED")
    assert evaluation["evidence_id"] == evidence_id
    assert evaluation["evaluation_id"] == evaluation_id
    assert evaluation["result_status"] == "MATCH"
    assert evaluation["source_provenance"] == "SIMULATED_RING"
    assert evaluation["action_metadata"]["evidence_ids"] == [evidence_id]
    assert evaluation["expectation"]["id"] == str(identity)
    assert evaluation["evidence"]["observed_at"] == event["timestamp"]

    persisted = db.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.expectation_id == identity,
            AuditEvent.event_type == "EVIDENCE_INGESTED",
        )
    )
    assert persisted == 1
    assert client.get(f"/api/v1/audit-events?expectation_id={identity}").json() == client.get(
        f"/api/v1/audit-events?expectation_id={identity}"
    ).json()


def test_bee_provenance_unknown_and_no_raw_provider_content(client):
    expectation = _expectation(
        client, source="bee_simulator", metric="appointment_confirmed"
    )
    identity = expectation["id"]
    response = client.post(
        f"/api/v1/simulators/bee/expectations/{identity}/events",
        json={
            "simulated": True,
            "id": "bee_sim_audit-0001",
            "type": "conversation",
            "speaker": "Landlord",
            "summary": "A plumber was promised for Friday",
            "start_time": "2026-10-13T12:00:00Z",
            "confidence": 0.85,
            "metric": "appointment_confirmed",
            "confirmed": True,
        },
    )
    assert response.status_code == 200
    assert response.json()["evaluation"]["result"] == "UNKNOWN"
    history = client.get(
        f"/api/v1/audit-events?expectation_id={identity}&source_provider=BEE"
        "&result_status=UNKNOWN"
    )
    assert history.status_code == 200
    row = next(
        item for item in history.json() if item["event_type"] == "EVALUATION_COMPLETED"
    )
    assert row["source_provenance"] == "SIMULATED_BEE"
    assert row["result_status"] == "UNKNOWN"
    assert "raw_data" not in history.text
    assert "access_token" not in history.text
    assert "refresh_token" not in history.text


def test_missing_evidence_is_unknown_and_history_is_private(client, users):
    expectation = _expectation(client, source="manual", metric="package_detected")
    identity = expectation["id"]
    evaluated = client.post(f"/api/v1/expectations/{identity}/evaluate")
    assert evaluated.status_code == 200
    assert evaluated.json()["result"] == "UNKNOWN"

    rows = client.get(
        f"/api/v1/audit-events?expectation_id={identity}&result_status=UNKNOWN"
    ).json()
    row = next(item for item in rows if item["event_type"] == "EVALUATION_COMPLETED")
    assert row["evidence_id"] is None
    assert row["result_status"] == "UNKNOWN"
    assert row["action_metadata"]["reason"] == "no_relevant_evidence"

    app.dependency_overrides[get_current_user] = lambda: users[1]
    assert client.get(f"/api/v1/audit-events?expectation_id={identity}").json() == []


def test_mismatch_notification_and_acknowledgement_are_linked(
    client, numeric_payload, bill_payload
):
    identity = client.post("/api/v1/expectations", json=numeric_payload).json()["id"]
    evidence = client.post(
        f"/api/v1/expectations/{identity}/evidence", json=bill_payload
    ).json()
    evaluation = client.post(f"/api/v1/expectations/{identity}/evaluate").json()
    notification = client.get("/api/v1/notifications").json()[0]
    client.patch(
        f"/api/v1/notifications/{notification['id']}", json={"status": "read"}
    )

    rows = client.get(
        f"/api/v1/audit-events?expectation_id={identity}&result_status=MISMATCH"
    ).json()
    by_type = {row["event_type"]: row for row in rows}
    assert {
        "EVALUATION_COMPLETED",
        "MISMATCH_DETECTED",
        "NOTIFICATION_CREATED",
    } <= by_type.keys()
    created = by_type["NOTIFICATION_CREATED"]
    assert created["evidence_id"] == evidence["id"]
    assert created["evaluation_id"] == evaluation["id"]
    acknowledged = next(
        row
        for row in client.get(
            f"/api/v1/audit-events?expectation_id={identity}"
        ).json()
        if row["event_type"] == "NOTIFICATION_ACKNOWLEDGED"
    )
    assert acknowledged["actor_type"] == "USER"
