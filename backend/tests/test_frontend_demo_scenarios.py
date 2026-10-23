"""The three web demo recipes use real APIs, PostgreSQL and deterministic results.

Cloud inference is disabled explicitly; the existing grounded Why fallback is
exercised through the shared orchestrator/MCP path, never a fabricated UI result.
"""

from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from sqlalchemy import select

from app.ai.mismatch_investigator import BedrockMismatchInvestigator
from app.api.dependencies import get_current_user
from app.db.models import AuditEvent, Evaluation, Evidence, Expectation, Notification
from app.main import app
from app.mcp import intelligence
from tests import test_agent, test_agent_api, test_alexa

settings = test_agent.settings
real_adapter = test_agent.real_adapter
wired = test_agent_api.wired
wired_alexa = test_alexa.wired_alexa
signing = test_alexa.signing
wire_engine = test_agent.wire_engine
pytestmark = pytest.mark.integration


def create(client, kind):
    friday = datetime.now(timezone.utc)
    friday += timedelta(days=(4 - friday.weekday()) % 7)
    friday = friday.replace(hour=23, minute=59, second=59)
    payload = {
        "claim": "My next electricity bill should be below $150.",
        "type": "numeric_comparison", "metric": "total_cost",
        "comparison": "less_than", "target_value": 150,
        "evidence_sources": ["utility_bill"], "materiality_threshold": 0,
    } if kind == "electricity" else {
        "claim": "My package should arrive by Friday." if kind == "package" else "My landlord said the plumber will arrive Friday.",
        "type": "boolean", "metric": "delivered" if kind == "package" else "appointment_confirmed",
        "deadline": friday.isoformat(),
        "evidence_sources": ["delivery", "ring_simulator"] if kind == "package" else ["bee_simulator"],
        "materiality_threshold": 0,
    }
    response = client.post("/api/v1/expectations", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def submit(client, kind, identity):
    now = datetime.now(timezone.utc).isoformat()
    if kind == "electricity":
        response = client.post(f"/api/v1/expectations/{identity}/evidence", json={
            "source": "utility_bill", "metric": "total_cost", "value": {"amount": 180}, "unit": "USD",
            "observed_at": now, "confidence": 1, "external_event_id": "util_bill_demo-stable-0001",
            "raw_data": {"simulated": True, "category": "DEMO", "provenance": "USER_SUBMITTED"},
        })
        assert response.status_code == 201
        evidence = response.json()
        headers = {"Idempotency-Key": "simulation:util_bill_demo-stable-0001"}
        first = client.post(f"/api/v1/expectations/{identity}/evaluate", headers=headers)
        replay = client.post(f"/api/v1/expectations/{identity}/evaluate", headers=headers)
        assert first.status_code == replay.status_code == 200
        assert first.json()["id"] == replay.json()["id"]
        return evidence, first.json()
    if kind == "package":
        shipping = client.post(f"/api/v1/expectations/{identity}/evidence", json={
            "source": "delivery", "metric": "delivered", "value": {"value": True},
            "observed_at": now, "confidence": 1, "external_event_id": "demo_delivery_stable-0001",
            "raw_data": {"simulated": True, "category": "DEMO", "provenance": "USER_SUBMITTED"},
        })
        assert shipping.status_code == 201
        path = f"/api/v1/simulators/ring/expectations/{identity}/events"
        event = {"simulated": True, "event_id": "ring_sim_demo-stable-0001", "kind": "package_detected", "device": "front_door", "timestamp": datetime.now(timezone.utc).isoformat(), "confidence": 0.95, "metric": "delivered"}
    else:
        path = f"/api/v1/simulators/bee/expectations/{identity}/events"
        event = {"simulated": True, "id": "bee_sim_demo-stable-0001", "type": "commitment", "speaker": "Landlord", "summary": "My landlord said the plumber will arrive Friday.", "start_time": now, "metric": "appointment_confirmed", "confirmed": True}
    first = client.post(path, json=event)
    replay = client.post(path, json=event)
    assert first.status_code == replay.status_code == 200
    assert first.json() == replay.json()
    return first.json()["evidence"], first.json()["evaluation"]


@pytest.mark.parametrize("kind,result,status,provenance", [
    ("electricity", "MISMATCH", "contradicted", "USER_SUBMITTED"),
    ("package", "MATCH", "fulfilled", "SIMULATED_RING"),
    ("bee", "UNKNOWN", "monitoring", "SIMULATED_BEE"),
])
def test_demo_persistence_alerts_audit_and_replay(client, db, users, kind, result, status, provenance):
    expectation = create(client, kind)
    identity = expectation["id"]
    evidence, evaluation = submit(client, kind, identity)
    assert evaluation["result"] == result
    assert evidence["raw_data"]["simulated"] is True
    assert evidence["raw_data"]["provenance"] == provenance
    assert client.get(f"/api/v1/expectations/{identity}").json()["status"] == status
    saved_evidence = client.get(f"/api/v1/expectations/{identity}/evidence").json()
    assert evidence in saved_evidence
    assert len(saved_evidence) == (2 if kind == "package" else 1)
    assert all(item["raw_data"]["simulated"] is True for item in saved_evidence)
    assert client.get(f"/api/v1/expectations/{identity}/evaluations").json() == [evaluation]
    assert client.get(f"/api/v1/expectations/{identity}/evaluations/latest").json() == evaluation
    assert identity in [row["id"] for row in client.get("/api/v1/expectations").json()]
    notices = client.get("/api/v1/notifications").json()
    assert len(notices) == (1 if result == "MISMATCH" else 0)
    if notices:
        assert notices[0]["expectation_id"] == identity
        assert notices[0]["evaluation_id"] == evaluation["id"]
        assert notices[0]["status"] == "pending"
    if kind == "electricity":
        assert evaluation["expected"]["target"] == 150
        assert evaluation["observed"]["value"] - evaluation["expected"]["target"] == 30
    if kind == "bee":
        assert evidence["value"]["context_only"] is True
        assert evidence["value"]["commitment_confirmed"] is True
        assert "value" not in evidence["value"]
    # Expiring the ORM cache proves reads reload actual SQL records.
    db.expire_all()
    assert db.get(Expectation, UUID(identity)).user_id == users[0].id
    assert db.get(Evidence, UUID(evidence["id"])) is not None
    assert db.get(Evaluation, UUID(evaluation["id"])) is not None
    if notices:
        assert db.get(Notification, UUID(notices[0]["id"])) is not None
    events = list(db.scalars(select(AuditEvent).where(AuditEvent.expectation_id == UUID(identity))))
    assert {"EXPECTATION_CREATED", "EVIDENCE_INGESTED", "EVALUATION_COMPLETED"} <= {event.event_type for event in events}
    assert ("NOTIFICATION_CREATED" in {event.event_type for event in events}) == (result == "MISMATCH")
    audit = client.get("/api/v1/audit-events", params={"expectation_id": identity})
    assert audit.status_code == 200 and audit.json()
    app.dependency_overrides[get_current_user] = lambda: users[1]
    assert client.get(f"/api/v1/expectations/{identity}").status_code == 404
    assert client.get(f"/api/v1/expectations/{identity}/evidence").status_code == 404
    assert client.get("/api/v1/notifications").json() == []


def test_electricity_why_is_grounded_in_persisted_bill(wired, db, settings, monkeypatch):
    identity = create(wired, "electricity")["id"]
    evidence, evaluation = submit(wired, "electricity", identity)
    original = intelligence.investigation_service.investigate_mismatch
    calls = []

    def investigate(**kwargs):
        calls.append(True)
        investigator = BedrockMismatchInvestigator(settings=settings.model_copy(update={"bedrock_enabled": False}))
        try:
            return original(**kwargs, investigator=investigator)
        finally:
            investigator.close()

    monkeypatch.setattr(intelligence.investigation_service, "investigate_mismatch", investigate)
    response = wired.post("/api/v1/agent/converse", json={"text": "Why did it fail?", "expectation_id": identity, "session_reference": None})
    assert response.status_code == 200
    result = response.json()
    assert result["action"] == "EXPLAIN_MISMATCH" and result["status"] == "SUCCESS"
    assert "150" in result["answer"] and "180" in result["answer"]
    assert result["provenance"]["grounded"] is True
    assert result["provenance"]["fallback_used"] is True
    assert result["provenance"]["bedrock_used"] is False
    assert len(calls) == 1
    event = db.scalar(select(AuditEvent).where(AuditEvent.expectation_id == UUID(identity), AuditEvent.event_type == "EXPLANATION_GENERATED"))
    assert event is not None
    assert str(event.evaluation_id) == evaluation["id"]
    assert evidence["id"] in event.audit_metadata["evidence_ids"]


def test_exact_alexa_electricity_capture_full_linked_lifecycle(
    wired_alexa, signing, wire_engine, settings, monkeypatch, db, users
):
    """One canonical row from signed ASK capture through the entire demo chain."""
    from app.api.v1 import alexa as alexa_route
    from tests.test_clarification import initial
    from tests.test_expectation_compiler import compiled

    monkeypatch.setattr(alexa_route, "get_settings", lambda: settings.model_copy(update={
        "alexa_skill_id": test_alexa.SKILL, "alexa_require_confirmation": True,
    }))
    runtime = wire_engine(
        compiled(subject="electricity bill", target=150, quote="$150", comparison_quote="below"),
        compiled(), initial(),
    )
    _, sign = signing

    def voice(intent, text=None, previous=None):
        return test_alexa.post(wired_alexa, sign, test_alexa.event_body(
            intent=intent, text=text, attributes=previous["sessionAttributes"] if previous else None,
        ))

    turn = voice("CaptureExpectationIntent", "My next electricity bill should be below $150.")
    assert "Should I save it?" in test_alexa.speech(turn)
    assert wired_alexa.get("/api/v1/expectations").json() == []
    confirmation = test_alexa.event_body(intent="AMAZON.YesIntent", attributes=turn["sessionAttributes"])
    turn = test_alexa.post(wired_alexa, sign, confirmation)
    assert test_alexa.post(wired_alexa, sign, confirmation) == turn
    records = wired_alexa.get("/api/v1/expectations").json()
    assert len(records) == 1
    row = records[0]
    identity = row["id"]
    assert row["claim"] == "I'm counting on My next electricity bill should be below $150."
    assert row["target_value"] == 150 and row["comparison"] == "less_than"
    assert row["user_id"] == str(users[0].id)
    assert row["compiler_metadata"]["creation_source"] == "alexa_skill"
    # This is the normal full response consumed by lib/types.ts and api.board,
    # rather than an Alexa-only model or storage representation.
    assert {"id", "user_id", "claim", "type", "metric", "baseline", "target_value", "comparison", "deadline", "evidence_sources", "status", "compiler_metadata", "created_at", "updated_at"} <= row.keys()
    turn = voice("ListExpectationsIntent", previous=turn)
    assert row["claim"] in test_alexa.speech(turn)
    turn = voice("GetExpectationIntent", "my electricity bill", turn)
    assert row["claim"] in test_alexa.speech(turn)
    evidence, evaluation = submit(wired_alexa, "electricity", identity)
    original = intelligence.investigation_service.investigate_mismatch

    def investigate(**kwargs):
        investigator = BedrockMismatchInvestigator(settings=settings.model_copy(update={"bedrock_enabled": False}))
        try:
            return original(**kwargs, investigator=investigator)
        finally:
            investigator.close()

    monkeypatch.setattr(intelligence.investigation_service, "investigate_mismatch", investigate)
    turn = voice("WhyExpectationIntent", previous=turn)
    assert "150" in test_alexa.speech(turn) and "180" in test_alexa.speech(turn)
    assert wired_alexa.get(f"/api/v1/expectations/{identity}").json()["status"] == "contradicted"
    notification = wired_alexa.get("/api/v1/notifications").json()[0]
    assert notification["expectation_id"] == identity
    assert notification["evaluation_id"] == evaluation["id"]
    audit = wired_alexa.get("/api/v1/audit-events", params={"expectation_id": identity}).json()
    for kind in ("EXPECTATION_CONFIRMED", "EVIDENCE_INGESTED", "EVALUATION_COMPLETED", "NOTIFICATION_CREATED", "EXPLANATION_GENERATED"):
        event = next(item for item in audit if item["event_type"] == kind)
        assert event["expectation_id"] == identity
        if kind == "EXPECTATION_CONFIRMED":
            assert event["source_provider"] == "ALEXA" and event["source_provenance"] == "SIGNED_ASK"
        else:
            assert event["evidence_id"] == evidence["id"]
        if kind in ("EVALUATION_COMPLETED", "NOTIFICATION_CREATED", "EXPLANATION_GENERATED"):
            assert event["evaluation_id"] == evaluation["id"]
        if kind == "NOTIFICATION_CREATED":
            assert event["action_metadata"]["notification_id"] == notification["id"]
    # Continue the same real conversation through the other requested utterances.
    turn = voice("CaptureExpectationIntent", "I'm counting on my grocery bill staying under $120 this week.", turn)
    assert "Should I save it?" in test_alexa.speech(turn)
    turn = voice("AMAZON.YesIntent", previous=turn)
    assert len(wired_alexa.get("/api/v1/expectations").json()) == 2
    turn = voice("CaptureExpectationIntent", "I'm counting on my bill being lower.", turn)
    assert turn["response"]["directives"][0]["slotToElicit"] == "text"
    calls = runtime.converse.call_count
    turn = voice("CaptureExpectationIntent", "Never mind.", turn)
    assert "Nothing was saved" in test_alexa.speech(turn)
    assert runtime.converse.call_count == calls
    assert len(wired_alexa.get("/api/v1/expectations").json()) == 2
    assert db.get(Expectation, UUID(identity)).user_id == users[0].id
