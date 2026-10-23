"""PostgreSQL-backed dashboard API tests."""

import pytest

pytestmark = pytest.mark.integration


def test_dashboard_summary_counts_statuses(client, numeric_payload):
    created = client.post(
        "/api/v1/expectations", json=numeric_payload
    )
    assert created.status_code == 201

    response = client.get("/api/v1/dashboard/summary")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 1
    assert data["by_status"]["monitoring"] == 1
    assert sum(data["by_status"].values()) == data["total"]


def test_dashboard_summary_empty(client):
    response = client.get("/api/v1/dashboard/summary")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0
    assert all(count == 0 for count in data["by_status"].values())



def test_unresolved_mismatches_returns_pending_mismatches(
    client, numeric_payload, bill_payload
):
    created = client.post(
        "/api/v1/expectations", json=numeric_payload
    ).json()
    path = f"/api/v1/expectations/{created['id']}"

    # Create evidence that produces a real mismatch.
    for payload in [
        dict(
            bill_payload,
            source="utility_usage",
            metric="energy_usage_change",
            value={"percentage": -18},
            unit="percent",
        ),
        bill_payload,
        dict(
            bill_payload,
            source="tariff",
            metric="rate_change",
            value={"percentage": 22},
            unit="percent",
        ),
    ]:
        assert client.post(
            path + "/evidence", json=payload
        ).status_code == 201

    evaluation = client.post(path + "/evaluate")
    assert evaluation.status_code == 200
    assert evaluation.json()["result"] == "MISMATCH"

    response = client.get(
        "/api/v1/dashboard/unresolved-mismatches"
    )

    assert response.status_code == 200
    notifications = response.json()
    assert len(notifications) == 1
    assert notifications[0]["expectation_id"] == created["id"]
    assert notifications[0]["evaluation_id"] == evaluation.json()["id"]
    assert notifications[0]["status"] == "pending"
    assert notifications[0]["metadata"]["result"] == "MISMATCH"



def test_unresolved_mismatches_pagination_validation(client):
    assert client.get(
        "/api/v1/dashboard/unresolved-mismatches?limit=0"
    ).status_code == 422

    assert client.get(
        "/api/v1/dashboard/unresolved-mismatches?offset=-1"
    ).status_code == 422
