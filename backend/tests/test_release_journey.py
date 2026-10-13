"""Release journey: real JWT/HTTP MCP/PostgreSQL, mocked inference/provider only.

This proves local wiring, not ASK NLU, Echo, cloud OAuth, or provider delivery.
"""

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from app.agent.actions import CapabilityTool, FailureCode
from app.agent.adapters import CapabilityError, StreamableMcpAdapter
from app.agent.orchestrator import AgentOrchestrator
from app.alexa.adapter import AlexaAdapter
from app.api import dependencies
from app.db.models import (
    Evaluation,
    Evidence,
    Expectation,
    MonitoringJob,
    Notification,
    ProviderSyncState,
)
from app.main import app as api_app
from app.mcp import auth, intelligence
from app.mcp.schemas import GetExpectationInput
from app.mcp.server import create_app, create_server
from app.monitoring.worker import Worker
from app.services import investigation_service
from tests import (
    test_agent,
    test_alexa,
    test_auth,
    test_automatic_tracking,
    test_monitoring,
    test_provider_sync,
)
from tests.test_clarification import decision, initial, patch
from tests.test_mcp_network import live_server
from tests.test_production_conversations import stores, voice_event

monitoring_sessions = test_monitoring.monitoring_sessions
scenario = test_monitoring.scenario
settings = test_agent.settings
wire_engine = test_agent.wire_engine
verifier = test_auth.verifier


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_name", ["google", "microsoft"])
async def test_confirmed_voice_capture_provider_worker_shared_state(
    scenario, settings, wire_engine, verifier, monkeypatch, provider_name
):
    sessions, (owner, fixture_id, fixture_job, _) = scenario
    verified, key = verifier
    encoded, _ = test_auth.token(verified, key, sub=str(owner))
    user = verified.verify(encoded)
    monkeypatch.setattr(auth, "get_token_verifier", lambda: verified)
    monkeypatch.setattr(dependencies, "get_token_verifier", lambda: verified)
    inference = wire_engine(
        initial("MISSING_BASELINE", "baseline"),
        decision(patch("baseline", 142.1, "$142.10")),
    )
    config = test_provider_sync.settings(monitoring_enabled=True)
    monkeypatch.setattr("app.core.config.get_settings", lambda: config)
    monkeypatch.setattr("app.api.v1.provider_sync.get_settings", lambda: config)
    with sessions() as db:
        db.get(MonitoringJob, fixture_job).status = "paused"
        db.commit()

    # The API dependencies open the same disposable database as MCP/workers.
    def api_db():
        with sessions() as db:
            yield db

    api_app.dependency_overrides[dependencies.get_db] = api_db
    try:
        with (
            live_server(
                create_app(create_server(session_factory=sessions), settings=settings)
            ) as origin,
            TestClient(api_app) as web,
        ):
            transport_settings = settings.model_copy(
                update={"mcp_public_url": origin + "/mcp"}
            )

            def host():
                core, voice = stores(
                    sessions
                )  # fresh instances prove restart persistence
                return AlexaAdapter(
                    voice,
                    AgentOrchestrator(
                        StreamableMcpAdapter(transport_settings, SecretStr(encoded)),
                        settings=settings,
                        session_store=core,
                        require_capture_confirmation=True,
                    ),
                )

            first = await host().handle(
                voice_event(
                    "CaptureExpectationIntent",
                    "my electricity bill being lower than my last bill when my next bill arrives",
                ),
                user,
            )
            assert first["response"]["directives"][0]["type"] == "Dialog.ElicitSlot"
            second = await host().handle(
                voice_event(
                    "CaptureExpectationIntent",
                    "My last bill was $142.10",
                    first["sessionAttributes"],
                ),
                user,
            )
            assert "Should I save it?" in test_alexa.speech(second)
            with sessions() as db:
                assert list(
                    db.scalars(
                        select(Expectation.id).where(Expectation.user_id == owner)
                    )
                ) == [fixture_id]
            confirmation = voice_event(
                "AMAZON.YesIntent", attrs=second["sessionAttributes"]
            )
            saved = await host().handle(confirmation, user)
            assert test_alexa.speech(saved) == "Got it. I'll track that."
            assert await host().handle(confirmation, user) == saved
            with sessions() as db:
                expectation = db.scalar(
                    select(Expectation).where(
                        Expectation.user_id == owner, Expectation.id != fixture_id
                    )
                )
                eid = expectation.id
                assert str(expectation.baseline) == "142.1"
                now = datetime.now(timezone.utc)
                conn, oauth, _ = test_provider_sync.connect(
                    db, owner, provider_name, "email", now
                )
                sync = ProviderSyncState(
                    connection_id=conn.id,
                    user_id=owner,
                    stream="inbox",
                    next_run_at=now,
                )
                db.add(sync)
                db.commit()
                now = datetime.now(timezone.utc)
                data = (
                    sessions,
                    owner,
                    eid,
                    None,
                    now,
                    sync.id,
                    conn.id,
                    oauth,
                    config,
                )

            # Normalize an authorized official-response fixture; no manual evidence POST.
            facts = test_provider_sync.mail_facts(
                test_provider_sync.gmail(now=now)
                if provider_name == "google"
                else {
                    "id": "mail1",
                    "conversationId": "thread1",
                    "receivedDateTime": now.isoformat(),
                    "lastModifiedDateTime": now.isoformat(),
                    "from": {"emailAddress": {"address": "bills@example.test"}},
                    "toRecipients": [
                        {"emailAddress": {"address": "owner@example.test"}}
                    ],
                    "subject": "Electricity bill",
                    "body": {"content": "Total due: $162.00"},
                },
                provider_name,
            )
            assert test_automatic_tracking.synchronizer(data, [("mail1", facts)]).once()
            headers = {"Authorization": "Bearer " + encoded}
            # Discovery reads owned synchronized projections. It does not ingest
            # evidence or schedule until the user explicitly selects a reference.
            with sessions() as db:
                assert not list(
                    db.scalars(select(Evidence).where(Evidence.expectation_id == eid))
                )
                assert not list(
                    db.scalars(
                        select(Notification).where(Notification.expectation_id == eid)
                    )
                )
            planned = web.post(
                f"/api/v1/expectations/{eid}/monitoring-plan/preview",
                headers=headers,
                json={},
            )
            assert planned.status_code == 200
            candidate = planned.json()["candidates"][0]
            assert candidate["suggestion_reason"] and candidate["synced_at"]
            selection = {
                "confirmed": True,
                "sources": [
                    {
                        "sync_id": candidate["sync_id"],
                        "external_id": candidate["external_id"],
                    }
                ],
            }
            applied = web.post(
                f"/api/v1/expectations/{eid}/monitoring-plan/confirm",
                headers=headers,
                json=selection,
            )
            assert applied.status_code == 200
            replay = web.post(
                f"/api/v1/expectations/{eid}/monitoring-plan/confirm",
                headers=headers,
                json=selection,
            )
            assert replay.json() == applied.json()
            with sessions() as db:
                db.get(ProviderSyncState, data[5]).next_run_at = now
                db.commit()
            assert test_automatic_tracking.synchronizer(
                data, [("mail1", facts)], full=False
            ).once()
            worker = Worker(config, sessions)
            assert worker.run_once(now=now)
            headers = {"Authorization": "Bearer " + encoded}
            detail = web.get(f"/api/v1/expectations/{eid}", headers=headers)
            assert (
                detail.status_code == 200 and detail.json()["status"] == "contradicted"
            )
            history = web.get(
                f"/api/v1/expectations/{eid}/evaluations", headers=headers
            )
            assert (
                history.status_code == 200 and history.json()[0]["result"] == "MISMATCH"
            )
            evidence_ids = history.json()[0]["reasoning"]["evidence_ids"]
            inbox = web.get("/api/v1/notifications", headers=headers)
            rows = [item for item in inbox.json() if item["expectation_id"] == str(eid)]
            assert (
                len(rows) == 1 and rows[0]["metadata"]["evidence_ids"] == evidence_ids
            )
            spoken = await host().handle(
                voice_event(
                    "GetExpectationIntent",
                    "my electricity bill",
                    saved["sessionAttributes"],
                ),
                user,
            )
            assert "needs attention" in test_alexa.speech(spoken)

            # Exercise real grounded fallback without any AWS dependency.
            from app.ai.mismatch_investigator import BedrockMismatchInvestigator

            investigator = BedrockMismatchInvestigator(
                settings=settings.model_copy(update={"bedrock_enabled": False})
            )
            original = investigation_service.investigate_mismatch
            monkeypatch.setattr(
                intelligence.investigation_service,
                "investigate_mismatch",
                lambda **kwargs: original(**kwargs, investigator=investigator),
            )
            try:
                why = await host().handle(
                    voice_event(
                        "WhyExpectationIntent", attrs=spoken["sessionAttributes"]
                    ),
                    user,
                )
                assert "162" in test_alexa.speech(why) and "142.1" in test_alexa.speech(
                    why
                )
            finally:
                investigator.close()
            with sessions() as db:
                job = db.scalar(
                    select(MonitoringJob).where(MonitoringJob.expectation_id == eid)
                )
                job.next_run_at = now
                db.commit()
            assert worker.run_once(now=now)
            with sessions() as db:
                assert (
                    len(
                        list(
                            db.scalars(
                                select(Notification).where(
                                    Notification.expectation_id == eid
                                )
                            )
                        )
                    )
                    == 1
                )
                assert (
                    db.scalar(
                        select(Evaluation).where(Evaluation.expectation_id == eid)
                    ).result.value
                    == "MISMATCH"
                )

            # Web-owned edits/cancellation must be observed by the voice/MCP read path.
            assert (
                web.patch(
                    f"/api/v1/expectations/{eid}",
                    headers=headers,
                    json={"baseline": 150},
                ).status_code
                == 200
            )
            assert (
                web.patch(
                    f"/api/v1/expectations/{eid}",
                    headers=headers,
                    json={"status": "cancelled"},
                ).status_code
                == 200
            )
            cancelled = await host().handle(
                voice_event(
                    "GetExpectationIntent",
                    "my electricity bill",
                    why["sessionAttributes"],
                ),
                user,
            )
            assert "cancelled" in test_alexa.speech(cancelled)
            foreign, _ = test_auth.token(verified, key, sub=str(uuid4()))
            assert (
                web.get(
                    f"/api/v1/expectations/{eid}",
                    headers={"Authorization": "Bearer " + foreign},
                ).status_code
                == 404
            )
            foreign_adapter = StreamableMcpAdapter(
                transport_settings, SecretStr(foreign)
            )
            with pytest.raises(CapabilityError) as denied:
                await foreign_adapter.call(
                    verified.verify(foreign),
                    CapabilityTool.GET,
                    GetExpectationInput(expectation_id=eid),
                )
            assert denied.value.code == FailureCode.NOT_FOUND
            assert inference.converse.call_count == 2
    finally:
        api_app.dependency_overrides.pop(dependencies.get_db, None)
