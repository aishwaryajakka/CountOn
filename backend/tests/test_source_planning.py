"""Rules-first planning, explicit permission/confirmation and real SQL workers."""

from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, func, select

from app.core.exceptions import ExpectationNotFoundError, InvalidExpectationError
from app.db.models import (
    Expectation,
    ExpectationSourceBinding,
    MonitoringJob,
    ProviderSourceEvent,
    ProviderSyncState,
)
from app.db.models.integration import IntegrationConnection
from app.integrations.normalization import calendar_facts, mail_facts, version
from app.monitoring.worker import Worker
from app.schemas.source_plan import (
    ConfirmMonitoringPlan,
    SourceChoice,
    SourcePlanRequest,
)
from app.services import source_planning_service as planner
from tests import test_automatic_tracking as tracking
from tests import test_provider_sync as provider

monitoring_sessions = tracking.monitoring_sessions
scenario = tracking.scenario


def prepared(scenario, monkeypatch, *, metric="delivery_reported", kind="order"):
    data = tracking.source(
        scenario, monkeypatch, metric=metric, kind=kind, deadline=False
    )
    with data[0]() as db:
        db.execute(
            delete(ExpectationSourceBinding).where(
                ExpectationSourceBinding.expectation_id == data[2]
            )
        )
        if metric in ("delivery_reported", "package_delivery"):
            db.get(Expectation, data[2]).deadline = data[4] + timedelta(hours=1)
        if metric == "package_delivery":
            db.get(Expectation, data[2]).type = "temporal"
        db.commit()
    return data


def fixture_order(data, order="123-1234567-1234567", when=None):
    return mail_facts(
        provider.gmail(
            now=when or data[4],
            text=f"Order {order} was delivered. Delivered at: {(when or data[4]).isoformat()}",
        ),
        "google",
    )


def preview(data, query=None):
    with data[0]() as db:
        return planner.preview(
            db, data[-1], data[2], data[1], query or SourcePlanRequest(), now=data[4]
        )


def confirm(data, plan, query=None):
    body = ConfirmMonitoringPlan(
        confirmed=True,
        query=query or SourcePlanRequest(),
        sources=[
            SourceChoice(sync_id=c.sync_id, external_id=c.external_id)
            for c in plan.candidates
        ],
    )
    with data[0]() as db:
        return planner.apply(db, data[-1], data[2], data[1], body)


@pytest.mark.parametrize("metric", ["delivery_reported", "package_delivery"])
def test_plan_confirm_schedules_exactly_once(scenario, monkeypatch, metric):
    data = prepared(scenario, monkeypatch, metric=metric)
    assert tracking.synchronizer(data, [("mail1", fixture_order(data))]).once()
    plan = preview(data)
    assert (
        plan.status == "ready" and len(plan.candidates) == 1 and plan.bedrock_calls == 0
    )
    with data[0]() as db:
        assert (
            db.scalar(select(func.count()).select_from(ExpectationSourceBinding)) == 0
        )
    applied = confirm(data, plan)
    with data[0]() as db:
        run = db.get(MonitoringJob, applied.job_id).run_key
    assert confirm(data, preview(data)).job_id == applied.job_id
    with data[0]() as db:
        assert db.get(MonitoringJob, applied.job_id).run_key == run
        assert (
            db.scalar(select(func.count()).select_from(ExpectationSourceBinding)) == 1
        )
        db.get(ProviderSyncState, data[5]).next_run_at = data[4]
        db.commit()
    assert tracking.synchronizer(data, [("mail1", fixture_order(data))]).once()
    assert Worker(data[-1], data[0]).run_once(now=data[4] + timedelta(seconds=1))
    assert tracking.results(data)[0][-1].result.value == "MATCH"


def test_multiple_orders_ask_one_question_and_narrow_by_identifier(
    scenario, monkeypatch
):
    data = prepared(scenario, monkeypatch)
    assert tracking.synchronizer(
        data,
        [("a", fixture_order(data)), ("b", fixture_order(data, "987-7654321-1234567"))],
    ).once()
    plan = preview(data)
    assert plan.status == "clarification" and "Which order" in plan.question
    with pytest.raises(InvalidExpectationError):
        confirm(data, plan)
    narrowed = preview(data, SourcePlanRequest(order_id="123-1234567-1234567"))
    assert narrowed.status == "ready" and len(narrowed.candidates) == 1


