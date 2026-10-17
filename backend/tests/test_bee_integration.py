
"""Bee simulated-event ingestion tests."""

from uuid import uuid4

import pytest

from app.integrations.bee import normalize_bee_event

pytestmark = pytest.mark.integration


def bee_event():
    return {
        "event_id": "bee-test-001",
        "metric": "steps",
        "value": 5200,
        "unit": "steps",
        "observed_at": "2026-10-16T10:00:00Z",
        "confidence": 0.95,
    }


def test_normalize_bee_event():
    evidence = normalize_bee_event(bee_event())

    assert evidence.external_event_id == "bee-test-001"
    assert evidence.source == "bee"
    assert evidence.metric == "steps"
    assert evidence.value == {"amount": 5200}
    assert evidence.unit == "steps"
    assert evidence.confidence == 0.95


@pytest.mark.parametrize(
    "event",
    [
        {},
        {"event_id": "bee-1"},
        {
            "event_id": "bee-2",
            "metric": "steps",
            "value": 100,
            "observed_at": "2026-10-16T10:00:00",
        },
        {
            "event_id": "bee-3",
            "metric": "steps",
            "value": 100,
            "observed_at": "invalid-time",
        },
        {
            "event_id": "bee-4",
            "metric": "steps",
            "value": 100,
            "observed_at": "2026-10-16T10:00:00Z",
            "confidence": 2,
        },
    ],
)
def test_invalid_bee_events_are_rejected(event):
    with pytest.raises(ValueError):
        normalize_bee_event(event)


def test_bee_event_ingestion_api(client, numeric_payload):
    expectation = client.post(
        "/api/v1/expectations",
        json=numeric_payload,
    )
    assert expectation.status_code == 201, expectation.text
    expectation_id = expectation.json()["id"]

    response = client.post(
        f"/api/v1/integrations/{expectation_id}/events/bee",
        json=bee_event(),
    )

    assert response.status_code == 201, response.text
    evidence = response.json()
    assert evidence["expectation_id"] == expectation_id
    assert evidence["source"] == "bee"
    assert evidence["external_event_id"] == "bee-test-001"
    assert evidence["metric"] == "steps"
    assert evidence["value"] == {"amount": 5200}


def test_bee_event_replay_is_idempotent(client, numeric_payload):
    expectation = client.post(
        "/api/v1/expectations",
        json=numeric_payload,
    )
    assert expectation.status_code == 201, expectation.text
    expectation_id = expectation.json()["id"]
    path = f"/api/v1/integrations/{expectation_id}/events/bee"
    event = bee_event()

    first = client.post(path, json=event)
    second = client.post(path, json=event)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["id"] == second.json()["id"]


def test_bee_event_invalid_payload_returns_422(client, numeric_payload):
    expectation = client.post(
        "/api/v1/expectations",
        json=numeric_payload,
    )
    assert expectation.status_code == 201, expectation.text

    response = client.post(
        f"/api/v1/integrations/{expectation.json()['id']}/events/bee",
        json={"event_id": "bee-invalid"},
    )

    assert response.status_code == 422


def test_bee_event_missing_expectation_returns_404(client):
    response = client.post(
        f"/api/v1/integrations/{uuid4()}/events/bee",
        json=bee_event(),
    )

    assert response.status_code == 404



def test_bee_event_cannot_be_added_to_another_users_expectation(
    client, users, numeric_payload
):
    from app.api.dependencies import get_current_user
    from app.main import app

    expectation = client.post(
        "/api/v1/expectations",
        json=numeric_payload,
    )
    assert expectation.status_code == 201, expectation.text
    expectation_id = expectation.json()["id"]

    try:
        app.dependency_overrides[get_current_user] = lambda: users[1]

        response = client.post(
            f"/api/v1/integrations/{expectation_id}/events/bee",
            json=bee_event(),
        )

        assert response.status_code == 404, response.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)
