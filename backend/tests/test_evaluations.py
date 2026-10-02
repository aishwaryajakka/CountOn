"""PostgreSQL vertical flows, atomicity, and status semantics."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import OperationalError

from app.repositories import expectation as expectation_repository
from app.services import evaluation_service

pytestmark = pytest.mark.integration


def test_hero_mismatch(client, numeric_payload, bill_payload):
    expectation = client.post("/api/v1/expectations", json=numeric_payload).json()
    path = f"/api/v1/expectations/{expectation['id']}"
    for payload in [
        dict(bill_payload, source="utility_usage", metric="energy_usage_change", value={"percentage": -18}, unit="percent"),
        bill_payload,
        dict(bill_payload, source="tariff", metric="rate_change", value={"percentage": 22}, unit="percent"),
    ]:
        assert client.post(path + "/evidence", json=payload).status_code == 201
    response = client.post(path + "/evaluate")
    assert response.status_code == 200
    evaluation = response.json()
    assert evaluation["result"] == "MISMATCH"
    assert evaluation["expected"] == {"metric": "total_cost", "comparison": "less_than", "target": 142.10}
    assert evaluation["observed"]["value"] == 162
    assert evaluation["reasoning"]["reason"] == "observed_value_failed_comparison"
    assert "tariff" not in str(evaluation["reasoning"])
    assert client.get(path).json()["status"] == "contradicted"
    assert client.get(path + "/evaluations").json() == [evaluation]
    assert client.get(path + "/evaluations/latest").json() == evaluation


@pytest.mark.parametrize("amount,result,status,reason", [
    (130, "MATCH", "fulfilled", "comparison_satisfied"),
    (None, "UNKNOWN", "monitoring", "no_relevant_evidence"),
    ("162", "UNKNOWN", "monitoring", "malformed_numeric_evidence"),
])
def test_match_unknown_and_malformed(client, numeric_payload, bill_payload, amount, result, status, reason):
    created = client.post("/api/v1/expectations", json=numeric_payload).json()
    path = f"/api/v1/expectations/{created['id']}"
    if amount is None:
        payload = dict(bill_payload, metric="energy_usage_change", value={"percentage": -18})
    else:
        payload = dict(bill_payload, value={"amount": amount})
    assert client.post(path + "/evidence", json=payload).status_code == 201
    evaluated = client.post(path + "/evaluate")
    assert evaluated.status_code == 200
    assert evaluated.json()["result"] == result
    assert evaluated.json()["reasoning"]["reason"] == reason
    assert client.get(path).json()["status"] == status


@pytest.mark.parametrize("status", ["resolved", "cancelled"])
def test_terminal_status_preserved(client, numeric_payload, bill_payload, status):
    created = client.post("/api/v1/expectations", json=numeric_payload).json()
    path = f"/api/v1/expectations/{created['id']}"
    assert client.patch(path, json={"status": status}).status_code == 200
    assert client.post(path + "/evidence", json=bill_payload).status_code == 201
    assert client.post(path + "/evaluate").json()["result"] == "MISMATCH"
    assert client.get(path).json()["status"] == status
    assert len(client.get(path + "/evaluations").json()) == 1


def test_unknown_preserves_previously_fulfilled_status(client, numeric_payload, bill_payload):
    created = client.post("/api/v1/expectations", json=numeric_payload).json()
    path = f"/api/v1/expectations/{created['id']}"
    client.post(path + "/evidence", json=dict(bill_payload, value={"amount": 130}))
    assert client.post(path + "/evaluate").json()["result"] == "MATCH"
    client.post(path + "/evidence", json=dict(bill_payload, value={"amount": "bad"}, observed_at="2026-10-03T12:00:00Z"))
    assert client.post(path + "/evaluate").json()["result"] == "UNKNOWN"
    assert client.get(path).json()["status"] == "fulfilled"
    history = client.get(path + "/evaluations").json()
    assert {row["result"] for row in history} == {"UNKNOWN", "MATCH"}
    assert client.get(path + "/evaluations/latest").json() == history[0]


def test_evaluation_rolls_back_if_status_write_fails(client, db, numeric_payload, bill_payload, monkeypatch):
    created = client.post("/api/v1/expectations", json=numeric_payload).json()
    parent_id = UUID(created["id"])
    path = f"/api/v1/expectations/{parent_id}"
    client.post(path + "/evidence", json=bill_payload)
    def fail_status_update(*args, **kwargs):
        raise RuntimeError("Injected status update failure")
    monkeypatch.setattr(expectation_repository, "update_expectation", fail_status_update)
    with pytest.raises(RuntimeError, match="Injected status update failure"):
        evaluation_service.evaluate_expectation(db, parent_id)
    assert client.get(path + "/evaluations").json() == []
    assert client.get(path).json()["status"] == "monitoring"


def test_database_errors_do_not_leak_sql(client, monkeypatch):
    def fail_read(*args, **kwargs):
        raise OperationalError("SELECT sensitive_payload", {}, Exception("secret"))
    monkeypatch.setattr(expectation_repository, "get_expectation", fail_read)
    response = client.get(f"/api/v1/expectations/{uuid4()}")
    assert response.status_code == 500
    assert response.json() == {"detail": "Database operation failed"}


@pytest.mark.parametrize("suffix,method", [
    ("/evaluate", "post"), ("/evaluations", "get"), ("/evaluations/latest", "get"),
])
def test_evaluation_missing_parent(client, suffix, method):
    assert getattr(client, method)(f"/api/v1/expectations/{uuid4()}" + suffix).status_code == 404


def test_no_history_and_missing_latest(client, numeric_payload):
    created = client.post("/api/v1/expectations", json=numeric_payload).json()
    path = f"/api/v1/expectations/{created['id']}"
    assert client.get(path + "/evaluations").json() == []
    assert client.get(path + "/evaluations/latest").status_code == 404


@pytest.mark.parametrize("kind", ["temporal", "event"])
def test_safe_temporal_api(client, kind):
    created = client.post("/api/v1/expectations", json={"claim": "A future event", "type": kind}).json()
    path = f"/api/v1/expectations/{created['id']}"
    evaluation = client.post(path + "/evaluate").json()
    assert evaluation["result"] == "UNKNOWN"
    assert evaluation["reasoning"]["reason"] == "temporal_evaluation_not_implemented"
    assert client.get(path).json()["status"] == "monitoring"


@pytest.mark.parametrize("value,result", [(True, "MATCH"), (False, "MISMATCH"), ("true", "UNKNOWN")])
def test_boolean_api(client, bill_payload, value, result):
    created = client.post("/api/v1/expectations", json={"claim": "Package delivered", "type": "boolean", "metric": "delivered"}).json()
    path = f"/api/v1/expectations/{created['id']}"
    payload = dict(bill_payload, source="delivery", metric="delivered", value={"value": value})
    assert client.post(path + "/evidence", json=payload).status_code == 201
    assert client.post(path + "/evaluate").json()["result"] == result