def test_order_plan_does_not_pin_future_shipping_updates_to_original_thread(
    scenario, monkeypatch
):
    data = prepared(scenario, monkeypatch)
    assert tracking.synchronizer(data, [("mail1", fixture_order(data))]).once()
    plan = preview(data)
    assert plan.candidates[0].rule.thread_id is None
    applied = confirm(data, plan)
    with data[0]() as db:
        db.get(MonitoringJob, applied.job_id).status = "failed"
        db.commit()
    assert (
        confirm(data, plan).status == "failed"
    )  # replay cannot silently reset a dead letter


@pytest.mark.parametrize("failure", ["revoked", "stale", "credential_missing"])
def test_unavailable_source_cannot_confirm_old_plan(scenario, monkeypatch, failure):
    from app.db.models.integration import IntegrationCredential

    data = prepared(scenario, monkeypatch)
    assert tracking.synchronizer(data, [("mail1", fixture_order(data))]).once()
    plan = preview(data)
    with data[0]() as db:
        if failure == "revoked":
            db.get(IntegrationConnection, data[6]).status = "disconnected"
        elif failure == "stale":
            db.get(ProviderSyncState, data[5]).last_success_at = data[4] - timedelta(
                days=2
            )
        else:
            db.delete(db.get(IntegrationCredential, data[6]))
        db.commit()
    with pytest.raises(InvalidExpectationError):
        confirm(data, plan)


def test_no_accounts_and_other_users_never_invent_sources(scenario, monkeypatch):
    data = prepared(scenario, monkeypatch)
    with data[0]() as db:
        db.get(IntegrationConnection, data[6]).status = "disconnected"
        db.commit()
        plan = planner.preview(db, data[-1], data[2], data[1], SourcePlanRequest())
        assert plan.status == "permission_required" and not plan.candidates
        with pytest.raises(ExpectationNotFoundError):
            planner.preview(db, data[-1], data[2], uuid4(), SourcePlanRequest())


def test_calendar_requires_actual_baseline_and_selects_owned_instance(
    scenario, monkeypatch
):
    data = prepared(scenario, monkeypatch, metric="event_unchanged", kind="calendar")
    facts = calendar_facts(provider.calendar(iCalUID="meeting@fixture.test"), "google")
    assert tracking.synchronizer(data, [("event1", facts)]).once()
    assert preview(data).question == "What exact start time should stay unchanged?"
    plan = preview(data, SourcePlanRequest(expected_start=facts["start"]))
    assert (
        plan.status == "ready"
        and plan.candidates[0].rule.calendar_uid == "meeting@fixture.test"
    )


def test_bounded_search_abstains_instead_of_guessing(scenario, monkeypatch):
    data = prepared(scenario, monkeypatch)
    with data[0]() as db:
        sync = db.get(ProviderSyncState, data[5])
        sync.last_success_at = data[4]
        facts = fixture_order(data)
        for i in range(201):
            db.add(
                ProviderSourceEvent(
                    sync_id=sync.id,
                    user_id=data[1],
                    external_id=str(i),
                    version=version(facts),
                    encrypted_facts=data[7].encrypt(facts, sync.id),
                    observed_at=data[4],
                    seen_round=sync.round_id,
                )
            )
        db.commit()
    assert preview(data).status == "bounded" and not preview(data).candidates


@pytest.mark.parametrize("value", [False, 1, "true", None])
def test_plan_requires_explicit_true_and_forbids_identity(value):
    with pytest.raises(ValidationError):
        ConfirmMonitoringPlan.model_validate(
            {
                "confirmed": value,
                "sources": [{"sync_id": str(uuid4()), "external_id": "event"}],
            }
        )
    with pytest.raises(ValidationError):
        SourcePlanRequest.model_validate({"user_id": str(uuid4())})


