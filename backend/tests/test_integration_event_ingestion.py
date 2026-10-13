
import pytest


from app.integrations.ring import normalize_ring_event
from app.integrations.bee import normalize_bee_event


def test_normalize_ring_event():
    event = {
        "event_id": "ring-1",
        "event_type": "motion",
        "observed_at": "2026-10-13T10:00:00Z",
    }

    evidence = normalize_ring_event(event)

    assert evidence.external_event_id == "ring-1"
    assert evidence.source == "ring"
    assert evidence.metric == "camera_event"
    assert evidence.value == {"event_type": "motion"}
    assert evidence.confidence == 1.0


def test_normalize_bee_event():
    event = {
        "event_id": "bee-1",
        "metric": "steps",
        "value": 5200,
        "unit": "steps",
        "observed_at": "2026-10-13T10:00:00Z",
    }

    evidence = normalize_bee_event(event)

    assert evidence.external_event_id == "bee-1"
    assert evidence.source == "bee"
    assert evidence.metric == "steps"
    assert evidence.value == {"amount": 5200}
    assert evidence.unit == "steps"


@pytest.mark.parametrize(
    "event",
    [
        {},
        {"event_id": "ring-1"},
        {
            "event_id": "ring-1",
            "event_type": "motion",
            "observed_at": "not-a-date",
        },
        {
            "event_id": "ring-1",
            "event_type": "motion",
            "observed_at": "2026-10-13T10:00:00",
        },
    ],
)
def test_invalid_ring_events_are_rejected(event):
    with pytest.raises(ValueError):
        normalize_ring_event(event)


@pytest.mark.parametrize(
    "event",
    [
        {},
        {
            "event_id": "bee-1",
            "metric": "steps",
            "value": 5200,
        },
        {
            "event_id": "bee-1",
            "metric": "steps",
            "value": 5200,
            "observed_at": "not-a-date",
        },
        {
            "event_id": "bee-1",
            "metric": "steps",
            "value": "many",
            "observed_at": "2026-10-13T10:00:00Z",
        },
    ],
)
def test_invalid_bee_events_are_rejected(event):
    with pytest.raises(ValueError):
        normalize_bee_event(event)

pytestmark = pytest.mark.integration


def test_ring_event_ingestion_api(client, numeric_payload):
    expectation = client.post(
        "/api/v1/expectations",
        json=numeric_payload,
    )
    assert expectation.status_code == 201
    expectation_id = expectation.json()["id"]

    response = client.post(
        f"/api/v1/integrations/{expectation_id}/events/ring",
        json={
            "event_id": "ring-api-1",
            "event_type": "motion",
            "observed_at": "2026-10-13T10:00:00Z",
        },
    )

    assert response.status_code == 201, response.text
    evidence = response.json()
    assert evidence["source"] == "ring"
    assert evidence["external_event_id"] == "ring-api-1"
    assert evidence["metric"] == "camera_event"


def test_bee_event_ingestion_api(client, numeric_payload):
    expectation = client.post(
        "/api/v1/expectations",
        json=numeric_payload,
    )
    assert expectation.status_code == 201
    expectation_id = expectation.json()["id"]

    response = client.post(
        f"/api/v1/integrations/{expectation_id}/events/bee",
        json={
            "event_id": "bee-api-1",
            "metric": "total_cost",
            "value": 130,
            "unit": "USD",
            "observed_at": "2026-10-13T10:00:00Z",
        },
    )

    assert response.status_code == 201, response.text
    evidence = response.json()
    assert evidence["source"] == "bee"
    assert evidence["external_event_id"] == "bee-api-1"
    assert evidence["value"] == {"amount": 130}


def test_ring_event_replay_is_idempotent(client, numeric_payload):
    expectation = client.post(
        "/api/v1/expectations",
        json=numeric_payload,
    )
    assert expectation.status_code == 201
    expectation_id = expectation.json()["id"]

    path = f"/api/v1/integrations/{expectation_id}/events/ring"
    event = {
        "event_id": "ring-replay-1",
        "event_type": "motion",
        "observed_at": "2026-10-13T10:00:00Z",
    }

    first = client.post(path, json=event)
    second = client.post(path, json=event)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]


def test_bee_event_rejects_invalid_payload(client, numeric_payload):
    expectation = client.post(
        "/api/v1/expectations",
        json=numeric_payload,
    )
    assert expectation.status_code == 201
    expectation_id = expectation.json()["id"]

    response = client.post(
        f"/api/v1/integrations/{expectation_id}/events/bee",
        json={"event_id": "bee-invalid"},
    )

    assert response.status_code == 422

def test_bee_event_replay_is_idempotent(client, numeric_payload):
    expectation = client.post(
        "/api/v1/expectations",
        json=numeric_payload,
    )
    assert expectation.status_code == 201
    expectation_id = expectation.json()["id"]

    path = f"/api/v1/integrations/{expectation_id}/events/bee"
    event = {
        "event_id": "bee-replay-1",
        "metric": "steps",
        "value": 5200,
        "unit": "steps",
        "observed_at": "2026-10-13T10:00:00Z",
    }

    first = client.post(path, json=event)
    second = client.post(path, json=event)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]