"""Explicit cross-provider identifiers, chronology, authority and SQL deduplication."""

from datetime import timedelta

import pytest

from app.db.models import Expectation, MonitoringJob, ProviderSyncState
from app.integrations.normalization import calendar_facts, mail_facts
from app.monitoring.worker import Worker
from app.schemas.provider_sync import BindingCreate, SourceRule
from app.services import provider_sync_service
from tests import test_automatic_tracking as tracking
from tests import test_provider_sync as provider

monitoring_sessions = tracking.monitoring_sessions
scenario = tracking.scenario
UID = "meeting@fixture.test"


def setup(scenario, monkeypatch, peer_kind="calendar"):
    data = tracking.source(
        scenario,
        monkeypatch,
        metric="event_not_cancelled",
        kind="calendar",
        deadline=False,
    )
    with data[0]() as db:
        primary = SourceRule(kind="calendar", event_id="event1", calendar_uid=UID)
        provider_sync_service.bind(
            db, data[2], data[1], BindingCreate(sync_id=data[5], rule=primary)
        )
        conn, oauth, _ = provider.connect(db, data[1], "microsoft", peer_kind, data[4])
        sync = ProviderSyncState(
            connection_id=conn.id,
            user_id=data[1],
            stream="calendar2" if peer_kind == "calendar" else "inbox",
            next_run_at=data[4],
        )
        db.add(sync)
        db.commit()
        rule = (
            SourceRule(kind="calendar", event_id="event2", calendar_uid=UID)
            if peer_kind == "calendar"
            else SourceRule(
                kind="commitment",
                sender="bills@example.test",
                thread_id="thread1",
                calendar_uid=UID,
            )
        )
        provider_sync_service.bind(
            db, data[2], data[1], BindingCreate(sync_id=sync.id, rule=rule)
        )
        db.get(ProviderSyncState, data[5]).next_run_at = data[4] - timedelta(seconds=1)
        sync.next_run_at = data[4]
        db.commit()
        peer = (*data[:5], sync.id, conn.id, oauth, data[-1])
    return data, peer


def cal(data, cancelled=False, uid=UID):
    return calendar_facts(
        provider.calendar(
            status="cancelled" if cancelled else "confirmed",
            iCalUID=uid,
            updated=data[4].isoformat(),
        ),
        "google",
    )


def run(data, peer, primary, secondary):
    assert tracking.synchronizer(data, [("event1", primary)]).once()
    assert tracking.synchronizer(
        peer, [("event2" if secondary["kind"] == "calendar" else "mail1", secondary)]
    ).once()
    assert Worker(data[-1], data[0]).run_once(now=data[4] + timedelta(minutes=1))
    return tracking.results(data)


def test_correlated_google_microsoft_cancellation_one_notification(
    scenario, monkeypatch
):
    data, peer = setup(scenario, monkeypatch)
    evaluations, notices = run(data, peer, cal(data, True), cal(data, True))
    result = evaluations[-1]
    assert (
        result.result.value == "MISMATCH" and len(result.reasoning["evidence_ids"]) == 2
    )
    assert len(notices) == 1
    with data[0]() as db:
        assert db.get(Expectation, data[2]).status.value == "contradicted"
        db.get(MonitoringJob, data[3]).next_run_at = data[4]
        db.commit()
    assert Worker(data[-1], data[0]).run_once(now=data[4] + timedelta(minutes=2))
    assert len(tracking.results(data)[1]) == 1


def test_current_calendars_conflict_never_pick_a_winner(scenario, monkeypatch):
    data, peer = setup(scenario, monkeypatch)
    evaluations, notices = run(data, peer, cal(data), cal(data, True))
    assert evaluations[-1].result.value == "UNKNOWN"
    assert evaluations[-1].reasoning["reason"] == "conflicting_evidence" and not notices


@pytest.mark.parametrize("peer_cancelled", [False, True])
def test_two_different_reschedules_are_unknown_even_when_both_mismatch(
    scenario, monkeypatch, peer_cancelled
):
    from sqlalchemy import select

    from app.db.models import ExpectationSourceBinding

    data, peer = setup(scenario, monkeypatch)
    with data[0]() as db:
        db.get(Expectation, data[2]).metric = "event_unchanged"
        for binding in db.scalars(select(ExpectationSourceBinding)):
            binding.rule = {
                **binding.rule,
                "expected_start": (data[4] + timedelta(days=5)).isoformat(),
            }
        db.commit()
    primary, secondary = cal(data), cal(data)
    secondary["start"] = (data[4] + timedelta(days=3)).isoformat()
    secondary["cancelled"] = peer_cancelled
    evaluations, notices = run(data, peer, primary, secondary)
    assert evaluations[-1].result.value == "UNKNOWN"
    assert evaluations[-1].reasoning["reason"] == "conflicting_evidence" and not notices


def test_old_email_reference_cannot_override_new_calendar(scenario, monkeypatch):
    data, peer = setup(scenario, monkeypatch, "email")
    facts = mail_facts(
        provider.gmail(
            now=data[4] - timedelta(hours=1),
            text=f"Appointment confirmed\nCalendar UID: {UID}",
        ),
        "google",
    )
    evaluations, notices = run(data, peer, cal(data, True), facts)
    assert evaluations[-1].result.value == "MISMATCH" and len(notices) == 1
    assert len(evaluations[-1].reasoning["authoritative_evidence_ids"]) == 1


def test_newer_contradictory_email_requires_reconciliation(scenario, monkeypatch):
    data, peer = setup(scenario, monkeypatch, "email")
    facts = mail_facts(
        provider.gmail(
            now=data[4] + timedelta(seconds=5),
            text=f"Appointment cancelled\nCalendar UID: {UID}",
        ),
        "google",
    )
    evaluations, notices = run(data, peer, cal(data), facts)
    assert evaluations[-1].result.value == "UNKNOWN" and not notices


