"""PostgreSQL-backed expectation lifecycle and domain validation."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select

from app.db.models import Evidence, Evaluation, Expectation

pytestmark = pytest.mark.integration


def test_expectation_lifecycle(client, db, numeric_payload, bill_payload):
    response = client.post("/api/v1/expectations", json=numeric_payload)
    assert response.status_code == 201
    created = response.json()
    expectation_id = created["id"]
    path = f"/api/v1/expectations/{expectation_id}"
    assert created["status"] == "monitoring"
    assert created["user_id"] is None
    assert created["compiler_metadata"] == {}
    assert created["baseline"] == 142.10
    assert client.get(path).json() == created
    listing = client.get("/api/v1/expectations?status=monitoring&limit=1&offset=0")
    assert listing.status_code == 200
    assert listing.json() == [created]
    assert client.get("/api/v1/expectations?status=fulfilled").json() == []
    assert client.get("/api/v1/expectations?offset=1").json() == []
    response = client.patch(path, json={"claim": "Updated claim", "target_value": 140})
    assert response.status_code == 200
    updated = response.json()
    assert updated["claim"] == "Updated claim"
    assert updated["target_value"] == 140
    assert updated["baseline"] == 142.10
    assert client.post(path + "/evidence", json=bill_payload).status_code == 201
    assert client.post(path + "/evaluate").status_code == 200
    # Load relationships to exercise DB-driven deletion even for loaded children.
    model = db.get(Expectation, UUID(expectation_id))
    assert len(model.evidence) == 1
    assert len(model.evaluations) == 1
    response = client.delete(path)
    assert response.status_code == 204
    assert response.content == b""
    assert client.get(path).status_code == 404
    assert db.scalar(select(func.count()).select_from(Evidence)) == 0
    assert db.scalar(select(func.count()).select_from(Evaluation)) == 0


@pytest.mark.parametrize("field", ["metric", "comparison", "baseline"])
def test_invalid_numeric_create(client, numeric_payload, field):
    numeric_payload.pop(field)
    response = client.post("/api/v1/expectations", json=numeric_payload)
    assert response.status_code == 422
    assert response.json()["detail"]
    assert client.get("/api/v1/expectations").json() == []


@pytest.mark.parametrize("changes", [
    {"metric": None}, {"comparison": None}, {"baseline": None},
    {"claim": None}, {"evidence_sources": None},
    {"materiality_threshold": None}, {"status": None},
])
def test_invalid_patch_preserves_record(client, numeric_payload, changes):
    created = client.post("/api/v1/expectations", json=numeric_payload).json()
    path = f"/api/v1/expectations/{created['id']}"
    assert client.patch(path, json=changes).status_code == 422
    assert client.get(path).json() == created


def test_patch_can_clear_nullable_field_when_target_remains(client, numeric_payload):
    numeric_payload["target_value"] = 130
    created = client.post("/api/v1/expectations", json=numeric_payload).json()
    response = client.patch(f"/api/v1/expectations/{created['id']}", json={"baseline": None})
    assert response.status_code == 200
    assert response.json()["baseline"] is None
    assert response.json()["target_value"] == 130


@pytest.mark.parametrize("method", ["get", "patch", "delete"])
def test_missing_expectation(client, method):
    path = f"/api/v1/expectations/{uuid4()}"
    kwargs = {"json": {"claim": "updated"}} if method == "patch" else {}
    assert getattr(client, method)(path, **kwargs).status_code == 404


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "status=invalid"])
def test_invalid_listing_parameters(client, query):
    assert client.get("/api/v1/expectations?" + query).status_code == 422