def test_owned_plan_api_requires_auth_and_ignores_no_client_identity(
    scenario, monkeypatch
):
    from fastapi.testclient import TestClient

    from app.api import dependencies
    from app.core.auth import AuthenticatedUser
    from app.main import app

    data = prepared(scenario, monkeypatch)

    def db_dependency():
        with data[0]() as db:
            yield db

    app.dependency_overrides[dependencies.get_db] = db_dependency
    try:
        with TestClient(app) as client:
            path = f"/api/v1/expectations/{data[2]}/monitoring-plan/preview"
            assert client.post(path, json={}).status_code == 401
            app.dependency_overrides[dependencies.get_current_user] = lambda: (
                AuthenticatedUser(id=data[1])
            )
            assert client.post(path, json={"user_id": str(uuid4())}).status_code == 422
            assert client.post(path, json={}).status_code == 200
            app.dependency_overrides[dependencies.get_current_user] = lambda: (
                AuthenticatedUser(id=uuid4())
            )
            assert client.post(path, json={}).status_code == 404
    finally:
        app.dependency_overrides.clear()


def test_concurrent_plan_confirmations_do_not_duplicate_bindings(scenario, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    data = prepared(scenario, monkeypatch)
    assert tracking.synchronizer(data, [("mail1", fixture_order(data))]).once()
    plan = preview(data)
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: confirm(data, plan), range(2)))
    assert outcomes[0].job_id == outcomes[1].job_id
    with data[0]() as db:
        assert (
            db.scalar(select(func.count()).select_from(ExpectationSourceBinding)) == 1
        )


def test_multi_source_plan_rolls_back_all_bindings_on_failure(scenario, monkeypatch):
    data = prepared(scenario, monkeypatch)
    facts = fixture_order(data)
    assert tracking.synchronizer(data, [("mail1", facts)]).once()
    with data[0]() as db:
        connection, crypto, _ = provider.connect(
            db, data[1], "microsoft", "email", data[4]
        )
        sync = ProviderSyncState(
            connection_id=connection.id,
            user_id=data[1],
            stream="inbox",
            last_success_at=data[4],
            next_run_at=data[4],
        )
        db.add(sync)
        db.flush()
        db.add(
            ProviderSourceEvent(
                sync_id=sync.id,
                user_id=data[1],
                external_id="mail2",
                version=version(facts),
                encrypted_facts=crypto.encrypt(facts, sync.id),
                observed_at=data[4],
                seen_round=sync.round_id,
            )
        )
        db.commit()
    plan = preview(data)
    assert len(plan.candidates) == 2
    original, attempts = planner.provider_sync_service.bind, [0]

    def interrupted(*args, **kwargs):
        attempts[0] += 1
        if attempts[0] == 2:
            raise RuntimeError("synthetic interrupted confirmation")
        return original(*args, **kwargs)

    monkeypatch.setattr(planner.provider_sync_service, "bind", interrupted)
    with pytest.raises(RuntimeError):
        confirm(data, plan)
    with data[0]() as db:
        assert (
            db.scalar(select(func.count()).select_from(ExpectationSourceBinding)) == 0
        )


@pytest.mark.parametrize(
    "failure", ["scopes", "expired", "corrupt", "different_account"]
)
def test_plan_rechecks_usable_owned_grant(scenario, monkeypatch, failure):
    from app.db.models.integration import IntegrationCredential

    data = prepared(scenario, monkeypatch)
    assert tracking.synchronizer(data, [("mail1", fixture_order(data))]).once()
    plan = preview(data)
    with data[0]() as db:
        connection = db.get(IntegrationConnection, data[6])
        credential = db.get(IntegrationCredential, data[6])
        if failure == "scopes":
            connection.scopes = []
        elif failure == "different_account":
            connection.external_account_id = "other-account"
        elif failure == "corrupt":
            credential.encrypted_tokens = "invalid-ciphertext"
        else:
            tokens = data[7].decrypt(credential.encrypted_tokens, connection.id)
            tokens.pop("refresh_token")
            credential.encrypted_tokens = data[7].encrypt(tokens, connection.id)
            credential.expires_at = data[4] - timedelta(minutes=1)
        db.commit()
    assert not preview(data).candidates
    with pytest.raises(InvalidExpectationError):
        confirm(data, plan)


@pytest.mark.parametrize("state", ["paused", "cancelled"])
def test_source_confirmation_preserves_explicit_monitoring_stop(
    scenario, monkeypatch, state
):
    data = prepared(scenario, monkeypatch)
    assert tracking.synchronizer(data, [("mail1", fixture_order(data))]).once()
    with data[0]() as db:
        db.get(MonitoringJob, data[3]).status = state
        db.commit()
    assert confirm(data, preview(data)).status == state


