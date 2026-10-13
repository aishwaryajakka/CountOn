"""Server-authoritative Ring/Bee simulator ingestion and source approval."""

import pytest

pytestmark = pytest.mark.integration


def _expectation(client, source, metric):
    return client.post("/api/v1/expectations", json={"claim": "Demo expectation", "type": "boolean", "metric": metric, "evidence_sources": [source], "materiality_threshold": 0}).json()


def test_ring_simulator_match_replay_and_no_detection_unknown(client):
    expectation = _expectation(client, "ring_simulator", "package_detected")
    path = f"/api/v1/simulators/ring/expectations/{expectation['id']}/events"
    event = {"simulated": True, "event_id": "ring_sim_stable-0001", "kind": "package_detected", "device": "front_door", "timestamp": "2026-10-13T12:00:00Z", "confidence": 0.95, "metric": "package_detected"}
    first = client.post(path, json=event)
    replay = client.post(path, json=event)
    assert first.status_code == replay.status_code == 200
    assert first.json()["evidence"]["id"] == replay.json()["evidence"]["id"]
    assert first.json()["evaluation"]["id"] == replay.json()["evaluation"]["id"]
    assert first.json()["evaluation"]["result"] == "MATCH"
    missing = dict(event, event_id="ring_sim_stable-0002", kind="package_not_detected", timestamp="2026-10-13T13:00:00Z")
    assert client.post(path, json=missing).json()["evaluation"]["result"] == "UNKNOWN"


def test_bee_promise_is_context_and_requires_source_binding(client):
    expectation = _expectation(client, "bee_simulator", "appointment_confirmed")
    path = f"/api/v1/simulators/bee/expectations/{expectation['id']}/events"
    event = {"simulated": True, "id": "bee_sim_stable-0001", "type": "conversation", "speaker": "Landlord", "summary": "I promise the plumber will arrive Friday", "start_time": "2026-10-13T12:00:00Z", "confidence": 0.85, "metric": "appointment_confirmed", "confirmed": True}
    result = client.post(path, json=event)
    assert result.status_code == 200
    assert result.json()["evaluation"]["result"] == "UNKNOWN"
    assert result.json()["evidence"]["value"]["context_only"] is True
    unbound = _expectation(client, "manual", "appointment_confirmed")
    assert client.post(f"/api/v1/simulators/bee/expectations/{unbound['id']}/events", json=event).status_code == 422
