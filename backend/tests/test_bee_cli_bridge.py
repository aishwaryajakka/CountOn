"""Official Bee CLI parsing and authenticated, consent-gated import regressions."""

from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.api.dependencies import get_current_user
from app.db.models import BeeExpectationBinding, Evidence
from app.integrations.bee import cli_bridge
from app.main import app

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
    replay = client.post("/api/v1/integrations/bee-cli/imports", json={"expectation_id": expectation["id"], "candidate_ids": [candidates[0]["id"]], "consent": True, "confirm_source_binding": True})
    assert replay.status_code == 404
    disconnected = client.post("/api/v1/integrations/bee-cli/disconnect", json={"revoke": True})
    assert disconnected.status_code == 200
    assert client.post("/api/v1/integrations/bee-cli/bridge/candidates", headers=headers, json=batch).status_code == 401


def test_unsupported_bee_changed_schema_is_rejected():
    with pytest.raises(cli_bridge.BridgeError):
        cli_bridge.normalize_changes({"meta": {}, "facts": "not-a-list"})
