"""Offline acceptance: official-provider fixtures, real PostgreSQL, real workers/API."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.models import (
    Evaluation,
    Evidence,
    Expectation,
    MonitoringJob,
    Notification,
    NotificationDelivery,
    NotificationPreference,
    ProviderSyncState,
    ProviderWatch,
)
from app.integrations.adapters import Page
from app.integrations.normalization import calendar_facts, mail_facts
from app.integrations.provider import ProviderError
from app.integrations.worker import SyncWorker
from app.monitoring.worker import Worker, claim_due
from app.notifications.delivery import EmailChannel, encrypt, ready_at
from app.notifications.worker import DeliveryWorker
from app.schemas.provider_sync import BindingCreate, SourceRule
from app.services import notification_service, provider_sync_service
from tests import test_monitoring as monitoring
from tests import test_provider_sync as provider

monitoring_sessions = monitoring.monitoring_sessions
scenario = monitoring.scenario


def source(
    scenario,
    monkeypatch,
    *,
    metric="reply_received",
    kind="reply",
    provider_name="google",
    deadline=True,
):
    sessions, (owner, eid, jid, now) = scenario
    config = provider.settings(monitoring_enabled=True)
    monkeypatch.setattr("app.core.config.get_settings", lambda: config)
    with sessions() as db:
        exp = db.get(Expectation, eid)
        exp.type, exp.metric, exp.comparison, exp.baseline = (
            "boolean",
            metric,
            None,
            None,
        )
        exp.evidence_sources = []
        exp.deadline = now - timedelta(minutes=1) if deadline else None
        db.commit()
        conn, oauth, _ = provider.connect(
            db, owner, provider_name, "calendar" if kind == "calendar" else "email", now
        )
        sync = ProviderSyncState(
            connection_id=conn.id,
            user_id=owner,
            stream="calendar1" if kind == "calendar" else "inbox",
            next_run_at=now,
        )
        db.add(sync)
        db.commit()
        rule = (
            SourceRule(
                kind=kind, event_id="event1", expected_start=now + timedelta(days=1)
            )
            if kind == "calendar"
            else SourceRule(
                kind=kind,
                sender="bills@example.test",
                thread_id="thread1",
                subject_contains="electricity",
                order_id="123-1234567-1234567" if kind == "order" else None,
            )
        )
        provider_sync_service.bind(
            db, eid, owner, BindingCreate(sync_id=sync.id, rule=rule)
        )
        sync.next_run_at = now
        db.get(MonitoringJob, jid).next_run_at = db.get(
            MonitoringJob, jid
        ).scheduled_at = now
        if kind == "reply":
            # This fixture represents a connected mailbox already synchronized
            # before the expectation was captured. Initial-scan gaps have their
            # own regression below and must never establish absence.
            sync.encrypted_checkpoint = oauth.encrypt({"history": "90"}, sync.id)
            sync.coverage_start_at = now - timedelta(hours=3)
            sync.coverage_through_at = sync.last_success_at = now - timedelta(hours=2)
        db.commit()
        return sessions, owner, eid, jid, now, sync.id, conn.id, oauth, config


def synchronizer(data, events, *, clock=None, complete=True, full=None):
    sessions, _, _, _, now, sync_id, _, oauth, config = data
    if full is None:
        with sessions() as db:
            full = not bool(db.get(ProviderSyncState, sync_id).encrypted_checkpoint)

    class Adapter:
        def __init__(self, *args):
            pass

        def page(self, *args):
            return Page(events, {"history": "100"}, complete, full)

    return SyncWorker(
        sessions,
        config,
        oauth_factory=lambda *args: oauth,
        adapter_factory=Adapter,
        now=clock or (lambda: now),
    )


def results(data):
    sessions, _, eid, *_ = data
    with sessions() as db:
        evaluations = list(
            db.scalars(
                select(Evaluation)
                .where(Evaluation.expectation_id == eid)
                .order_by(Evaluation.created_at, Evaluation.id)
            )
        )
        notifications = list(
            db.scalars(select(Notification).where(Notification.expectation_id == eid))
        )
        return evaluations, notifications


def test_a_reply_absent_after_covered_deadline_one_alert(scenario, monkeypatch):
    data = source(scenario, monkeypatch)
    sessions, _, eid, jid, now, *_ = data
    assert synchronizer(data, []).once()
    assert Worker(data[-1], sessions).run_once(now=now)
    evaluations, notices = results(data)
    assert evaluations[-1].result.value == "MISMATCH"
    assert evaluations[-1].reasoning["reason"] == "reply_absent_after_covered_deadline"
    assert evaluations[-1].reasoning["evidence_ids"]
    assert len(notices) == 1 and notices[0].type == "expectation_mismatch"
    # Repeat coverage with a new cursor/time: same mismatch episode, one alert.
    with sessions() as db:
        db.get(ProviderSyncState, data[5]).next_run_at = now
        db.commit()
    later = now + timedelta(minutes=2)
    assert synchronizer(data, [], clock=lambda: later, full=False).once()
    assert Worker(data[-1], sessions).run_once(now=later)
    assert len(results(data)[1]) == 1
    with sessions() as db:
        assert db.get(MonitoringJob, jid).status == "pending"
        assert db.get(Expectation, eid).status.value == "contradicted"


@pytest.mark.parametrize(
    "impairment",
    ["before_deadline", "partial", "old_window", "unknown_tombstone", "deleted_reply"],
)
def test_absence_requires_complete_current_coverage(scenario, monkeypatch, impairment):
    data = source(scenario, monkeypatch)
    sessions, _, eid, _, now, *_ = data
    events = []
    if impairment == "before_deadline":
        with sessions() as db:
            db.get(Expectation, eid).deadline = now + timedelta(minutes=1)
            db.commit()
    elif impairment == "old_window":
        with sessions() as db:
            db.get(Expectation, eid).created_at = now - timedelta(days=31)
            db.commit()
    elif impairment == "unknown_tombstone":
        events = [("unknown", {"kind": "email", "unavailable": True})]
    elif impairment == "deleted_reply":
        facts = mail_facts(provider.gmail(now=now - timedelta(minutes=5)), "google")
        events = [("mail1", {**facts, "unavailable": True})]
    assert synchronizer(data, events, complete=impairment != "partial").once()
    assert Worker(data[-1], sessions).run_once(now=now)
    evaluations, notices = results(data)
    assert evaluations[-1].result.value == "UNKNOWN"
    assert not any(n.type == "expectation_mismatch" for n in notices)


@pytest.mark.parametrize("minutes,result", [(-10, "MATCH"), (0, "MISMATCH")])
def test_reply_chronology(scenario, monkeypatch, minutes, result):
    data = source(scenario, monkeypatch)
    now = data[4]
    facts = mail_facts(provider.gmail(now=now + timedelta(minutes=minutes)), "google")
    assert synchronizer(data, [("mail1", facts)]).once()
    assert Worker(data[-1], data[0]).run_once(now=now)
    assert results(data)[0][-1].result.value == result


def test_later_reply_does_not_undo_earlier_on_time_reply(scenario, monkeypatch):
    data = source(scenario, monkeypatch)
    now = data[4]
    events = [
        (
            "first",
            mail_facts(provider.gmail(now=now - timedelta(minutes=10)), "google"),
        ),
        ("second", mail_facts(provider.gmail(now=now), "google")),
    ]
    assert synchronizer(data, events).once()
    assert Worker(data[-1], data[0]).run_once(now=now)
    assert results(data)[0][-1].result.value == "MATCH"


def webhook_client(data, monkeypatch):
    from app.api.dependencies import get_db
    from app.api.v1 import provider_sync
    from app.main import app

    sessions, owner, _, _, now, sync_id, _, oauth, config = data
    monkeypatch.setattr(provider_sync, "get_settings", lambda: config)
    monkeypatch.setattr(provider_sync, "account_oauth", lambda *args: oauth)
    subscription = str(uuid4())
    with sessions() as db:
        db.add(
            ProviderWatch(
                sync_id=sync_id,
                user_id=owner,
                provider="graph",
                external_id=subscription,
                encrypted_secret=oauth.encrypt(
                    {"token": "fixture-watch-secret"}, sync_id
                ),
                expires_at=now + timedelta(days=1),
            )
        )
        db.get(ProviderSyncState, sync_id).next_run_at = now + timedelta(days=1)
        db.commit()

    def database():
        with sessions() as db:
            yield db

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = database
    return (
        app,
        previous,
        TestClient(app),
        {
            "value": [
                {
                    "subscriptionId": subscription,
                    "clientState": "fixture-watch-secret",
                    "resource": "https://evil.test/never-fetch",
                }
            ]
        },
    )


@pytest.mark.parametrize("cancelled", [False, True])
def test_b_d_e_verified_graph_event_updates_calendar_and_deduplicates(
    scenario, monkeypatch, cancelled
):
    data = source(
        scenario,
        monkeypatch,
        metric="event_not_cancelled" if cancelled else "event_unchanged",
        kind="calendar",
        provider_name="microsoft",
        deadline=False,
    )
    sessions, _, _, _, now, *_ = data
    event = {
        "id": "event1",
        "subject": "Appointment",
        "isCancelled": cancelled,
        "start": {"dateTime": (now + timedelta(days=1, hours=2)).isoformat()},
        "end": {"dateTime": (now + timedelta(days=1, hours=3)).isoformat()},
        "lastModifiedDateTime": now.isoformat(),
    }
    facts = calendar_facts(event, "microsoft")
    app, previous, client, body = webhook_client(data, monkeypatch)
    try:
        with client:
            bad = {"value": [{**body["value"][0], "clientState": "forged"}]}
            assert (
                client.post(
                    "/api/v1/integrations/webhooks/microsoft", json=bad
                ).status_code
                == 400
            )
            for i in range(3):
                assert (
                    client.post(
                        "/api/v1/integrations/webhooks/microsoft", json=body
                    ).status_code
                    == 202
                )
                checked = now + timedelta(seconds=5 + i)
                assert synchronizer(
                    data, [("event1", facts)], clock=lambda checked=checked: checked
                ).once()
                assert Worker(data[-1], sessions).run_once(now=checked)
            evaluations, notices = results(data)
            assert evaluations[-1].result.value == "MISMATCH" and len(notices) == 1
            with sessions() as db:
                assert db.scalar(select(func.count()).select_from(Evidence)) == 1
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def test_c_changed_delivery_estimate_is_warning_not_confirmed_failure(
    scenario, monkeypatch
):
    data = source(scenario, monkeypatch, metric="delivery_reported", kind="order")
    sessions, _, eid, _, now, *_ = data
    with sessions() as db:
        db.get(Expectation, eid).deadline = now + timedelta(days=5)
        db.commit()
    text = (
        "Order 123-1234567-1234567 has shipped. Expected delivery: "
        + (now + timedelta(days=5)).date().isoformat()
        + ". Revised delivery: "
        + (now + timedelta(days=8)).date().isoformat()
    )
    facts = mail_facts(provider.gmail(now=now, text=text), "google")
    assert synchronizer(data, [("mail1", facts)]).once()
    assert Worker(data[-1], sessions).run_once(now=now)
    evaluations, notices = results(data)
    assert evaluations[-1].result.value == "UNKNOWN"
    assert len(notices) == 1 and notices[0].type == "potential_delivery_delay"
    assert notices[0].notification_metadata["certainty"] == "predicted"


@pytest.mark.parametrize("timestamped,result", [(False, "UNKNOWN"), (True, "MATCH")])
def test_delivery_receipt_is_not_delivery_time(
    scenario, monkeypatch, timestamped, result
):
    data = source(scenario, monkeypatch, metric="delivery_reported", kind="order")
    now = data[4]
    text = "Order 123-1234567-1234567 has been delivered."
    if timestamped:
        text += " Delivered at: " + (now - timedelta(minutes=10)).isoformat(
            timespec="seconds"
        )
    facts = mail_facts(provider.gmail(now=now, text=text), "google")
    assert synchronizer(data, [("mail1", facts)]).once()
    assert Worker(data[-1], data[0]).run_once(now=now)
    assert results(data)[0][-1].result.value == result


def test_f_expired_oauth_wakes_unknown_and_connection_warning(scenario, monkeypatch):
    data = source(scenario, monkeypatch)
    sessions, _, _, _, now, *_ = data
    monkeypatch.setattr(
        data[7],
        "access_token",
        lambda *a: (_ for _ in ()).throw(
            ProviderError("AUTH_REQUIRED", retryable=False)
        ),
    )
    assert synchronizer(data, []).once()
    assert Worker(data[-1], sessions).run_once(now=now)
    evaluations, notices = results(data)
    assert evaluations[-1].result.value == "UNKNOWN"
    assert evaluations[-1].reasoning["reason"] == "source_unavailable"
    assert len(notices) == 1 and notices[0].type == "connection_warning"


def test_g_crash_after_evidence_before_notification_recovers(scenario, monkeypatch):
    data = source(scenario, monkeypatch)
    sessions, _, _, _, now, *_ = data
    assert synchronizer(data, []).once()
    worker = Worker(data[-1], sessions)
    with sessions() as db:
        claim = claim_due(db, 300, now=now)
    with monkeypatch.context() as patch:
        patch.setattr(
            notification_service,
            "for_evaluation",
            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("fixture crash")),
        )
        with pytest.raises(RuntimeError):
            worker.finish(claim, [], now=now)
    assert not results(data)[0]
    assert Worker(data[-1], sessions).run_once(now=now + timedelta(seconds=301))
    assert len(results(data)[1]) == 1
    assert not worker.finish(claim, [], now=now + timedelta(seconds=302))


def test_completed_match_reopens_on_calendar_change(scenario, monkeypatch):
    data = source(
        scenario,
        monkeypatch,
        metric="event_not_cancelled",
        kind="calendar",
        deadline=False,
    )
    now = data[4]
    assert synchronizer(
        data, [("event1", calendar_facts(provider.calendar(), "google"))]
    ).once()
    assert Worker(data[-1], data[0]).run_once(now=now)
    assert results(data)[0][-1].result.value == "MATCH"
    with data[0]() as db:
        db.get(ProviderSyncState, data[5]).next_run_at = now
        db.commit()
    assert synchronizer(
        data,
        [("event1", calendar_facts(provider.calendar(status="cancelled"), "google"))],
        clock=lambda: now + timedelta(seconds=10),
    ).once()
    assert Worker(data[-1], data[0]).run_once(now=now + timedelta(seconds=10))
    assert (
        results(data)[0][-1].result.value == "MISMATCH" and len(results(data)[1]) == 1
    )


def test_source_failure_never_reuses_previous_match(scenario, monkeypatch):
    data = source(
        scenario, monkeypatch, metric="event_scheduled", kind="calendar", deadline=False
    )
    assert synchronizer(
        data, [("event1", calendar_facts(provider.calendar(), "google"))]
    ).once()
    assert Worker(data[-1], data[0]).run_once(now=data[4])
    with data[0]() as db:
        db.get(ProviderSyncState, data[5]).status = "auth_required"
        from app.monitoring.sources import wake

        wake(db, db.get(Expectation, data[2]), data[4])
        db.commit()
    assert Worker(data[-1], data[0]).run_once(now=data[4])
    assert results(data)[0][-1].result.value == "UNKNOWN"


def test_explicit_pause_survives_source_event(scenario, monkeypatch):
    data = source(scenario, monkeypatch)
    with data[0]() as db:
        db.get(MonitoringJob, data[3]).status = "paused"
        db.commit()
    assert synchronizer(data, []).once()
    assert not Worker(data[-1], data[0]).run_once(now=data[4])
    assert not results(data)[0]


def email_config():
    return provider.settings(
        notification_email_enabled=True,
        notification_email_api_key="fixture-only",
        notification_email_from="alerts@example.test",
        frontend_public_url="https://counton.test",
    )


def outbox(scenario):
    sessions, (owner, eid, _, now) = scenario
    config = email_config()
    with sessions() as db:
        db.add(
            NotificationPreference(
                user_id=owner,
                email_enabled=True,
                encrypted_recipient=encrypt(
                    config, {"email": "user@example.test"}, owner
                ),
            )
        )
        db.flush()
        notification_service.notice(
            db,
            db.get(Expectation, eid),
            "connection_warning",
            "Source needs attention.",
            "fixture",
        )
        for delivery in db.scalars(
            select(NotificationDelivery).where(NotificationDelivery.user_id == owner)
        ):
            delivery.next_run_at = now
        db.commit()
    return sessions, owner, eid, now, config


def test_outbox_crash_after_provider_acceptance_is_idempotent(scenario):
    sessions, _, _, now, config = outbox(scenario)
    accepted, requests = {}, []

    def respond(request):
        key = request.headers["Idempotency-Key"]
        requests.append((key, request.content))
        accepted.setdefault(key, len(accepted) + 1)
        return httpx.Response(200, json={"id": str(accepted[key])})

    channel = EmailChannel(config, transport=httpx.MockTransport(respond))
    worker = DeliveryWorker(sessions, config, channel=channel, now=lambda: now)
    claim = worker.claim()
    channel.send(claim[2], claim[0])  # process dies before acknowledging accepted send
    restarted = DeliveryWorker(
        sessions, config, channel=channel, now=lambda: now + timedelta(seconds=61)
    )
    assert restarted.once() and not restarted.once()
    assert len(accepted) == 1 and requests[0] == requests[1]
    with sessions() as db:
        delivery = db.get(NotificationDelivery, claim[0])
        assert delivery.status == "sent"
        assert db.get(Notification, delivery.notification_id).status == "pending"


def test_outbox_concurrent_workers_claim_once(scenario):
    sessions, _, _, now, config = outbox(scenario)
    with ThreadPoolExecutor(max_workers=2) as pool:
        claims = list(
            pool.map(
                lambda _: DeliveryWorker(sessions, config, now=lambda: now).claim(),
                range(2),
            )
        )
    assert sum(bool(c) for c in claims) == 1


def test_outbox_retry_and_dead_letter(scenario):
    sessions, _, _, now, config = outbox(scenario)
    channel = EmailChannel(
        config, transport=httpx.MockTransport(lambda _: httpx.Response(503))
    )
    assert DeliveryWorker(sessions, config, channel=channel, now=lambda: now).once()
    with sessions() as db:
        item = db.scalar(select(NotificationDelivery))
        assert item.status == "pending"
        assert item.last_error == "PROVIDER_UNAVAILABLE"
        item.first_attempt_at = now - timedelta(hours=24)
        item.next_run_at = now
        db.commit()
    assert DeliveryWorker(sessions, config, channel=channel, now=lambda: now).once()
    with sessions() as db:
        assert (
            db.scalar(select(NotificationDelivery)).last_error
            == "DELIVERY_WINDOW_EXPIRED"
        )


def test_quiet_hours_dst_and_unread_inbox(scenario):
    sessions, owner, _, _now, config = outbox(scenario)
    from datetime import datetime

    instant = datetime(
        2026, 11, 1, 6, 30, tzinfo=timezone.utc
    )  # repeated 1:30 AM Chicago
    with sessions() as db:
        pref = db.get(NotificationPreference, owner)
        (
            pref.quiet_enabled,
            pref.quiet_start_hour,
            pref.quiet_end_hour,
            pref.timezone,
        ) = True, 22, 8, "America/Chicago"
        assert (
            ready_at(pref, instant)
            .astimezone(__import__("zoneinfo").ZoneInfo("America/Chicago"))
            .hour
            == 8
        )
        assert db.scalar(select(Notification)).status == "pending"
        db.commit()
    assert DeliveryWorker(sessions, config, now=lambda: instant).once()
    with sessions() as db:
        assert db.scalar(select(NotificationDelivery)).status == "pending"
        assert db.scalar(select(NotificationDelivery)).attempt_count == 0


def test_preferences_owned_no_recipient_injection(client, db, users):
    from app.api.v1.notification_preferences import Preferences

    assert client.get("/api/v1/notification-preferences").status_code == 200
    response = client.put(
        "/api/v1/notification-preferences",
        json={"timezone": "America/Chicago", "deadline_enabled": True},
    )
    assert response.status_code == 200 and response.json()["deadline_enabled"]
    assert (
        "encrypted_recipient" not in response.json()
        and "user_id" not in response.json()
    )
    assert (
        client.put(
            "/api/v1/notification-preferences",
            json={"recipient": "attacker@example.test"},
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/api/v1/notification-preferences", json={"timezone": "Not/AZone"}
        ).status_code
        == 422
    )
    with pytest.raises(ValueError):
        Preferences(quiet_enabled=True, quiet_start_hour=0, quiet_end_hour=0)
    assert db.get(NotificationPreference, users[1].id) is None


def test_unconfirmed_or_wrong_supabase_identity_not_opted_in(monkeypatch):
    from app.api.v1 import notification_preferences as api
    from app.core.exceptions import AuthenticationError, InvalidExpectationError

    owner = uuid4()
    config = email_config()
    config.supabase_url, config.supabase_publishable_key = (
        "https://auth.test",
        "fixture",
    )
    original = httpx.Client
    for identity in (
        {"id": str(owner), "email": "a@example.test"},
        {"id": str(uuid4()), "email": "a@example.test", "email_confirmed_at": "yes"},
    ):
        monkeypatch.setattr(
            api.httpx,
            "Client",
            lambda identity=identity, **kwargs: original(
                transport=httpx.MockTransport(
                    lambda _, identity=identity: httpx.Response(200, json=identity)
                ),
                **kwargs,
            ),
        )
        expected = (
            InvalidExpectationError
            if identity["id"] == str(owner)
            else AuthenticationError
        )
        with pytest.raises(expected):
            api.confirmed_email(config, "Bearer fixture", owner)


def test_webhook_during_sync_is_not_lost(scenario, monkeypatch):
    data = source(scenario, monkeypatch)
    clock = [data[4]]

    class Adapter:
        def __init__(self, *args):
            pass

        def page(self, *args):
            with data[0]() as db:
                db.get(ProviderSyncState, data[5]).wake_requested_at = clock[
                    0
                ] + timedelta(seconds=1)
                db.commit()
            return Page([], {"history": "100"}, True, True)

    worker = SyncWorker(
        data[0],
        data[-1],
        oauth_factory=lambda *args: data[7],
        adapter_factory=Adapter,
        now=lambda: clock[0],
    )
    assert worker.once()
    with data[0]() as db:
        assert db.get(ProviderSyncState, data[5]).next_run_at <= clock[0]


def test_completed_calendar_delta_revalidates_unchanged_state_not_email(
    scenario, monkeypatch
):
    data = source(
        scenario, monkeypatch, metric="event_scheduled", kind="calendar", deadline=False
    )
    assert synchronizer(
        data, [("event1", calendar_facts(provider.calendar(), "google"))]
    ).once()
    assert Worker(data[-1], data[0]).run_once(now=data[4])
    later = data[4] + timedelta(days=2)
    with data[0]() as db:
        db.get(ProviderSyncState, data[5]).next_run_at = later
        db.commit()
    assert synchronizer(data, [], clock=lambda: later, full=False).once()
    assert Worker(data[-1], data[0]).run_once(now=later)
    row = results(data)[0][-1]
    assert row.result.value == "MATCH" and row.reasoning["calendar_state_revalidated"]
    with data[0]() as db:
        assert db.scalar(select(func.count()).select_from(Evidence)) == 1


def test_stale_source_does_not_revalidate_calendar(scenario, monkeypatch):
    data = source(
        scenario, monkeypatch, metric="event_scheduled", kind="calendar", deadline=False
    )
    assert synchronizer(
        data, [("event1", calendar_facts(provider.calendar(), "google"))]
    ).once()
    assert Worker(data[-1], data[0]).run_once(now=data[4] + timedelta(days=2))
    assert results(data)[0][-1].result.value == "UNKNOWN"
    assert results(data)[0][-1].reasoning["reason"] == "stale_source"


def test_multiple_explicit_sources_abstain_and_require_selection(scenario, monkeypatch):
    from app.db.models import ExpectationSourceBinding

    data = source(scenario, monkeypatch)
    with data[0]() as db:
        sync = ProviderSyncState(
            connection_id=data[6],
            user_id=data[1],
            stream="second",
            next_run_at=data[4] + timedelta(days=10),
        )
        db.add(sync)
        db.flush()
        db.add(
            ExpectationSourceBinding(
                expectation_id=data[2],
                user_id=data[1],
                sync_id=sync.id,
                rule=SourceRule(
                    kind="reply", sender="bills@example.test", thread_id="thread2"
                ).model_dump(mode="json"),
            )
        )
        db.commit()
    assert synchronizer(data, []).once()
    assert Worker(data[-1], data[0]).run_once(now=data[4])
    assert results(data)[0][-1].reasoning["reason"] == "ambiguous_sources"
    assert not any(n.type == "expectation_mismatch" for n in results(data)[1])


def test_untrusted_absence_assertion_cannot_claim_mismatch(scenario, monkeypatch):
    from app.integrations.normalization import version
    from app.monitoring.sources import wake

    data = source(scenario, monkeypatch)
    assert synchronizer(data, [], complete=False).once()
    with data[0]() as db:
        from app.db.models import ExpectationSourceBinding

        binding = db.scalar(select(ExpectationSourceBinding))
        connection = db.get(
            __import__(
                "app.db.models", fromlist=["IntegrationConnection"]
            ).IntegrationConnection,
            data[6],
        )
        sync = db.get(ProviderSyncState, data[5])
        sync.last_success_at = data[4]
        db.add(
            Evidence(
                expectation_id=data[2],
                metric="reply_received",
                value={"value": False},
                source="gmail_email",
                confidence=1,
                observed_at=data[4],
                external_event_id="forged",
                raw_data={
                    "binding_id": str(binding.id),
                    "binding_rule": version(binding.rule),
                    "connection_id": str(connection.id),
                    "account_id": connection.external_account_id,
                    "oauth_generation": str(connection.oauth_generation),
                    "absence_verified": True,
                    "coverage_signature": "forged",
                },
            )
        )
        wake(db, db.get(Expectation, data[2]), data[4])
        db.commit()
    assert Worker(data[-1], data[0]).run_once(now=data[4])
    assert results(data)[0][-1].result.value == "UNKNOWN"


def test_source_crash_attempts_are_bounded(scenario, monkeypatch):
    data = source(scenario, monkeypatch)
    with data[0]() as db:
        sync = db.get(ProviderSyncState, data[5])
        sync.status, sync.attempt_count, sync.lease_expires_at = (
            "running",
            8,
            data[4] - timedelta(seconds=1),
        )
        db.commit()
    assert not synchronizer(data, []).once()
    with data[0]() as db:
        sync = db.get(ProviderSyncState, data[5])
        assert sync.status == "error" and sync.last_error == "ATTEMPTS_EXHAUSTED"


def test_upcoming_deadline_requires_opt_in_and_is_deduplicated(scenario):
    sessions, (owner, eid, _, now) = scenario
    with sessions() as db:
        db.add(NotificationPreference(user_id=owner, deadline_enabled=True))
        db.get(Expectation, eid).deadline = now + timedelta(hours=1)
        db.scalar(
            select(MonitoringJob).where(MonitoringJob.expectation_id == eid)
        ).interval_seconds = 60
        db.commit()
    assert Worker(monitoring.settings(), sessions).run_once(now=now)
    assert Worker(monitoring.settings(), sessions).run_once(
        now=now + timedelta(minutes=10)
    )
    with sessions() as db:
        notices = list(
            db.scalars(select(Notification).where(Notification.user_id == owner))
        )
        assert len(notices) == 1 and notices[0].type == "upcoming_deadline"
        evaluation = db.get(
            Evaluation, notices[0].notification_metadata["evaluation_id"]
        )
        assert evaluation.expectation_id == eid
        assert notices[0].notification_metadata["evaluation_id"] == str(evaluation.id)
        assert notices[0].evaluation_id is None


def test_impaired_source_and_upcoming_deadline_do_not_suppress_each_other(scenario):
    sessions, (owner, eid, _, now) = scenario
    with sessions() as db:
        db.add(NotificationPreference(user_id=owner, deadline_enabled=True))
        expectation = db.get(Expectation, eid)
        expectation.deadline = now + timedelta(hours=1)
        expectation.evidence_sources = ["gmail_email"]
        job = db.scalar(
            select(MonitoringJob).where(MonitoringJob.expectation_id == eid)
        )
        job.connection_id = None
        job.interval_seconds = 60
        db.commit()
    worker = Worker(monitoring.settings(), sessions)
    assert worker.run_once(now=now)
    assert worker.run_once(now=now + timedelta(minutes=10))
    with sessions() as db:
        notices = list(
            db.scalars(select(Notification).where(Notification.user_id == owner))
        )
        assert sorted(n.type for n in notices) == [
            "connection_warning",
            "upcoming_deadline",
        ]
        evaluation = db.get(
            Evaluation, notices[0].notification_metadata["evaluation_id"]
        )
        assert evaluation.expectation_id == eid
        assert evaluation.result.value == "UNKNOWN"
        assert {n.notification_metadata["evaluation_id"] for n in notices} == {
            str(evaluation.id)
        }


def test_acknowledged_notification_suppresses_queued_email(scenario):
    sessions, owner, _, now, config = outbox(scenario)
    with sessions() as db:
        notice = db.scalar(select(Notification).where(Notification.user_id == owner))
        notification_service.update(db, notice.id, "read", owner)
        assert notice.acknowledged_at is not None
    assert DeliveryWorker(sessions, config, now=lambda: now).once()
    with sessions() as db:
        assert db.scalar(select(NotificationDelivery)).status == "cancelled"


def test_recipient_is_encrypted_and_confirmed_user_can_enable(
    client, db, users, monkeypatch
):
    from app.api.v1 import notification_preferences as api

    config = email_config()
    monkeypatch.setattr(api, "get_settings", lambda: config)
    monkeypatch.setattr(api, "confirmed_email", lambda *a: "verified@example.test")
    assert (
        client.put(
            "/api/v1/notification-preferences", json={"email_enabled": True}
        ).status_code
        == 200
    )
    pref = db.get(NotificationPreference, users[0].id)
    assert (
        pref.email_enabled and "verified@example.test" not in pref.encrypted_recipient
    )
    assert (
        client.put(
            "/api/v1/notification-preferences", json={"email_enabled": False}
        ).status_code
        == 200
    )
    db.refresh(pref)
    assert not pref.email_enabled and pref.encrypted_recipient is None


def test_email_transport_errors_are_private_and_permanent_auth_failure():
    config = email_config()
    transport = httpx.MockTransport(
        lambda _: httpx.Response(401, json={"private": "provider-secret"})
    )
    with pytest.raises(ProviderError) as error:
        EmailChannel(config, transport=transport).send(
            {"text": "safe fixture"}, uuid4()
        )
    assert error.value.code == "PERMISSION_DENIED" and not error.value.retryable
    assert "provider-secret" not in str(error.value)


def test_manual_evidence_wakes_existing_job_without_external_provider(scenario):
    from app.schemas.evidence import EvidenceCreate
    from app.services import evidence_service

    sessions, (owner, eid, jid, now) = scenario
    with sessions() as db:
        db.get(MonitoringJob, jid).next_run_at = now + timedelta(days=1)
        db.commit()
        evidence_service.add_evidence(
            db,
            eid,
            EvidenceCreate(
                source="utility_bill",
                metric="total_cost",
                value={"amount": 162},
                observed_at=now,
                confidence=1,
            ),
            owner,
        )
    assert Worker(monitoring.settings(), sessions).run_once(
        now=now + timedelta(seconds=5)
    )
    with sessions() as db:
        assert db.scalar(select(Evaluation)).result.value == "MISMATCH"
        assert db.scalar(select(func.count()).select_from(Notification)) == 1


def test_round_started_before_deadline_needs_post_deadline_incremental_sync(
    scenario, monkeypatch
):
    data = source(scenario, monkeypatch)
    sessions, _, eid, _, now, *_ = data
    with sessions() as db:
        db.get(Expectation, eid).deadline = now + timedelta(minutes=1)
        db.commit()
    assert synchronizer(data, [], complete=False).once()
    assert synchronizer(data, [], clock=lambda: now + timedelta(minutes=2)).once()
    assert Worker(data[-1], sessions).run_once(now=now + timedelta(minutes=2))
    assert results(data)[0][-1].result.value == "UNKNOWN"
    with sessions() as db:
        db.get(ProviderSyncState, data[5]).next_run_at = now + timedelta(minutes=3)
        db.commit()
    assert synchronizer(
        data, [], full=False, clock=lambda: now + timedelta(minutes=3)
    ).once()
    assert Worker(data[-1], sessions).run_once(now=now + timedelta(minutes=3))
    assert results(data)[0][-1].result.value == "MISMATCH"


def test_new_migration_metadata_rls_and_guarded_rollback(scenario):
    from pathlib import Path

    from alembic.autogenerate import compare_metadata
    from alembic.config import Config
    from alembic.migration import MigrationContext
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    from alembic import command
    from app.db.base import Base

    sessions, (owner, eid, _, _) = scenario
    with sessions() as db:
        notification_service.notice(
            db,
            db.get(Expectation, eid),
            "connection_warning",
            "Source needs attention.",
            "rollback-fixture",
        )
        db.commit()
        engine = db.get_bind()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    with pytest.raises(DBAPIError), engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "9b635da2e034")
    with engine.begin() as connection:
        assert (
            connection.scalar(text("SELECT version_num FROM alembic_version"))
            == "d6a71c9e24f0"
        )
        assert (
            compare_metadata(MigrationContext.configure(connection), Base.metadata)
            == []
        )
        for name in ("notification_preferences", "notification_deliveries"):
            assert connection.scalar(
                text(
                    "SELECT relrowsecurity FROM pg_class WHERE oid = to_regclass(:table)"
                ),
                {"table": "public." + name},
            )
    with sessions() as db:
        assert (
            db.scalar(select(Notification).where(Notification.user_id == owner))
            is not None
        )


def test_shipping_date_comparison_uses_selected_source_timezone(scenario):
    from datetime import datetime

    sessions, (owner, eid, _, _) = scenario
    with sessions() as db:
        exp = db.get(Expectation, eid)
        exp.metric = "delivery_reported"
        exp.deadline = datetime(
            2026, 10, 17, 4, 0, tzinfo=timezone.utc
        )  # Friday 11 PM Chicago
        notification_service.delivery_estimate_warning(
            db,
            exp,
            {"revised_delivery_date": "2026-10-17", "order_id": "123-1234567-1234567"},
            "fixture",
            exp.created_at,
            timezone="America/Chicago",
        )
        db.commit()
        assert (
            db.scalar(select(Notification).where(Notification.user_id == owner)).type
            == "potential_delivery_delay"
        )
    with pytest.raises(ValueError):
        SourceRule(kind="calendar", event_id="event1", timezone="invalid-zone")


def test_corrupt_encrypted_recipient_is_a_safe_dead_letter(scenario):
    sessions, owner, _, now, config = outbox(scenario)
    with sessions() as db:
        db.get(NotificationPreference, owner).encrypted_recipient = "corrupt"
        db.commit()
    assert DeliveryWorker(sessions, config, now=lambda: now).once()
    with sessions() as db:
        item = db.scalar(select(NotificationDelivery))
        assert item.status == "failed" and item.last_error == "CREDENTIAL_UNAVAILABLE"


def test_new_authenticated_routes_deny_missing_auth_and_other_user_history(
    client, db, users
):
    from app.api.dependencies import get_current_user
    from app.core.exceptions import AuthenticationError
    from app.main import app

    client.put("/api/v1/notification-preferences", json={"deadline_enabled": True})
    saved = app.dependency_overrides[get_current_user]
    try:
        app.dependency_overrides[get_current_user] = lambda: users[1]
        assert not client.get("/api/v1/notification-preferences").json()[
            "deadline_enabled"
        ]
        assert (
            client.get("/api/v1/notification-preferences/delivery-history").json() == []
        )

        def denied():
            raise AuthenticationError()

        app.dependency_overrides[get_current_user] = denied
        assert client.get("/api/v1/notification-preferences").status_code == 401
        assert (
            client.get("/api/v1/notification-preferences/delivery-history").status_code
            == 401
        )
    finally:
        app.dependency_overrides[get_current_user] = saved


def test_email_configuration_is_opt_in_and_requires_private_backend_settings():
    config = monitoring.settings()
    assert config.notification_email_enabled is False
    assert config.notification_email_api_key is None
    with pytest.raises(ValueError):
        monitoring.settings(notification_email_enabled=True)


def test_older_calendar_update_cannot_undo_newer_cancellation(scenario, monkeypatch):
    data = source(
        scenario,
        monkeypatch,
        metric="event_not_cancelled",
        kind="calendar",
        deadline=False,
    )
    now = data[4]
    cancelled = calendar_facts(
        provider.calendar(status="cancelled", updated=now.isoformat()), "google"
    )
    assert synchronizer(data, [("event1", cancelled)]).once()
    assert Worker(data[-1], data[0]).run_once(now=now)
    with data[0]() as db:
        db.get(ProviderSyncState, data[5]).next_run_at = now
        db.commit()
    older = calendar_facts(
        provider.calendar(updated=(now - timedelta(hours=1)).isoformat()), "google"
    )
    assert synchronizer(
        data, [("event1", older)], clock=lambda: now + timedelta(seconds=10)
    ).once()
    assert Worker(data[-1], data[0]).run_once(now=now + timedelta(seconds=10))
    assert results(data)[0][-1].result.value == "MISMATCH"
    assert len(results(data)[1]) == 1


def test_email_verification_outage_does_not_invalidate_valid_session(monkeypatch):
    from app.api.v1 import notification_preferences as api

    config = email_config()
    config.supabase_url, config.supabase_publishable_key = (
        "https://auth.test",
        "fixture",
    )
    original = httpx.Client
    monkeypatch.setattr(
        api.httpx,
        "Client",
        lambda **kwargs: original(
            transport=httpx.MockTransport(lambda _: httpx.Response(503, json={})),
            **kwargs,
        ),
    )
    with pytest.raises(ProviderError) as error:
        api.confirmed_email(config, "Bearer fixture", uuid4())
    assert error.value.retryable and error.value.code == "PROVIDER_UNAVAILABLE"


def test_late_sync_discovery_of_on_time_reply_replaces_absence_and_closes_alert(
    scenario, monkeypatch
):
    data = source(scenario, monkeypatch)
    now = data[4]
    assert synchronizer(data, []).once()
    assert Worker(data[-1], data[0]).run_once(now=now)
    assert results(data)[0][-1].result.value == "MISMATCH"
    with data[0]() as db:
        db.get(ProviderSyncState, data[5]).next_run_at = now
        db.commit()
    reply = mail_facts(provider.gmail(now=now - timedelta(minutes=10)), "google")
    assert synchronizer(
        data, [("mail1", reply)], full=False, clock=lambda: now + timedelta(minutes=1)
    ).once()
    assert Worker(data[-1], data[0]).run_once(now=now + timedelta(minutes=1))
    evaluations, notices = results(data)
    assert evaluations[-1].result.value == "MATCH"
    assert len(notices) == 1 and notices[0].status == "dismissed"
    assert (
        notices[0].acknowledged_at is None
    )  # system resolution isn't user acknowledgement


def test_mail_revision_replaces_old_version_at_same_received_timestamp(
    scenario, monkeypatch
):
    data = source(
        scenario, monkeypatch, metric="total_cost", kind="bill", deadline=False
    )
    sessions, _, eid, _, now, *_ = data
    with sessions() as db:
        exp = db.get(Expectation, eid)
        exp.type, exp.comparison, exp.baseline = (
            "numeric_comparison",
            "less_than",
            142.1,
        )
        db.commit()
    first = mail_facts(
        provider.gmail(now=now - timedelta(minutes=1), historyId="100"), "google"
    )
    assert synchronizer(data, [("mail1", first)]).once()
    assert Worker(data[-1], sessions).run_once(now=now)
    with sessions() as db:
        db.get(ProviderSyncState, data[5]).next_run_at = now
        db.commit()
    revised = mail_facts(
        provider.gmail(
            now=now - timedelta(minutes=1), text="Total due: $130.00", historyId="101"
        ),
        "google",
    )
    assert synchronizer(
        data, [("mail1", revised)], full=False, clock=lambda: now + timedelta(minutes=1)
    ).once()
    assert Worker(data[-1], sessions).run_once(now=now + timedelta(minutes=1))
    assert results(data)[0][-1].result.value == "MATCH"
    assert results(data)[0][-1].observed["value"] == 130


def test_malformed_provider_headers_cannot_become_absence():
    message = provider.gmail()
    message["payload"]["headers"] = []
    with pytest.raises(ProviderError) as error:
        mail_facts(message, "google")
    assert error.value.code == "PROVIDER_RESPONSE_INVALID" and not error.value.retryable


@pytest.mark.parametrize("late_reply", [False, True])
def test_first_scan_after_capture_cannot_retroactively_prove_no_reply(
    scenario, monkeypatch, late_reply
):
    data = source(scenario, monkeypatch)
    with data[0]() as db:
        sync = db.get(ProviderSyncState, data[5])
        sync.encrypted_checkpoint = None
        sync.coverage_start_at = sync.coverage_through_at = sync.last_success_at = None
        db.commit()
    events = (
        [("mail1", mail_facts(provider.gmail(now=data[4]), "google"))]
        if late_reply
        else []
    )
    assert synchronizer(data, events, full=True).once()
    assert Worker(data[-1], data[0]).run_once(now=data[4])
    row = results(data)[0][-1]
    assert (
        row.result.value == "UNKNOWN"
        and row.reasoning["reason"] == "incomplete_mailbox_coverage"
    )
    assert not any(n.type == "expectation_mismatch" for n in results(data)[1])


def test_forged_provider_value_cannot_override_authorized_projection(
    scenario, monkeypatch
):
    from app.monitoring.sources import wake

    data = source(
        scenario, monkeypatch, metric="total_cost", kind="bill", deadline=False
    )
    with data[0]() as db:
        exp = db.get(Expectation, data[2])
        exp.type, exp.comparison, exp.baseline = (
            "numeric_comparison",
            "less_than",
            142.1,
        )
        db.commit()
    facts = mail_facts(provider.gmail(now=data[4]), "google")
    assert synchronizer(data, [("mail1", facts)]).once()
    with data[0]() as db:
        genuine = db.scalar(select(Evidence).where(Evidence.expectation_id == data[2]))
        db.add(
            Evidence(
                expectation_id=data[2],
                source=genuine.source,
                metric=genuine.metric,
                observed_at=genuine.observed_at,
                value={"amount": 130},
                unit="USD",
                confidence=0.8,
                raw_data=dict(genuine.raw_data),
            )
        )
        wake(db, db.get(Expectation, data[2]), data[4])
        db.commit()
    assert Worker(data[-1], data[0]).run_once(now=data[4])
    row = results(data)[0][-1]
    assert (
        row.result.value == "UNKNOWN"
        and row.reasoning["reason"] == "provider_evidence_not_grounded"
    )
    assert not any(n.type == "expectation_mismatch" for n in results(data)[1])
