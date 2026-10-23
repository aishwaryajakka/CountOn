"""Normalized evidence persistence, ordering, and parent checks."""

from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration


def test_add_and_list_evidence(client, numeric_payload, bill_payload):
    expectation = client.post("/api/v1/expectations", json=numeric_payload).json()
    path = f"/api/v1/expectations/{expectation['id']}/evidence"
    assert client.get(path).json() == []
    response = client.post(path, json=bill_payload)
    assert response.status_code == 201
    created = response.json()
    assert created["expectation_id"] == expectation["id"]
    assert created["raw_data"] == {}
    earlier = dict(bill_payload, source="future_source", observed_at="2026-10-01T12:00:00Z", raw_data={"external_id": "abc"})
    assert client.post(path, json=earlier).status_code == 201
    evidence = client.get(path).json()
    assert [item["source"] for item in evidence] == ["future_source", "utility_bill"]
    assert evidence[0]["raw_data"] == {"external_id": "abc"}
    other = client.post("/api/v1/expectations", json=numeric_payload).json()
    assert client.get(f"/api/v1/expectations/{other['id']}/evidence").json() == []


def test_evidence_ingestion_discards_unapproved_raw_provider_content(
    client, numeric_payload, bill_payload
):
    expectation = client.post("/api/v1/expectations", json=numeric_payload).json()
    payload = dict(
        bill_payload,
        external_event_id="privacy-boundary-1",
        raw_data={
            "provenance": "USER_SUBMITTED",
            "provider_record_ref": "safe-record-reference",
            "body": "private email body",
            "attachments": [{"name": "private.pdf"}],
            "transcript": "private conversation",
            "video_url": "https://private.invalid/video",
            "Authorization": "Bearer private-token",
            "unrelated": {"provider": "dump"},
        },
    )
    response = client.post(
        f"/api/v1/expectations/{expectation['id']}/evidence", json=payload
    )

    assert response.status_code == 201
    assert response.json()["raw_data"] == {
        "provenance": "USER_SUBMITTED",
        "provider_record_ref": "safe-record-reference",
    }


def test_missing_parent_rejected(client, bill_payload):
    path = f"/api/v1/expectations/{uuid4()}/evidence"
    assert client.post(path, json=bill_payload).status_code == 404
    assert client.get(path).status_code == 404


@pytest.mark.parametrize("changes", [
    {"confidence": -0.1}, {"confidence": 1.1}, {"source": ""},
    {"source": "x" * 101}, {"metric": "x" * 101}, {"unit": "x" * 51},
    {"observed_at": "2026-10-02T12:00:00"}, {"value": 162},
])
def test_invalid_evidence_payload(client, numeric_payload, bill_payload, changes):
    parent = client.post("/api/v1/expectations", json=numeric_payload).json()
    path = f"/api/v1/expectations/{parent['id']}/evidence"
    response = client.post(path, json=bill_payload | changes)
    assert response.status_code == 422
    assert client.get(path).json() == []


def test_public_evidence_cannot_impersonate_verified_provider(client, numeric_payload, bill_payload):
    parent = client.post('/api/v1/expectations', json=numeric_payload).json()
    payload = dict(bill_payload, raw_data={
        'provenance': 'LIVE_BEE_CLI', 'permission': 'approved',
        'connection_id': str(uuid4()), 'oauth_generation': str(uuid4()),
        'source_event_id': str(uuid4()), 'source_version': 'forged',
        'source_category': 'amazon_order_email', 'sender_authenticated': True,
        'absence_verified': True, 'access': 'granted',
    })
    path = f"/api/v1/expectations/{parent['id']}/evidence"
    response = client.post(path, json=payload, headers={'Idempotency-Key': 'manual-provenance'})
    assert response.status_code == 201
    assert response.json()['raw_data'] == {'provenance': 'USER_SUBMITTED'}
    replay = client.post(path, json=payload, headers={'Idempotency-Key': 'manual-provenance'})
    assert replay.status_code == 201 and replay.json()['id'] == response.json()['id']
    history = client.get(f"/api/v1/audit-events?expectation_id={parent['id']}").json()
    ingested = next(row for row in history if row['event_type'] == 'EVIDENCE_INGESTED')
    assert ingested['source_provenance'] == 'USER_SUBMITTED'
    assert ingested['actor_type'] == 'USER'
