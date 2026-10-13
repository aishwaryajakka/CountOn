"""Committed worker concurrency data is restricted to a disposable PostgreSQL DB."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.orm import sessionmaker

from alembic import command
from app.core.config import Settings
from app.core.exceptions import ExpectationNotFoundError
from app.db.models import (
    Evaluation,
    Evidence,
    Expectation,
    MonitoringJob,
    Notification,
    Profile,
)
from app.integrations.provider import ProviderError
from app.monitoring.worker import Worker, claim_due
from app.repositories.profile import ensure_profile
from app.schemas.evidence import EvidenceCreate
from app.schemas.expectation import ExpectationCreate
from app.schemas.monitoring import MonitoringSchedule
from app.services import expectation_service, monitoring_service

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def monitoring_sessions(postgres_engine):
    name = f"counton_monitor_{uuid4().hex}_test"
    with postgres_engine.connect().execution_options(
        isolation_level="AUTOCOMMIT"
    ) as admin:
        admin.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_engine(postgres_engine.url.set(database=name), pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield sessionmaker(bind=engine, expire_on_commit=False)
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(
            isolation_level="AUTOCOMMIT"
        ) as admin:
            admin.execute(text(f'DROP DATABASE "{name}"'))


@pytest.fixture
def scenario(monitoring_sessions):
    owner, now = uuid4(), datetime.now(timezone.utc)
    with monitoring_sessions() as db:
        ensure_profile(db, owner)
        item = expectation_service.create_expectation(
            db,
            ExpectationCreate(
                claim="Monitoring fixture",
                type="numeric_comparison",
                metric="total_cost",
                comparison="less_than",
                baseline=142.1,
                evidence_sources=["utility_bill"],
            ),
            owner,
        )
        item.created_at = now - timedelta(hours=2)
        job = db.scalar(
            select(MonitoringJob).where(MonitoringJob.expectation_id == item.id)
        )
        job.next_run_at = job.scheduled_at = now - timedelta(seconds=1)
        db.commit()
        ids = owner, item.id, job.id, now
    try:
        yield monitoring_sessions, ids
    finally:
        with monitoring_sessions() as db:
            db.execute(delete(Profile).where(Profile.id == owner))
            db.commit()


def settings(**changes):
    return Settings(
        _env_file=None,
        database_target="local",
        local_database_url="postgresql+psycopg://fixture@localhost/fixture",
        **changes,
    )


def fact(
    sessions, eid, now, amount=162, offset=-60, source="utility_bill", confidence=1
):
    with sessions() as db:
        row = Evidence(
            expectation_id=eid,
            source=source,
            metric="total_cost",
            value={"amount": amount},
            unit="USD",
            confidence=confidence,
            observed_at=now + timedelta(seconds=offset),
        )
        db.add(row)
        db.commit()
        return row.id


def counts(sessions, eid):
    with sessions() as db:
        return tuple(
            db.scalar(
                select(func.count()).select_from(m).where(m.expectation_id == eid)
            )
            for m in (Evidence, Evaluation, Notification)
        )


def claim(sessions, now):
    with sessions() as db:
        return claim_due(db, 120, now=now)


def test_schedule_repeats_dedupe_and_provenance(scenario):
    sessions, (_, eid, jid, now) = scenario
    identity = fact(sessions, eid, now)
    worker = Worker(settings(), sessions)
    assert worker.run_once(now=now)
    assert not worker.run_once(now=now)
    assert worker.run_once(now=now + timedelta(hours=1))
    assert counts(sessions, eid) == (1, 2, 1)
    with sessions() as db:
        rows = list(
            db.scalars(select(Evaluation).where(Evaluation.expectation_id == eid))
        )
        assert all(
            r.result.value == "MISMATCH"
            and r.reasoning["evidence_ids"] == [str(identity)]
            for r in rows
        )
        assert len({r.idempotency_key for r in rows}) == 2
        assert db.get(MonitoringJob, jid).status == "pending"


def test_multiple_workers_claim_once(scenario):
    sessions, (_, eid, _, _) = scenario
    worker = Worker(settings(), sessions)
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert sum(pool.map(lambda _: worker.run_once(), range(6))) == 1
    assert counts(sessions, eid) == (0, 1, 0)


def test_skip_locked_does_not_wait(scenario):
    sessions, (_, _, jid, now) = scenario
    with sessions() as db:
        db.scalar(
            select(MonitoringJob).where(MonitoringJob.id == jid).with_for_update()
        )
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(claim, sessions, now).result(timeout=2) is None


def test_crash_recovery_and_stale_worker_fencing(scenario):
    sessions, (_, eid, _, now) = scenario
    first = claim(sessions, now)
    assert claim(sessions, now + timedelta(seconds=119)) is None
    second = claim(sessions, now + timedelta(seconds=121))
    assert first.run_key == second.run_key and first.token != second.token
    worker = Worker(settings(), sessions)
    assert not worker.finish(first, [], now=now + timedelta(seconds=122))
    assert worker.finish(second, [], now=now + timedelta(seconds=122))
    assert not worker.finish(second, [], now=now + timedelta(seconds=123))
    assert counts(sessions, eid) == (0, 1, 0)


def test_backoff_retry_after_and_dead_letter(scenario):
    sessions, (_, _, jid, now) = scenario
    with sessions() as db:
        db.get(MonitoringJob, jid).max_attempts = 2
        db.commit()
    worker = Worker(settings(monitoring_backoff_seconds=10), sessions)
    first = claim(sessions, now)
    worker.fail(first, ProviderError("PROVIDER_THROTTLED", retry_after=30), now=now)
    with sessions() as db:
        assert db.get(MonitoringJob, jid).next_run_at == now + timedelta(seconds=30)
    second = claim(sessions, now + timedelta(seconds=30))
    worker.fail(
        second, ProviderError("PROVIDER_UNAVAILABLE"), now=now + timedelta(seconds=31)
    )
    with sessions() as db:
        job = db.get(MonitoringJob, jid)
        assert (job.status, job.attempt_count, job.last_error) == (
            "failed",
            2,
            "PROVIDER_UNAVAILABLE",
        )
    assert claim(sessions, now + timedelta(days=1)) is None


def test_abandoned_leases_exhaust_attempts(scenario):
    sessions, (_, _, jid, now) = scenario
    with sessions() as db:
        db.get(MonitoringJob, jid).max_attempts = 1
        db.commit()
    assert claim(sessions, now)
    assert claim(sessions, now + timedelta(seconds=121)) is None
    with sessions() as db:
        assert db.get(MonitoringJob, jid).status == "failed"


@pytest.mark.parametrize(
    "kind,reason",
    [
        ("missing", "no_relevant_evidence"),
        ("stale", "stale_evidence"),
        ("conflict", "conflicting_evidence"),
        ("future", "future_evidence"),
        ("malformed", "malformed_evidence"),
        ("untrusted", "no_relevant_evidence"),
        ("confidence", "unusable_evidence_confidence"),
    ],
)
def test_evidence_quality_unknown(scenario, kind, reason):
    sessions, (_, eid, jid, now) = scenario
    if kind == "stale":
        with sessions() as db:
            db.get(Expectation, eid).created_at = now - timedelta(days=3)
            db.commit()
        fact(sessions, eid, now, offset=-90000)
    elif kind == "conflict":
        fact(sessions, eid, now, 162)
        fact(sessions, eid, now, 130)
    elif kind == "future":
        fact(sessions, eid, now, offset=60)
    elif kind == "malformed":
        fact(sessions, eid, now, amount="162")
    elif kind == "untrusted":
        fact(sessions, eid, now, source="unapproved")
    elif kind == "confidence":
        fact(sessions, eid, now, confidence=0)
    assert Worker(settings(), sessions).run_once(now=now)
    with sessions() as db:
        row = db.scalar(select(Evaluation).where(Evaluation.expectation_id == eid))
        assert row.result.value == "UNKNOWN" and row.reasoning["reason"] == reason
        assert db.get(Expectation, eid).status.value == "monitoring"
        assert db.get(MonitoringJob, jid).status == "pending"
    assert counts(sessions, eid)[2] == 0


def test_atomic_evidence_evaluation_notification_and_replay(scenario, monkeypatch):
    sessions, (_, eid, _, now) = scenario
    owned = claim(sessions, now)
    payload = EvidenceCreate(
        source="utility_bill",
        metric="total_cost",
        value={"amount": 162},
        unit="USD",
        observed_at=now - timedelta(seconds=10),
        external_event_id="atomic-fixture",
    )
    worker = Worker(settings(), sessions)

    def broken(*a, **k):
        raise RuntimeError("private-token")

    with monkeypatch.context() as patch:
        patch.setattr("app.services.notification_service.for_evaluation", broken)
        with pytest.raises(RuntimeError):
            worker.finish(owned, [payload], now=now)
    assert counts(sessions, eid) == (0, 0, 0)
    assert worker.finish(owned, [payload], now=now)
    assert counts(sessions, eid) == (1, 1, 1)
    assert not worker.finish(owned, [payload], now=now)


def test_pause_requeue_and_ownership(scenario):
    sessions, (owner, eid, _, now) = scenario
    worker = Worker(settings(), sessions)
    stale = claim(sessions, now)
    with sessions() as db:
        with pytest.raises(ExpectationNotFoundError):
            monitoring_service.get(db, eid, uuid4())
        db.rollback()
        monitoring_service.configure(
            db, eid, owner, MonitoringSchedule(next_run_at=now, status="paused")
        )
    assert not worker.finish(stale, [], now=now)
    assert not worker.run_once(now=now)
    with sessions() as db:
        monitoring_service.configure(
            db, eid, owner, MonitoringSchedule(next_run_at=now)
        )
    assert worker.run_once(now=now)


def test_match_completes_one_shot(scenario):
    sessions, (_, eid, jid, now) = scenario
    fact(sessions, eid, now, 130)
    assert Worker(settings(), sessions).run_once(now=now)
    with sessions() as db:
        assert db.get(MonitoringJob, jid).status == "completed"
        assert db.get(Expectation, eid).status.value == "fulfilled"


def test_recurring_window_excludes_previous_period(scenario):
    sessions, (owner, eid, jid, now) = scenario
    fact(sessions, eid, now, 130)
    with sessions() as db:
        monitoring_service.configure(
            db,
            eid,
            owner,
            MonitoringSchedule(next_run_at=now, interval_seconds=60, recurring=True),
        )
    worker = Worker(settings(), sessions)
    assert worker.run_once(now=now) and worker.run_once(now=now + timedelta(seconds=60))
    with sessions() as db:
        assert db.get(Expectation, eid).status.value == "monitoring"
        assert db.get(MonitoringJob, jid).status == "pending"
        assert {
            r.result.value
            for r in db.scalars(
                select(Evaluation).where(Evaluation.expectation_id == eid)
            )
        } == {"MATCH", "UNKNOWN"}


@pytest.mark.parametrize("offset,result", [(-60, "MATCH"), (60, "MISMATCH")])
def test_temporal_occurrence(scenario, offset, result):
    sessions, (_, eid, _, now) = scenario
    with sessions() as db:
        item = db.get(Expectation, eid)
        item.type = "temporal"
        item.metric = "delivered"
        item.deadline = now - timedelta(minutes=2)
        db.add(
            Evidence(
                expectation_id=eid,
                source="utility_bill",
                metric="delivered",
                value={"value": True},
                observed_at=item.deadline + timedelta(seconds=offset),
            )
        )
        db.commit()
    assert Worker(settings(), sessions).run_once(now=now)
    with sessions() as db:
        assert (
            db.scalar(
                select(Evaluation).where(Evaluation.expectation_id == eid)
            ).result.value
            == result
        )


def test_http_schedule_ack_and_evaluation_idempotency(
    client, db, numeric_payload, bill_payload
):
    from uuid import UUID

    eid = client.post("/api/v1/expectations", json=numeric_payload).json()["id"]
    path = f"/api/v1/expectations/{eid}"
    assert (
        client.put(
            path + "/monitoring",
            json={
                "next_run_at": datetime.now(timezone.utc).isoformat(),
                "recurring": True,
            },
        ).status_code
        == 200
    )
    assert (
        client.put(path + "/monitoring", json={"next_run_at": "bad"}).status_code == 422
    )
    client.post(path + "/evidence", json=bill_payload)
    first = client.post(
        path + "/evaluate", headers={"Idempotency-Key": "stable"}
    ).json()
    assert (
        client.post(path + "/evaluate", headers={"Idempotency-Key": "stable"}).json()
        == first
    )
    notice = client.get("/api/v1/notifications").json()[0]
    assert (
        client.patch(
            "/api/v1/notifications/" + notice["id"], json={"status": "read"}
        ).status_code
        == 200
    )
    assert db.get(Notification, UUID(notice["id"])).acknowledged_at is not None


def test_cancellation_invalidates_running_worker(scenario):
    from app.schemas.expectation import ExpectationUpdate

    sessions, (owner, eid, jid, now) = scenario
    owned = claim(sessions, now)
    with sessions() as db:
        expectation_service.update_expectation(
            db, eid, ExpectationUpdate(status="cancelled"), owner
        )
    assert not Worker(settings(), sessions).finish(owned, [], now=now)
    assert counts(sessions, eid) == (0, 0, 0)
    with sessions() as db:
        assert db.get(MonitoringJob, jid).status == "cancelled"


def test_bounded_ambiguous_evidence_is_unknown(scenario):
    sessions, (_, eid, _, now) = scenario
    with sessions() as db:
        db.add_all(
            [
                Evidence(
                    expectation_id=eid,
                    source="utility_bill",
                    metric="total_cost",
                    value={"amount": 162},
                    observed_at=now - timedelta(seconds=60),
                )
                for _ in range(101)
            ]
        )
        db.commit()
    assert Worker(settings(), sessions).run_once(now=now)
    with sessions() as db:
        row = db.scalar(select(Evaluation).where(Evaluation.expectation_id == eid))
        assert (
            row.result.value == "UNKNOWN"
            and row.reasoning["reason"] == "insufficient_evidence"
        )


def test_safe_worker_failure_retries_without_sensitive_error(
    scenario, monkeypatch, caplog
):
    sessions, (_, eid, jid, now) = scenario
    worker = Worker(settings(), sessions)

    def broken(*a, **k):
        raise RuntimeError("secret-token-and-database-url")

    monkeypatch.setattr(worker, "finish", broken)
    assert worker.run_once(now=now)
    with sessions() as db:
        job = db.get(MonitoringJob, jid)
        assert job.status == "pending" and job.last_error == "WORKER_ERROR"
        assert job.next_run_at == now + timedelta(seconds=30)
    assert counts(sessions, eid) == (0, 0, 0)
    assert "secret-token-and-database-url" not in caplog.text


def test_monitoring_http_is_owned(client, users, numeric_payload):
    from app.api.dependencies import get_current_user
    from app.main import app

    eid = client.post("/api/v1/expectations", json=numeric_payload).json()["id"]
    app.dependency_overrides[get_current_user] = lambda: users[1]
    try:
        assert client.get(f"/api/v1/expectations/{eid}/monitoring").status_code == 404
        assert (
            client.put(
                f"/api/v1/expectations/{eid}/monitoring",
                json={"next_run_at": datetime.now(timezone.utc).isoformat()},
            ).status_code
            == 404
        )
    finally:
        app.dependency_overrides[get_current_user] = lambda: users[0]


def test_numeric_observation_after_deadline_does_not_fulfil(scenario):
    sessions, (_, eid, _, now) = scenario
    with sessions() as db:
        db.get(Expectation, eid).deadline = now - timedelta(minutes=5)
        db.commit()
    fact(sessions, eid, now, amount=130)
    assert Worker(settings(), sessions).run_once(now=now)
    with sessions() as db:
        result = db.scalar(select(Evaluation).where(Evaluation.expectation_id == eid))
        assert result.result.value == "UNKNOWN"
        assert result.reasoning["reason"] == "observation_after_deadline"
        assert db.get(Expectation, eid).status.value == "monitoring"
    assert counts(sessions, eid) == (1, 1, 0)


def test_missed_periods_coalesce_to_a_single_run_with_aligned_window(scenario):
    sessions, (_, eid, jid, now) = scenario
    with sessions() as db:
        job = db.get(MonitoringJob, jid)
        job.recurring = True
        job.interval_seconds = 60
        job.scheduled_at = job.next_run_at = now - timedelta(seconds=185)
        db.commit()
    assert Worker(settings(), sessions).run_once(now=now)
    with sessions() as db:
        job = db.get(MonitoringJob, jid)
        assert job.next_run_at == now + timedelta(seconds=55)
        assert job.window_start_at == now - timedelta(seconds=5)
    assert counts(sessions, eid) == (0, 1, 0)
    assert not Worker(settings(), sessions).run_once(now=now)