@pytest.mark.parametrize("impairment", ["wrong_uid", "disconnected", "stale"])
def test_cross_provider_missing_permissions_or_identity_abstains(
    scenario, monkeypatch, impairment
):
    from app.db.models.integration import IntegrationConnection

    data, peer = setup(scenario, monkeypatch)
    evaluations, _ = run(
        data,
        peer,
        cal(data),
        cal(data, uid="foreign-event" if impairment == "wrong_uid" else UID),
    )
    if impairment != "wrong_uid":
        with data[0]() as db:
            if impairment == "disconnected":
                db.get(IntegrationConnection, peer[6]).status = "disconnected"
            else:
                db.get(ProviderSyncState, peer[5]).last_success_at = data[
                    4
                ] - timedelta(days=3)
            db.get(MonitoringJob, data[3]).next_run_at = data[4]
            db.commit()
        assert Worker(data[-1], data[0]).run_once(now=data[4] + timedelta(minutes=2))
        evaluations, _ = tracking.results(data)
    assert evaluations[-1].result.value == "UNKNOWN"


def test_order_estimate_update_across_providers_is_warning_not_verdict(
    scenario, monkeypatch
):
    data = tracking.source(
        scenario, monkeypatch, metric="package_delivery", kind="order", deadline=False
    )
    order = "123-1234567-1234567"
    with data[0]() as db:
        exp = db.get(Expectation, data[2])
        exp.type = "temporal"
        exp.deadline = data[4] + timedelta(days=1)
        conn, oauth, _ = provider.connect(db, data[1], "microsoft", "email", data[4])
        sync = ProviderSyncState(
            connection_id=conn.id, user_id=data[1], stream="inbox", next_run_at=data[4]
        )
        db.add(sync)
        db.commit()
        provider_sync_service.bind(
            db,
            exp.id,
            data[1],
            BindingCreate(
                sync_id=sync.id,
                rule=SourceRule(
                    kind="order",
                    sender="bills@example.test",
                    thread_id="thread1",
                    order_id=order,
                ),
            ),
        )
        db.get(ProviderSyncState, data[5]).next_run_at = data[4] - timedelta(seconds=1)
        sync.next_run_at = data[4]
        db.commit()
        peer = (*data[:5], sync.id, conn.id, oauth, data[-1])
    estimated = mail_facts(
        provider.gmail(
            now=data[4],
            text=f"Order {order} has shipped. Expected delivery: {data[4].date().isoformat()}",
        ),
        "google",
    )
    revised = mail_facts(
        provider.gmail(
            now=data[4],
            text=f"Order {order} has shipped. Revised delivery: {(data[4] + timedelta(days=3)).date().isoformat()}",
        ),
        "google",
    )
    assert tracking.synchronizer(data, [("mail1", estimated)]).once()
    assert tracking.synchronizer(peer, [("mail2", revised)]).once()
    assert Worker(data[-1], data[0]).run_once(now=data[4] + timedelta(minutes=1))
    evaluations, notices = tracking.results(data)
    assert evaluations[-1].result.value == "UNKNOWN"
    assert len(notices) == 1 and notices[0].type == "potential_delivery_delay"
    assert notices[0].notification_metadata["certainty"] == "predicted"
    with data[0]() as db:
        db.get(ProviderSyncState, peer[5]).next_run_at = data[4]
        db.commit()
    assert tracking.synchronizer(peer, [("mail2", revised)], full=False).once()
    assert len(tracking.results(data)[1]) == 1


@pytest.mark.parametrize("metric", ["package_delivery", "delivery_reported"])
@pytest.mark.parametrize("both_late", [False, True])
def test_conflicting_delivery_reports_never_choose_later_arrival(
    scenario, monkeypatch, metric, both_late
):
    data = tracking.source(
        scenario, monkeypatch, metric=metric, kind="order", deadline=False
    )
    order = "123-1234567-1234567"
    with data[0]() as db:
        exp = db.get(Expectation, data[2])
        exp.type = "temporal"
        exp.deadline = data[4] - timedelta(hours=1)
        conn, oauth, _ = provider.connect(db, data[1], "microsoft", "email", data[4])
        sync = ProviderSyncState(
            connection_id=conn.id, user_id=data[1], stream="inbox", next_run_at=data[4]
        )
        db.add(sync)
        db.commit()
        provider_sync_service.bind(
            db,
            exp.id,
            data[1],
            BindingCreate(
                sync_id=sync.id,
                rule=SourceRule(
                    kind="order", sender="bills@example.test", order_id=order
                ),
            ),
        )
        db.get(ProviderSyncState, data[5]).next_run_at = data[4] - timedelta(seconds=1)
        sync.next_run_at = data[4]
        db.commit()
        peer = (*data[:5], sync.id, conn.id, oauth, data[-1])
    early = data[4] - timedelta(minutes=45 if both_late else 90)
    late = data[4] - timedelta(minutes=15)
    for source_data, external, arrived in (
        (data, "mail1", early),
        (peer, "mail2", late),
    ):
        facts = mail_facts(
            provider.gmail(
                now=data[4],
                text=f"Order {order} was delivered. Delivered at: {arrived.isoformat()}",
            ),
            "google",
        )
        assert tracking.synchronizer(source_data, [(external, facts)]).once()
    assert Worker(data[-1], data[0]).run_once(now=data[4] + timedelta(minutes=1))
    evaluations, notices = tracking.results(data)
    assert evaluations[-1].result.value == "UNKNOWN"
    assert evaluations[-1].reasoning["reason"] == "conflicting_evidence"
    assert not notices
