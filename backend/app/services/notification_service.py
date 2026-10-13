"""Persist attention events atomically. MATCH stays quiet; email is opt-in."""

from datetime import timedelta
from typing import Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.exceptions import ResourceNotFoundError
from app.db.models import Evaluation, Evidence, Notification, NotificationPreference
from app.integrations.normalization import version
from app.repositories import audit
from app.repositories import notification as repository


class NotificationChannel(Protocol):
    def publish(self, db, expectation, evaluation, *, dedupe_key=None): ...


class InAppChannel:
    """Persistence is delivery; pending is the existing unread inbox state."""

    def publish(self, db, expectation, evaluation, *, dedupe_key=None):
        return repository.create_mismatch(
            db, expectation, evaluation, dedupe_key=dedupe_key
        )


def audit_context(db, evaluation):
    raw = evaluation.reasoning.get("evidence_ids", []) if evaluation else []
    if evaluation and not raw and evaluation.observed.get("evidence_id"):
        raw = [evaluation.observed["evidence_id"]]
    evidence = None
    if raw:
        try:
            evidence = db.get(Evidence, UUID(str(raw[0])))
        except (ValueError, TypeError):
            pass
    return evidence, audit.evidence_source(evidence) if evidence else {}


def preference(db, user_id):
    return db.get(NotificationPreference, user_id)


def enabled(db, user_id, kind):
    pref = preference(db, user_id)
    field = {
        "expectation_mismatch": "mismatch_enabled",
        "upcoming_deadline": "deadline_enabled",
        "connection_warning": "connection_enabled",
        "potential_delivery_delay": "mismatch_enabled",
    }[kind]
    return getattr(pref, field) if pref else kind != "upcoming_deadline"


def enqueue_email(db, item):
    from app.db.models import NotificationDelivery

    pref = preference(db, item.user_id)
    if pref and pref.email_enabled and pref.encrypted_recipient:
        db.execute(
            insert(NotificationDelivery)
            .values(notification_id=item.id, user_id=item.user_id)
            .on_conflict_do_nothing(index_elements=["notification_id", "channel"])
        )


def for_evaluation(db, expectation, evaluation, *, dedupe_key=None):
    if dedupe_key and evaluation.result.value == "MATCH":
        for item in db.scalars(
            select(Notification).where(
                Notification.expectation_id == expectation.id,
                Notification.user_id == expectation.user_id,
                Notification.type == "expectation_mismatch",
                Notification.status.in_(["pending", "read", "sent"]),
            )
        ):
            item.status = "dismissed"
            item.notification_metadata = {
                **item.notification_metadata,
                "resolved_by_evaluation_id": str(evaluation.id),
            }
            audit.record(
                db,
                expectation.user_id,
                "notification",
                item.id,
                "notification.auto_closed",
                expectation.id,
                {},
            )
    if evaluation.result.value != "MISMATCH" or not enabled(
        db, expectation.user_id, "expectation_mismatch"
    ):
        return None
    if dedupe_key:
        # Same mismatch episode remains one alert, even with a new source version.
        # UNKNOWN (e.g. expired OAuth) cannot falsely reset a contradiction episode.
        previous = db.scalar(
            select(Evaluation)
            .where(
                Evaluation.expectation_id == expectation.id,
                Evaluation.id != evaluation.id,
                Evaluation.result != "UNKNOWN",
            )
            .order_by(Evaluation.created_at.desc(), Evaluation.id.desc())
            .limit(1)
        )
        if previous is not None and previous.result.value == "MISMATCH":
            return None
    item, created = InAppChannel().publish(
        db, expectation, evaluation, dedupe_key=dedupe_key
    )
    if created:
        item.notification_metadata = {
            **item.notification_metadata,
            "evidence_ids": evaluation.reasoning.get("evidence_ids", []),
            "reason": evaluation.reasoning.get("reason"),
            "evaluation_id": str(evaluation.id),
        }
        # Use known reason codes, not arbitrary evidence text, in notifications.
        reason = evaluation.reasoning.get("primary_reason") or evaluation.reasoning.get(
            "reason"
        )
        item.message = {
            "reply_absent_after_covered_deadline": "No reply was found in the selected synchronized mailbox thread by your deadline.",
            "event_observed_after_deadline": "The recorded event occurred after your deadline.",
        }.get(
            reason,
            {
                "event_not_cancelled": "The linked source reports this event was cancelled. Open CountOn to review the evidence.",
                "event_unchanged": "The linked schedule no longer matches the start you chose. Open CountOn to review the evidence.",
            }.get(
                expectation.metric,
                "The latest recorded evidence did not meet this expectation. Open it to review the evidence.",
            ),
        )
        metadata = {
            k: v
            for k, v in expectation.compiler_metadata.items()
            if k in ("demo", "demo_tag")
        }
        evidence, source = audit_context(db, evaluation)
        audit.record(
            db,
            expectation.user_id,
            "notification",
            item.id,
            "notification.created",
            expectation.id,
            metadata,
            actor_type="SYSTEM",
            evidence_id=evidence.id if evidence else None,
            evaluation_id=evaluation.id,
            result_status=evaluation.result.value,
            idempotency_key=f"NOTIFICATION_CREATED:{item.id}",
            **source,
        )
        enqueue_email(db, item)
    return item if created else None


