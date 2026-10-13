"""Durable bounded-page synchronization, PostgreSQL leases and fenced publication.

Run: python -m app.integrations.worker. No emails/calendar events are modified.
"""

import argparse
import logging
import signal
import threading
from datetime import datetime, timedelta, timezone
from time import perf_counter
from uuid import uuid4

from sqlalchemy import delete, or_, select

from app.core.config import get_settings
from app.core.observability import record
from app.db.models import (
    Evidence,
    Expectation,
    ExpectationSourceBinding,
    IntegrationConnection,
    ProviderSourceEvent,
    ProviderSyncState,
)
from app.integrations.accounts import account_oauth
from app.integrations.adapters import AccountAdapter
from app.integrations.normalization import version
from app.integrations.provider import ProviderError
from app.repositories import audit
from app.schemas.evidence import EvidenceCreate
from app.schemas.provider_sync import SourceRule
from app.services import evidence_service, integration_service
from app.services.provider_sync_service import source_name

logger = logging.getLogger(__name__)


def matches(facts: dict, event_id: str, rule: SourceRule) -> bool:
    if rule.calendar_uid and facts.get("calendar_uid") != rule.calendar_uid:
        return False
    if rule.occurrence_start:
        try:
            if (
                datetime.fromisoformat(facts.get("original_start", ""))
                != rule.occurrence_start
            ):
                return False
        except (ValueError, TypeError):
            return False
    if rule.kind == "calendar":
        return event_id == rule.event_id
    if facts.get("sender", "").casefold() != (rule.sender or "").casefold():
        return False
    return not (
        rule.message_id
        and event_id != rule.message_id
        or rule.recipient
        and rule.recipient.casefold() not in facts.get("recipients", [])
        or rule.thread_id
        and facts.get("thread_id") != rule.thread_id
        or rule.subject_contains
        and rule.subject_contains.casefold() not in facts.get("subject", "").casefold()
        or rule.order_id
        and facts.get("order_id") != rule.order_id
    )


def value_for(
    facts: dict, rule: SourceRule, metric: str | None
) -> tuple[dict, str | None] | None:
    if facts.get("unavailable"):
        return ({"value": None}, None)
    if rule.kind == "bill" and metric == "total_cost":
        if facts.get("currency") == rule.currency and "amount" in facts:
            return ({"amount": facts["amount"]}, "USD")
        return ({"value": None}, None)
    if rule.kind == "reply" and metric == "reply_received":
        return ({"value": True}, None)
    if rule.kind == "calendar":
        cancelled = facts.get("cancelled") is True
        if metric == "event_cancelled":
            return ({"value": cancelled}, None)
        if metric == "event_scheduled":
            return ({"value": not cancelled}, None)
        if metric == "event_not_cancelled":
            return ({"value": not cancelled}, None)
        if metric == "event_unchanged" and rule.expected_start and facts.get("start"):
            try:
                start = datetime.fromisoformat(facts["start"])
                if start.tzinfo is None:
                    return None  # all-day date cannot prove an expected timestamp
                return ({"value": not cancelled and start == rule.expected_start}, None)
            except ValueError:
                return None
    if rule.kind == "commitment" and metric in (
        "commitment_confirmed",
        "commitment_cancelled",
        "event_not_cancelled",
        "event_cancelled",
        "event_scheduled",
        "event_unchanged",
    ):
        status = facts.get("commitment_status")
        if status not in ("confirmed", "cancelled"):
            return ({"value": None}, None)
        if metric == "event_unchanged":
            if not rule.expected_start or not facts.get("event_start"):
                return ({"value": None}, None)
            try:
                unchanged = (
                    datetime.fromisoformat(facts["event_start"]) == rule.expected_start
                )
                return ({"value": status == "confirmed" and unchanged}, None)
            except (ValueError, TypeError):
                return ({"value": None}, None)
        return (
            {
                "value": status
                == (
                    "cancelled"
                    if metric in ("commitment_cancelled", "event_cancelled")
                    else "confirmed"
                )
            },
            None,
        )
    if rule.kind == "order" and metric in ("delivery_reported", "package_delivery"):
        return (
            {"value": True if facts.get("shipping_status") == "delivered" else None},
            None,
        )
    if rule.kind == "order" and metric == "order_update":
        return (
            {
                key: facts[key]
                for key in (
                    "order_id",
                    "merchant_reference",
                    "expected_delivery_date",
                    "revised_delivery_date",
                    "shipping_status",
                    "tracking_id",
                    "report_basis",
                )
                if key in facts
            },
            None,
        )
    return None  # no inference from silence, date strings, or arbitrary metrics


