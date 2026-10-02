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
