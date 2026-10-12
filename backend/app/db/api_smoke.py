"""Verify live Supabase APIs and audit persistence using the configured engine."""

from uuid import UUID, uuid4

from _common import require_target, run_cli


def main() -> int:
    if not require_target("supabase"):
        return 1

    import httpx
    from sqlalchemy import func, select
    from app.db.models import Evaluation, Evidence, Expectation
    from app.db.session import SessionLocal, engine

    from _token import access_token
    from app.core.auth import get_token_verifier
    token = access_token()
    owner = get_token_verifier().verify(token).id
    ids: list[UUID] = []
    resources: set[UUID] = set()
    integration_ids: list[UUID] = []
    scenarios = (("MISMATCH", 162, "contradicted"), ("MATCH", 130, "fulfilled"), ("UNKNOWN", None, "monitoring"))

    def verify(condition: bool, step: str) -> None:
        if not condition:
            print(f"FAIL {step}")
            raise RuntimeError("API smoke verification failed")

    def verify_deleted(expectation_id: UUID) -> None:
        with SessionLocal() as db:
            verify(db.get(Expectation, expectation_id) is None, "expectation cleanup")
            for model in (Evidence, Evaluation):
                remaining = db.scalar(select(func.count()).select_from(model).where(model.expectation_id == expectation_id))
                verify(remaining == 0, "delete cascade")

    try:
        with httpx.Client(base_url="http://localhost:8000", timeout=30, headers={"Authorization": f"Bearer {token}"}) as client:
            response = client.get("/health")
            verify(response.status_code == 200 and response.json() == {"status": "ok", "service": "counton-api"}, "health")
            verify(client.get("/docs").status_code == 200, "Swagger")
            verify(client.get("/openapi.json").status_code == 200, "OpenAPI")
            try:
                account=client.post('/api/v1/integrations',json={'provider':'google','connection_type':'calendar','display_name':'API smoke calendar','metadata':{'mock':True}})
                verify(account.status_code==201,'integration create')
                integration_id=UUID(account.json()['id'])
                integration_ids.append(integration_id)
                ipath=f'/api/v1/integrations/{integration_id}'
                verify(client.get(ipath).status_code==200,'integration read')
                verify(client.get('/api/v1/integrations?provider=google&connection_type=calendar&status=pending').status_code==200,'integration filters')
                verify(client.patch(ipath,json={'status':'disconnected'}).status_code==200,'integration patch')
                for result, amount, status in scenarios:
                    response = client.post("/api/v1/expectations", json={
                        "claim": "My next electricity bill will be lower",
                        "type": "numeric_comparison", "metric": "total_cost",
                        "comparison": "less_than", "baseline": 142.1,
                        "evidence_sources": ["utility_bill"], "materiality_threshold": 0.05,
                    })
                    verify(response.status_code == 201, "create expectation")
                    expectation_id = UUID(response.json()["id"])
                    ids.append(expectation_id)
                    resources.add(expectation_id)
                    path = f"/api/v1/expectations/{expectation_id}"
                    response = client.get(path)
                    verify(response.status_code == 200 and response.json()["id"] == str(expectation_id), "read expectation")
                    response = client.get("/api/v1/expectations", params={"limit": 100})
                    verify(response.status_code == 200 and any(item["id"] == str(expectation_id) for item in response.json()), "list expectations")
                    payload = {
                        "source": "utility_bill" if amount is not None else "utility_usage",
                        "metric": "total_cost" if amount is not None else "energy_usage_change",
                        "value": {"amount": amount} if amount is not None else {"percentage": -18},
                        "unit": "USD" if amount is not None else "percent",
                        "observed_at": "2026-10-02T12:00:00Z", "confidence": 1.0, "raw_data": {},
                    }
                    response = client.post(path + "/evidence", json=payload)
                    verify(response.status_code == 201, "add evidence")
                    evidence_id = UUID(response.json()["id"])
                    resources.add(evidence_id)
                    response = client.get(path + "/evidence")
                    verify(response.status_code == 200 and any(item["id"] == str(evidence_id) for item in response.json()), "list evidence")
                    response = client.post(path + "/evaluate")
                    verify(response.status_code == 200 and response.json()["result"] == result, result)
                    evaluation_id = UUID(response.json()["id"])
                    resources.add(evaluation_id)
                    response = client.get(path + "/evaluations")
                    verify(response.status_code == 200 and any(item["id"] == str(evaluation_id) for item in response.json()), "evaluation history")
                    response = client.get(path + "/evaluations/latest")
                    verify(response.status_code == 200 and response.json()["id"] == str(evaluation_id), "latest evaluation")
                    notices=client.get('/api/v1/notifications').json()
                    linked=[row for row in notices if row['expectation_id']==str(expectation_id)]
                    verify(len(linked)==(1 if result=='MISMATCH' else 0),'notification policy')
                    for notice in linked:
                        nid=UUID(notice['id']);resources.add(nid)
                        npath=f'/api/v1/notifications/{nid}'
                        verify(client.get(npath).status_code==200,'notification read')
                        verify(client.patch(npath,json={'status':'dismissed'}).json().get('status')=='dismissed','notification dismiss')
                    response = client.get(path)
                    verify(response.status_code == 200 and response.json()["status"] == status, "expectation status")
                    response = client.patch(path, json={"materiality_threshold": 0.1})
                    verify(response.status_code == 200, "PATCH")
                    response = client.get(path)
                    verify(response.status_code == 200 and response.json()["materiality_threshold"] == 0.1, "PATCH readback")

                    # These queries run against settings.database_url, which was
                    # confirmed as Supabase before deployment, not the API's cache.
                    with SessionLocal() as db:
                        expectation = db.get(Expectation, expectation_id)
                        evidence = db.get(Evidence, evidence_id)
                        evaluation = db.get(Evaluation, evaluation_id)
                        verify(expectation is not None and expectation.user_id == owner and expectation.status.value == status
                               and expectation.materiality_threshold == 0.1, "actual Supabase expectation persistence")
                        verify(evidence is not None and evidence.expectation_id == expectation_id
                               and evidence.value == payload["value"], "actual Supabase evidence persistence")
                        verify(evaluation is not None and evaluation.expectation_id == expectation_id
                               and evaluation.result.value == result, "actual Supabase evaluation persistence")

                fake = f"/api/v1/expectations/{uuid4()}"
                verify(client.get(fake).status_code == 404, "404 read")
                verify(client.post(fake + "/evidence", json=payload).status_code == 404, "404 evidence")
                verify(client.post(fake + "/evaluate").status_code == 404, "404 evaluate")
            finally:
                # IDs were returned by this run's create calls only. Never bulk
                # delete team rows. Confirm cascades using fresh database reads.
                for expectation_id in ids:
                    response = client.delete(f"/api/v1/expectations/{expectation_id}")
                    verify(response.status_code == 204, "DELETE")
                    verify_deleted(expectation_id)
                for integration_id in integration_ids:
                    verify(client.delete(f'/api/v1/integrations/{integration_id}').status_code==204,'integration delete')
                    resources.add(integration_id)
                from _cleanup import remove_audits
                with SessionLocal() as db:
                    remove_audits(db, owner, resources)
            for label in ("health/Swagger/OpenAPI", "expectation CRUD", "evidence API", "evaluation API",
                          "integration CRUD/filters", "notification read/dismiss", "PATCH persistence", "MISMATCH", "MATCH", "UNKNOWN", "404 checks",
                          "actual Supabase persistence", "delete cascade", "smoke-test cleanup"):
                print(f"PASS {label}")
            print("SUPABASE API SMOKE PASSED")
            return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(run_cli(main))
