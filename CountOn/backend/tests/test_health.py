"""Check the public health contract without requiring PostgreSQL."""

from fastapi.testclient import TestClient

from app.main import app


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "counton-api"}


def test_openapi_and_swagger_expose_the_vertical_flow() -> None:
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 200
        response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert {"get", "post"} <= paths["/api/v1/expectations"].keys()
    assert {"get", "patch", "delete"} <= paths["/api/v1/expectations/{expectation_id}"].keys()
    assert paths["/api/v1/expectations"]["post"]["responses"]["201"]
    assert paths["/api/v1/expectations/{expectation_id}/evidence"]["post"]["responses"]["201"]
    assert paths["/api/v1/expectations/{expectation_id}/evaluate"]["post"]["responses"]["200"]
    assert paths["/api/v1/expectations/{expectation_id}/evaluations"]["get"]["responses"]["200"]

    validation_schema = paths["/api/v1/expectations"]["post"]["responses"]["422"]["content"]["application/json"]["schema"]
    assert validation_schema["$ref"] == "#/components/schemas/ErrorEnvelope"