class SyncWorker:
    def __init__(
        self,
        sessions,
        settings,
        *,
        oauth_factory=account_oauth,
        adapter_factory=AccountAdapter,
        now=None,
    ):
        self.sessions, self.settings = sessions, settings
        self.oauth_factory, self.adapter_factory = oauth_factory, adapter_factory
        self.now = now or (lambda: datetime.now(timezone.utc))

    def claim(self):
        now = self.now()
        with self.sessions() as db:
            item = db.scalar(
                select(ProviderSyncState)
                .where(
                    or_(
                        ProviderSyncState.status == "pending",
                        (ProviderSyncState.status == "running")
                        & or_(
                            ProviderSyncState.lease_expires_at <= now,
                            ProviderSyncState.lease_expires_at.is_(None),
                        ),
                    ),
                    ProviderSyncState.next_run_at <= now,
                )
                .order_by(ProviderSyncState.next_run_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if item is None:
                return None
            if item.attempt_count >= 8:
                item.status, item.last_error = "error", "ATTEMPTS_EXHAUSTED"
                item.lease_token = item.lease_expires_at = None
                db.commit()
                return None
            item.status, item.lease_token = "running", uuid4()
            item.lease_expires_at = now + timedelta(minutes=30)
            item.attempt_count += 1
            db.commit()
            return item.id, item.lease_token

    def once(self) -> bool:
        if not self.settings.provider_sync_enabled:
            return False
        claimed = self.claim()
        if claimed is None:
            return False
        id, lease = claimed
        started = perf_counter()
        now = self.now()
        try:
            with self.sessions() as db:
                item = db.get(ProviderSyncState, id)
                if item is None:
                    return True
                connection = integration_service.get(
                    db, item.connection_id, item.user_id
                )
                oauth = self.oauth_factory(self.settings, connection)
                generation = connection.oauth_generation
                wake_stamp, prior_success = item.wake_requested_at, item.last_success_at
                account_id, scopes = (
                    connection.external_account_id,
                    list(connection.scopes),
                )
                provider_label = connection.provider
                token = oauth.access_token(db, connection.id, item.user_id, now)
                checkpoint = (
                    oauth.decrypt(item.encrypted_checkpoint, item.id)
                    if item.encrypted_checkpoint
                    else {}
                )
                adapter = self.adapter_factory(
                    connection.provider,
                    connection.connection_type,
                    oauth.http,
                    self.settings.provider_retention_days,
                )
                if isinstance(adapter, AccountAdapter):
                    adapter.cache_scope = (
                        str(item.user_id),
                        str(connection.id),
                        str(generation),
                        item.stream,
                        version({"scopes": scopes}),
                        str(self.settings.provider_retention_days),
                    )
                try:
                    page = adapter.page(token, item.stream, checkpoint, now)
                except ProviderError as error:
                    if error.code != "SYNC_CURSOR_EXPIRED":
                        raise
                    page = adapter.page(token, item.stream, {}, now)
                    # New full reconciliation round: missing old sources become unavailable.
                    checkpoint = {}
                db.rollback()
                # Serialize against disconnect/reconnect first, then fence sync and rule edits.
                connection = oauth.connection(
                    db, connection.id, connection.user_id, lock=True
                )
                item = db.scalar(
                    select(ProviderSyncState)
                    .where(ProviderSyncState.id == id)
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if (
                    item is None
                    or item.lease_token != lease
                    or item.lease_expires_at <= self.now()
                    or connection.oauth_generation != generation
                    or connection.status != "connected"
                    or connection.external_account_id != account_id
                    or connection.scopes != scopes
                ):
                    db.rollback()
                    return True
                if not checkpoint:
                    item.round_id = uuid4()
                    item.round_started_at = now
                    item.coverage_start_at = item.coverage_through_at = None
                if item.round_started_at is None:
                    item.round_started_at = now
                round_started = item.round_started_at
                for external_id, facts in page.events:
                    if not external_id or len(external_id) > 512:
                        raise ProviderError(
                            "PROVIDER_RESPONSE_INVALID", retryable=False
                        )
                    stored = db.scalar(
                        select(ProviderSourceEvent).where(
                            ProviderSourceEvent.sync_id == id,
                            ProviderSourceEvent.external_id == external_id,
                        )
                    )
                    if stored is None:
                        stored = ProviderSourceEvent(
                            sync_id=id, user_id=item.user_id, external_id=external_id
                        )
                        db.add(stored)
                    elif (
                        stored.encrypted_facts
                        and connection.connection_type == "calendar"
                    ):
                        previous = oauth.decrypt(stored.encrypted_facts, id)
                        old_time, new_time = (
                            previous.get("source_timestamp"),
                            facts.get("source_timestamp"),
                        )
                        if (
                            old_time
                            and new_time
                            and datetime.fromisoformat(new_time)
                            < datetime.fromisoformat(old_time)
                        ):
                            stored.seen_round, stored.observed_at = item.round_id, now
                            continue
                    incoming_version = version(facts)
                    if stored.encrypted_facts and stored.version == incoming_version:
                        stored.observed_at, stored.seen_round = now, item.round_id
                        record("provider_duplicate_suppression", "unchanged_projection")
                        continue
                    if facts.get("unavailable") and stored.encrypted_facts:
                        facts = {**oauth.decrypt(stored.encrypted_facts, id), **facts}
                    stored.encrypted_facts, stored.version = (
                        oauth.encrypt(facts, id),
                        version(facts),
                    )
                    stored.observed_at, stored.seen_round = now, item.round_id
                db.flush()
                if page.complete:
                    # Full pagination proves coverage only up to its first pull;
                    # an incremental round starts at the previous durable cursor.
                    if page.full:
                        # A retained snapshot cannot prove that a reply never
                        # arrived before synchronization began. Coverage starts
                        # at the real cursor anchor, never backdated by retention.
                        item.coverage_start_at = item.round_started_at
                    if item.coverage_start_at:
                        item.coverage_start_at = max(
                            item.coverage_start_at,
                            now - timedelta(days=self.settings.provider_retention_days),
                        )
                    item.coverage_through_at = item.round_started_at
                    if page.full:
                        for stored in db.scalars(
                            select(ProviderSourceEvent).where(
                                ProviderSourceEvent.sync_id == id,
                                ProviderSourceEvent.seen_round != item.round_id,
                            )
                        ):
                            facts = {
                                **oauth.decrypt(stored.encrypted_facts, id),
                                "unavailable": True,
                            }
                            stored.encrypted_facts, stored.version = (
                                oauth.encrypt(facts, id),
                                version(facts),
                            )
                            stored.observed_at, stored.seen_round = now, item.round_id
                    self.publish(db, item, connection, oauth, now)
                    item.last_success_at, connection.last_synced_at = now, now
                    connection.failure_status = None
                    audit.record(
                        db, item.user_id, "integration", connection.id,
                        "provider.sync_completed", actor_type="PROVIDER",
                        source_provider=connection.provider.upper(),
                        source_type=connection.connection_type.upper(),
                        source_provenance="OFFICIAL_API",
                        source_reference=connection.external_account_id,
                        idempotency_key=f"SYNC_COMPLETED:{item.id}:{item.round_id}",
                    )
                    item.round_id = uuid4()
                    item.round_started_at = None
                item.encrypted_checkpoint = oauth.encrypt(page.checkpoint, id)
                item.status, item.lease_token, item.lease_expires_at = (
                    "pending",
                    None,
                    None,
                )
                item.attempt_count, item.last_error = 0, None
                item.next_run_at = now + timedelta(
                    seconds=self.settings.provider_sync_interval_seconds
                    if page.complete
                    else 1
                )
                if item.wake_requested_at and item.wake_requested_at >= round_started:
                    item.next_run_at = now
                for deadline in db.scalars(
                    select(Expectation.deadline)
                    .join(
                        ExpectationSourceBinding,
                        ExpectationSourceBinding.expectation_id == Expectation.id,
                    )
                    .where(ExpectationSourceBinding.sync_id == item.id)
                ):
                    if deadline and now < deadline < item.next_run_at:
                        item.next_run_at = deadline
                db.execute(
                    delete(ProviderSourceEvent).where(
                        ProviderSourceEvent.sync_id == id,
                        ProviderSourceEvent.observed_at
                        < now - timedelta(days=self.settings.provider_retention_days),
                    )
                )
                db.commit()
                from app.integrations.watches import renew

                try:
                    renew(db, self.settings, item, connection, oauth, token, now)
                except ProviderError:
                    logger.warning(
                        "Provider push unavailable; polling continues",
                        extra={"result_status": "push_unavailable"},
                    )
            logger.info(
                "Provider synchronization completed",
                extra={
                    "result_status": "complete" if page.complete else "page",
                    "run_id": str(lease),
                },
            )
            record("provider_sync_results", "complete" if page.complete else "page")
            record("provider_sync_records", provider_label, len(page.events))
            if page.complete:
                record(
                    "provider_reconciliation_seconds",
                    provider_label,
                    max(0, (self.now() - round_started).total_seconds()),
                )
                if (
                    wake_stamp
                    and wake_stamp <= round_started
                    and (not prior_success or wake_stamp > prior_success)
                ):
                    record(
                        "provider_wake_latency_seconds",
                        provider_label,
                        max(0, (self.now() - wake_stamp).total_seconds()),
                    )
        except Exception as error:  # noqa: BLE001 -- fence failures without logging provider bodies
            safe = (
                error
                if isinstance(error, ProviderError)
                else ProviderError("WORKER_ERROR")
            )
            with self.sessions() as db:
                item = db.scalar(
                    select(ProviderSyncState)
                    .where(ProviderSyncState.id == id)
                    .with_for_update()
                )
                if item is not None and item.lease_token == lease:
                    item.last_error = safe.code
                    connection = db.scalar(
                        select(IntegrationConnection).where(
                            IntegrationConnection.id == item.connection_id,
                            IntegrationConnection.user_id == item.user_id,
                        )
                    )
                    if connection is not None:
                        connection.failure_status = safe.code
                    item.status = (
                        "auth_required"
                        if safe.code
                        in (
                            "AUTH_REQUIRED",
                            "PERMISSION_DENIED",
                            "CREDENTIAL_UNAVAILABLE",
                        )
                        else "error"
                        if not safe.retryable or item.attempt_count >= 8
                        else "pending"
                    )
                    item.next_run_at = self.now() + timedelta(
                        seconds=max(
                            safe.retry_after,
                            min(3600, 15 * 2 ** min(item.attempt_count, 8)),
                        )
                    )
                    item.lease_token, item.lease_expires_at = None, None
                    from app.monitoring.sources import wake
                    from app.services.expectation_service import get_expectation

                    for binding in db.scalars(
                        select(ExpectationSourceBinding).where(
                            ExpectationSourceBinding.sync_id == id
                        )
                    ):
                        wake(
                            db,
                            get_expectation(db, binding.expectation_id, item.user_id),
                            self.now(),
                        )
                    db.commit()
            logger.warning(
                "Provider synchronization failed",
                extra={"result_status": safe.code, "run_id": str(lease)},
            )
            record("provider_sync_results", safe.code)
        finally:
            record("provider_sync_latency_seconds", "worker", perf_counter() - started)
        return True

    def publish(self, db, item, connection, crypto, now):
        from app.services.expectation_service import get_expectation

        bindings = list(
            db.scalars(
                select(ExpectationSourceBinding)
                .where(
                    ExpectationSourceBinding.sync_id == item.id,
                    ExpectationSourceBinding.user_id == item.user_id,
                )
                .limit(1001)
            )
        )
        sources = list(
            db.scalars(
                select(ProviderSourceEvent)
                .where(ProviderSourceEvent.sync_id == item.id)
                .limit(10001)
            )
        )
        if len(bindings) > 1000 or len(sources) > 10000:
            raise ProviderError("INCOMPLETE_SYNC", retryable=False)
        decoded = [
            (source, crypto.decrypt(source.encrypted_facts, item.id))
            for source in sources
        ]
        for binding in bindings:
            expectation = get_expectation(db, binding.expectation_id, item.user_id)
            db.refresh(expectation, with_for_update=True)
            if str(expectation.status) in ("cancelled", "resolved"):
                continue
            rule = SourceRule.model_validate(binding.rule)
            relevant = decoded
            relevant = [
                (source, facts)
                for source, facts in relevant
                if matches(facts, source.external_id, rule)
            ]
            if rule.kind == "reply":
                # The first actual reply satisfies the condition; later replies
                # cannot retroactively turn an on-time reply into a late one.
                relevant.sort(key=lambda pair: pair[1].get("source_timestamp", ""))
                useful = [
                    (source, facts)
                    for source, facts in relevant
                    if not facts.get("unavailable")
                    and facts.get("source_timestamp")
                    and datetime.fromisoformat(facts["source_timestamp"])
                    >= expectation.created_at
                ]
                if useful:
                    relevant = useful[:1]
            for source, facts in relevant:
                normalized = value_for(facts, rule, expectation.metric)
                if normalized is None:
                    continue
                value, unit = normalized
                # Email receipt time is not the actual delivery time.
                if (
                    expectation.metric in ("delivery_reported", "package_delivery")
                    and expectation.deadline
                    and value.get("value") is True
                    and not facts.get("delivery_timestamp")
                ):
                    value = {"value": None}
                source_timestamp = facts.get("source_timestamp")
                observed = (
                    datetime.fromisoformat(source_timestamp)
                    if source_timestamp and connection.connection_type == "email"
                    else now
                )
                if (
                    expectation.metric in ("delivery_reported", "package_delivery")
                    and value.get("value") is True
                    and facts.get("delivery_timestamp")
                ):
                    observed = datetime.fromisoformat(facts["delivery_timestamp"])
                if observed < expectation.created_at or observed < now - timedelta(
                    days=self.settings.provider_retention_days
                ):
                    continue
                # Only changed source facts create evidence; polling cannot repeat notifications.
                identity = version(
                    {
                        "binding": str(binding.id),
                        "event": source.external_id,
                        "version": source.version,
                        "rule": binding.rule,
                        "metric": expectation.metric,
                        "generation": str(connection.oauth_generation),
                        "format_version": 2,
                    }
                )
                if db.scalar(
                    select(Evidence.id).where(
                        Evidence.expectation_id == expectation.id,
                        Evidence.idempotency_key == identity,
                    )
                ):
                    record("provider_duplicate_suppression", "evidence")
                    continue
                payload = EvidenceCreate(
                    source=source_name(connection),
                    metric=expectation.metric,
                    value=value,
                    unit=unit,
                    observed_at=observed,
                    confidence=0.8 if connection.connection_type == "email" else 1.0,
                    external_event_id=identity,
                    raw_data={
                        "connection_id": str(connection.id),
                        "binding_id": str(binding.id),
                        "binding_rule": version(binding.rule),
                        "oauth_generation": str(connection.oauth_generation),
                        "account_id": connection.external_account_id,
                        "source_event_id": source.external_id,
                        "source_version": source.version,
                        "source_timestamp": source_timestamp,
                        "effective_at": facts.get("start")
                        or facts.get("revised_delivery_date")
                        or facts.get("expected_delivery_date")
                        or source_timestamp,
                        "observed_at": observed.isoformat(),
                        "verified_at": now.isoformat(),
                        "scopes": connection.scopes,
                        "provenance": "official_api",
                        "report_basis": facts.get("report_basis", "provider_event"),
                        "sender_authenticated": facts.get(
                            "sender_authenticated", False
                        ),
                        "facts": facts,
                    },
                )
                evidence_service.add_evidence(
                    db, expectation.id, payload, item.user_id, identity, commit=False
                )
                from app.monitoring.sources import wake

                wake(db, expectation, now)
                from app.services.notification_service import delivery_estimate_warning

                delivery_estimate_warning(
                    db, expectation, facts, identity, now, timezone=rule.timezone
                )
            from app.monitoring.sources import publish_absence, wake

            unidentified = any(
                facts.get("unavailable") and not facts.get("sender")
                for _, facts in decoded
            )
            if rule.recipient:
                unidentified = unidentified or any(
                    facts.get("sender") == rule.sender
                    and facts.get("thread_id") == rule.thread_id
                    and not facts.get("recipients")
                    for _, facts in decoded
                )
            if not unidentified:
                publish_absence(
                    db, expectation, binding, item, connection, relevant, now
                )
            # Coverage/health changes must also wake evaluation (without new facts).
            wake(db, expectation, now)
            if expectation.deadline and expectation.deadline > now:
                item.next_run_at = min(item.next_run_at, expectation.deadline)


def main():
    from app.core.logging import configure_logging
    from app.db.session import SessionLocal

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--once", action="store_true", help="Attempt one due synchronization page"
    )
    args = parser.parse_args()
    settings = get_settings()
    configure_logging()
    if not settings.provider_sync_enabled:
        raise SystemExit(
            "Provider sync is disabled; set PROVIDER_SYNC_ENABLED=true on the backend."
        )
    worker = SyncWorker(SessionLocal, settings)
    stopped = threading.Event()
    for name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(name, lambda *_: stopped.set())
    while not stopped.is_set():
        try:
            processed = worker.once()
        except Exception:  # noqa: BLE001 -- preserve leases and mask private database diagnostics
            logger.error("Provider synchronization database unavailable")
            if args.once:
                raise SystemExit(1) from None
            processed = False
        if args.once:
            return
        if not processed:
            stopped.wait(2)


if __name__ == "__main__":
    main()