def notice(db, expectation, kind, message, identity, *, evaluation=None, metadata=None):
    if not enabled(db, expectation.user_id, kind):
        return None
    id = db.scalar(
        insert(Notification)
        .values(
            user_id=expectation.user_id,
            expectation_id=expectation.id,
            # The existing unique evaluation FK is reserved for mismatch alerts.
            # A single UNKNOWN can warrant both a source and deadline warning.
            evaluation_id=None,
            type=kind,
            message=message,
            dedupe_key=version({"kind": kind, "identity": identity}),
            notification_metadata={
                **(metadata or {}),
                **({"evaluation_id": str(evaluation.id)} if evaluation else {}),
            },
        )
        .on_conflict_do_nothing()
        .returning(Notification.id)
    )
    if id is None:
        return None
    item = db.get(Notification, id)
    enqueue_email(db, item)
    evidence, source = audit_context(db, evaluation)
    audit.record(
        db,
        expectation.user_id,
        "notification",
        id,
        "notification.created",
        expectation.id,
        {},
        actor_type="SYSTEM",
        evidence_id=evidence.id if evidence else None,
        evaluation_id=evaluation.id if evaluation else None,
        result_status=evaluation.result.value if evaluation else None,
        idempotency_key=f"NOTIFICATION_CREATED:{id}",
        **source,
    )
    return item


def monitoring_warnings(db, expectation, evaluation, now):
    from app.db.models import ProviderSyncState
    from app.monitoring.sources import bindings

    reason = evaluation.reasoning.get("reason")
    if reason in ("source_unavailable", "stale_source", "source_not_bound"):
        selected = bindings(db, expectation)
        sync = (
            db.get(ProviderSyncState, selected[0].sync_id)
            if len(selected) == 1
            else None
        )
        notice(
            db,
            expectation,
            "connection_warning",
            "Tracking is impaired because the selected source needs attention. Reconnect or synchronize it; the outcome is unknown.",
            {
                "source": str(sync.id) if sync else "unbound",
                "last_success": str(sync.last_success_at) if sync else None,
            },
            evaluation=evaluation,
            metadata={"reason": reason},
        )
    if (
        expectation.deadline
        and now < expectation.deadline <= now + timedelta(hours=24)
        and evaluation.result.value == "UNKNOWN"
    ):
        notice(
            db,
            expectation,
            "upcoming_deadline",
            "This expectation is due within 24 hours and is still waiting for evidence.",
            expectation.deadline.isoformat(),
            evaluation=evaluation,
            metadata={"deadline": expectation.deadline.isoformat()},
        )


def delivery_estimate_warning(db, expectation, facts, identity, now, *, timezone="UTC"):
    if (
        expectation.metric not in ("delivery_reported", "package_delivery")
        or not expectation.deadline
    ):
        return
    zone = ZoneInfo(timezone)
    date = facts.get("revised_delivery_date") or facts.get("expected_delivery_date")
    if (
        date
        and date > expectation.deadline.astimezone(zone).date().isoformat()
        and facts.get("shipping_status") != "delivered"
    ):
        notice(
            db,
            expectation,
            "potential_delivery_delay",
            "The shipping email reports an arrival estimate after your deadline. This is a potential delay, not a confirmed missed delivery.",
            {
                "order": facts.get("order_id"),
                "estimate": date,
                "deadline": expectation.deadline.isoformat(),
            },
            metadata={
                "certainty": "predicted",
                "source_identity": identity,
                "reported_date": date,
            },
        )


def get(db, id, user_id):
    item = repository.get(db, id, user_id)
    if item is None:
        raise ResourceNotFoundError("NOTIFICATION_NOT_FOUND", "Notification not found")
    return item


def list_notifications(db, user_id, **filters):
    return repository.list_notifications(db, user_id, **filters)


def update(db, id, status, user_id):
    item = get(db, id, user_id)
    if item.status == status:
        return item
    try:
        repository.update_status(db, item, status)
        evaluation = db.get(Evaluation, item.evaluation_id) if item.evaluation_id else None
        evidence, source = audit_context(db, evaluation)
        audit.record(
            db,
            user_id,
            "notification",
            item.id,
            "notification.acknowledged",
            item.expectation_id,
            {
                k: v
                for k, v in item.notification_metadata.items()
                if k in ("demo", "demo_tag")
            },
            actor_type="USER",
            evidence_id=evidence.id if evidence else None,
            evaluation_id=item.evaluation_id,
            result_status=evaluation.result.value if evaluation else None,
            idempotency_key=f"NOTIFICATION_ACKNOWLEDGED:{item.id}",
            **source,
        )
        db.commit()
        db.refresh(item)
    except Exception:
        db.rollback()
        raise
    return item
