"""Acceptance checks for CountOn's deterministic bill evidence outcomes."""

import pytest

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "amount,result,status,notification_count",
    [
        (180, "MISMATCH", "contradicted", 1),
        (125, "MATCH", "fulfilled", 0),
        (None, "UNKNOWN", "monitoring", 0),
    ],
)
def test_bill_pipeline_uses_real_evidence_and_notifies_only_mismatch(
    client, amount, result, status, notification_count
):
    expectation = client.post(
        "/api/v1/expectations",
        json={
            "claim": "My electricity bill will stay below $150",
            "type": "numeric_comparison",
            "metric": "total_cost",
            "comparison": "less_than",
            "baseline": 150,
            "evidence_sources": ["utility_bill"],
            "materiality_threshold": 0.05,
        },
    ).json()
    path = f"/api/v1/expectations/{expectation['id']}"
    if amount is not None:
        evidence = client.post(
            path + "/evidence",
            json={
                "source": "utility_bill",
                "metric": "total_cost",
                "value": {"amount": amount},
                "unit": "USD",
                "observed_at": "2026-10-13T12:00:00Z",
                "confidence": 1,
                "external_event_id": f"acceptance-bill-{amount}",
            },
        )
        assert evidence.status_code == 201

    evaluation = client.post(path + "/evaluate")
    assert evaluation.status_code == 200
    assert evaluation.json()["result"] == result
    assert client.get(path).json()["status"] == status
    assert len(client.get("/api/v1/notifications").json()) == notification_count

    history = client.get(
        f"/api/v1/audit-events?expectation_id={expectation['id']}"
        f"&result_status={result}"
    ).json()
    completed = next(
        row for row in history if row["event_type"] == "EVALUATION_COMPLETED"
    )
    assert completed["result_status"] == result
    assert completed["evaluation_id"] == evaluation.json()["id"]
    if amount is None:
        assert completed["evidence_id"] is None
    else:
        assert completed["evidence_id"] == evidence.json()["id"]