def test_stale_session_cannot_confirm_cancelled_expectation(scenario, monkeypatch):
    data = prepared(scenario, monkeypatch)
    assert tracking.synchronizer(data, [("mail1", fixture_order(data))]).once()
    plan = preview(data)
    request = ConfirmMonitoringPlan(
        confirmed=True,
        sources=[
            SourceChoice(
                sync_id=plan.candidates[0].sync_id,
                external_id=plan.candidates[0].external_id,
            )
        ],
    )
    with data[0]() as stale:
        cached = stale.get(Expectation, data[2])
        assert cached.status.value != "cancelled"
        with data[0]() as concurrent:
            concurrent.get(Expectation, data[2]).status = "cancelled"
            concurrent.commit()
        assert cached.status.value != "cancelled"
        with pytest.raises(InvalidExpectationError):
            planner.apply(stale, data[-1], data[2], data[1], request)
        stale.rollback()
    with data[0]() as db:
        assert (
            db.scalar(select(func.count()).select_from(ExpectationSourceBinding)) == 0
        )


def test_wake_rechecks_cancellation_after_loading_old_identity(scenario):
    from app.monitoring.sources import wake

    sessions, (_, eid, jid, now) = scenario
    with sessions() as stale:
        expectation = stale.get(Expectation, eid)
        with sessions() as concurrent:
            concurrent.get(Expectation, eid).status = "cancelled"
            concurrent.get(MonitoringJob, jid).status = "completed"
            concurrent.commit()
        wake(stale, expectation, now)
        stale.commit()
    with sessions() as db:
        assert db.get(MonitoringJob, jid).status == "completed"


def test_confirmation_does_not_reuse_cached_deleted_credentials(scenario, monkeypatch):
    from app.db.models.integration import IntegrationCredential

    data = prepared(scenario, monkeypatch)
    assert tracking.synchronizer(data, [("mail1", fixture_order(data))]).once()
    plan = preview(data)
    request = ConfirmMonitoringPlan(
        confirmed=True,
        sources=[
            SourceChoice(
                sync_id=plan.candidates[0].sync_id,
                external_id=plan.candidates[0].external_id,
            )
        ],
    )
    with data[0]() as stale:
        cached = stale.get(IntegrationCredential, data[6])
        assert cached is not None
        with data[0]() as concurrent:
            concurrent.delete(concurrent.get(IntegrationCredential, data[6]))
            concurrent.commit()
        with pytest.raises(InvalidExpectationError):
            planner.apply(stale, data[-1], data[2], data[1], request)
        stale.rollback()
    with data[0]() as db:
        assert (
            db.scalar(select(func.count()).select_from(ExpectationSourceBinding)) == 0
        )


def test_legacy_poll_worker_locks_account_before_expectation(scenario):
    import threading
    from concurrent.futures import ThreadPoolExecutor

    from sqlalchemy import event

    from app.db.models.integration import IntegrationConnection
    from app.monitoring.worker import claim_due

    sessions, (owner, eid, jid, now) = scenario
    config = provider.settings(monitoring_enabled=True)
    with sessions() as db:
        connection, _, _ = provider.connect(db, owner, "microsoft", "email", now)
        cid = connection.id
        db.get(MonitoringJob, jid).connection_id = cid
        db.commit()
        claim = claim_due(db, config.monitoring_lease_seconds, now=now)
    reached = threading.Event()
    engine = sessions.kw["bind"]

    def before_execute(conn, cursor, statement, parameters, context, executemany):
        if "integration_connections" in statement and "FOR UPDATE" in statement:
            reached.set()

    with sessions() as revocation:
        revocation.scalar(
            select(IntegrationConnection)
            .where(IntegrationConnection.id == cid)
            .with_for_update()
        )
        event.listen(engine, "before_cursor_execute", before_execute)
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(
                    Worker(config, sessions).finish, claim, [], now=now
                )
                try:
                    assert reached.wait(5)
                    # NOWAIT fails if the worker took the inverse lock order.
                    expectation = revocation.scalar(
                        select(Expectation)
                        .where(Expectation.id == eid)
                        .with_for_update(nowait=True)
                    )
                    expectation.status = "cancelled"
                    revocation.commit()
                finally:
                    revocation.rollback()  # releases account on assertion failure
                assert future.result(timeout=5)
        finally:
            event.remove(engine, "before_cursor_execute", before_execute)
    with sessions() as db:
        assert db.get(MonitoringJob, jid).status == "cancelled"
