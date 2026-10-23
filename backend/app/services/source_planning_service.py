"""Typed, rules-first expectation orchestration over current owned projections.

Language/temporal clarification stays in the existing compiler. Saved expectations
enter this read-only source planner, then explicit confirmation atomically binds
approved references and wakes the existing monitor. No model, network or SQL agent.
"""

from datetime import datetime, timedelta, timezone
from time import perf_counter

from sqlalchemy import select

from app.core.exceptions import ExpectationNotFoundError, InvalidExpectationError
from app.core.observability import record
from app.db.models import (
    Expectation,
    ExpectationSourceBinding,
    ProviderSourceEvent,
    ProviderSyncState,
)
from app.db.models.integration import IntegrationConnection, IntegrationCredential
from app.integrations.accounts import account_oauth
from app.integrations.normalization import version
from app.integrations.provider import ProviderError
from app.integrations.worker import value_for
from app.schemas.provider_sync import BindingCreate, SourceRule
from app.schemas.source_plan import (
    AppliedMonitoringPlan,
    MonitoringPlan,
    SourceCandidate,
)
from app.services import monitoring_service, provider_sync_service
from app.services.expectation_service import get_expectation


def rule_for(expectation, facts, external_id, query):
    metric = expectation.metric
    if facts.get("unavailable"):
        return None
    if facts.get("kind") == "calendar" and metric in (
        "event_cancelled",
        "event_scheduled",
        "event_not_cancelled",
        "event_unchanged",
    ):
        if query.calendar_uid and facts.get("calendar_uid") != query.calendar_uid:
            return None
        return SourceRule(
            kind="calendar",
            event_id=external_id,
            calendar_uid=facts.get("calendar_uid"),
            occurrence_start=facts.get("original_start"),
            expected_start=query.expected_start,
        )
    if (
        facts.get("kind") != "email"
        or not facts.get("sender")
        or not facts.get("thread_id")
    ):
        return None
    fields = {"sender": facts["sender"], "thread_id": facts["thread_id"]}
    if metric in ("delivery_reported", "package_delivery") and facts.get("order_id"):
        if query.order_id and query.order_id != facts["order_id"]:
            return None
        # Shipping updates can use a different thread. The explicitly confirmed
        # exact sender + order ID is the association, not inbox subject similarity.
        return SourceRule(
            kind="order", order_id=facts["order_id"], sender=facts["sender"]
        )
    if metric in (
        "event_cancelled",
        "event_scheduled",
        "event_not_cancelled",
        "event_unchanged",
    ) and facts.get("calendar_uid"):
        if query.calendar_uid and facts["calendar_uid"] != query.calendar_uid:
            return None
        return SourceRule(
            kind="commitment",
            calendar_uid=facts["calendar_uid"],
            occurrence_start=facts.get("original_start"),
            expected_start=query.expected_start,
            **fields,
        )
    if metric == "total_cost" and facts.get("currency") == "USD" and "amount" in facts:
        return SourceRule(kind="bill", **fields)
    if metric == "reply_received":
        return SourceRule(kind="reply", **fields)
    if metric in ("commitment_confirmed", "commitment_cancelled") and facts.get(
        "commitment_status"
    ):
        return SourceRule(kind="commitment", **fields)
    return None


def preview(db, settings, expectation_id, user_id, query, *, now=None):
    started = perf_counter()
    now = now or datetime.now(timezone.utc)
    expectation = get_expectation(db, expectation_id, user_id)
    plan = MonitoringPlan(
        expectation_id=expectation.id,
        status="clarification",
        deadline=expectation.deadline,
        triggers=("verified_provider_change", "periodic_reconciliation", "deadline")
        if expectation.deadline
        else ("verified_provider_change", "periodic_reconciliation"),
    )
    if expectation.status.value in ("cancelled", "resolved"):
        return plan.model_copy(
            update={
                "status": "unsupported",
                "question": "This expectation is no longer being monitored.",
            }
        )
    if expectation.metric not in (
        "total_cost",
        "reply_received",
        "delivery_reported",
        "package_delivery",
        "commitment_confirmed",
        "commitment_cancelled",
        "event_cancelled",
        "event_not_cancelled",
        "event_scheduled",
        "event_unchanged",
    ):
        return plan.model_copy(
            update={
                "status": "unsupported",
                "question": "This expectation needs an explicitly supported evidence metric.",
            }
        )
    if expectation.metric == "event_unchanged" and not query.expected_start:
        return plan.model_copy(
            update={"question": "What exact start time should stay unchanged?"}
        )
    states = list(
        db.execute(
            select(ProviderSyncState, IntegrationConnection)
            .join(
                IntegrationConnection,
                IntegrationConnection.id == ProviderSyncState.connection_id,
            )
            .join(
                IntegrationCredential,
                IntegrationCredential.connection_id == IntegrationConnection.id,
            )
            .where(
                ProviderSyncState.user_id == user_id,
                IntegrationConnection.user_id == user_id,
                IntegrationCredential.user_id == user_id,
                IntegrationConnection.status == "connected",
            )
            .order_by(ProviderSyncState.id)
            .limit(21)
        )
    )
    if not settings.provider_sync_enabled or not states:
        return plan.model_copy(
            update={
                "status": "permission_required",
                "question": "Please authorize and synchronize an email account or calendar in CountOn first.",
            }
        )
    candidates, inspected = [], 0
    for sync, connection in states[:20]:
        if (
            not connection.oauth_generation
            or sync.status in ("paused", "auth_required", "error")
            or not sync.last_success_at
            or sync.last_success_at < now - timedelta(seconds=3600)
        ):
            continue
        try:
            crypto = account_oauth(settings, connection)
            crypto.authorize_projection(db, connection, now)
            rows = list(
                db.scalars(
                    select(ProviderSourceEvent)
                    .where(
                        ProviderSourceEvent.sync_id == sync.id,
                        ProviderSourceEvent.user_id == user_id,
                    )
                    .order_by(
                        ProviderSourceEvent.observed_at.desc(), ProviderSourceEvent.id
                    )
                    .limit(201 - inspected)
                )
            )
            for row in rows:
                inspected += 1
                if inspected > 200:
                    return plan.model_copy(
                        update={
                            "status": "bounded",
                            "question": "Please narrow the source selection using an exact order or calendar identifier.",
                        }
                    )
                facts = crypto.decrypt(row.encrypted_facts, sync.id)
                rule = rule_for(expectation, facts, row.external_id, query)
                if rule is None or value_for(facts, rule, expectation.metric) is None:
                    continue
                if facts.get("recurring_id") and not rule.occurrence_start:
                    continue
                # Stable identifiers group references; titles never associate records.
                key = {"owner": str(user_id), "metric": expectation.metric}
                if rule.order_id:
                    key.update(order=rule.order_id)
                    label = "Order " + rule.order_id
                elif rule.calendar_uid:
                    key.update(
                        calendar=rule.calendar_uid,
                        occurrence=str(rule.occurrence_start),
                    )
                    label = str(
                        facts.get("title")
                        or facts.get("subject")
                        or "Calendar occurrence"
                    )[:180]
                else:
                    key.update(
                        sync=str(sync.id), thread=rule.thread_id, sender=rule.sender
                    )
                    label = str(facts.get("subject") or "Email thread")[:180]
                candidates.append(
                    SourceCandidate(
                        sync_id=sync.id,
                        external_id=row.external_id,
                        group_id=version(key),
                        provider=connection.provider,
                        account_label=(
                            connection.display_name
                            or f"{connection.provider} {connection.connection_type}"
                        )[:150],
                        label=label,
                        suggestion_reason={
                            "order": "Exact order identifier in a synchronized email.",
                            "calendar": "Exact calendar event and occurrence identity.",
                            "commitment": "Exact sender/thread or explicit calendar reference.",
                            "bill": "Explicit USD total in this sender's email thread.",
                            "reply": "Exact sender and email thread; absence needs verified coverage.",
                        }[rule.kind],
                        synced_at=sync.last_success_at,
                        sync_status=sync.status,
                        rule=rule,
                    )
                )
        except (ProviderError, ValueError, TypeError):
            continue  # unavailable or malformed private projection cannot authorize a plan
    if len(states) > 20 or len(candidates) > 20:
        plan.status, plan.question = (
            "bounded",
            "Please narrow the source selection using an exact identifier.",
        )
    else:
        # One rule per account/thread or exact event; later revisions don't add questions.
        unique = {}
        for candidate in candidates:
            unique.setdefault(
                (candidate.sync_id, version(candidate.rule.model_dump(mode="json"))),
                candidate,
            )
        plan.candidates = list(unique.values())
        groups = {c.group_id for c in plan.candidates}
        plan.status = "ready" if len(groups) == 1 else "clarification"
        plan.question = (
            "Confirm which accounts and source references CountOn may monitor."
            if len(groups) == 1
            else "Which order, event or email thread should I monitor?"
            if groups
            else "I couldn't find a matching authorized source. Please select an exact source in CountOn."
        )
    record("source_plans", plan.status)
    record("source_plan_latency_seconds", plan.status, perf_counter() - started)
    return plan


def apply(db, settings, expectation_id, user_id, request):
    """No trusted plan supplied by a browser: recompute and reauthorize every reference."""
    # Same connection -> sync -> expectation lock order as publication/revocation.
    get_expectation(db, expectation_id, user_id)
    list(
        db.scalars(
            select(IntegrationConnection)
            .join(
                ProviderSyncState,
                ProviderSyncState.connection_id == IntegrationConnection.id,
            )
            .where(
                IntegrationConnection.user_id == user_id,
                ProviderSyncState.user_id == user_id,
                ProviderSyncState.id.in_([s.sync_id for s in request.sources]),
            )
            .order_by(IntegrationConnection.id)
            .with_for_update(of=IntegrationConnection)
            .execution_options(populate_existing=True)
        )
    )
    # Fence cancellation/deletion and refresh identity-map state before planning.
    list(
        db.scalars(
            select(ProviderSyncState)
            .where(
                ProviderSyncState.user_id == user_id,
                ProviderSyncState.id.in_([s.sync_id for s in request.sources]),
            )
            .order_by(ProviderSyncState.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    )
    expectation = db.scalar(
        select(Expectation)
        .where(
            Expectation.id == expectation_id,
            Expectation.user_id == user_id,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if expectation is None:
        raise ExpectationNotFoundError(expectation_id)
    plan = preview(db, settings, expectation_id, user_id, request.query)
    available = {(c.sync_id, c.external_id): c for c in plan.candidates}
    selected = [available.get((s.sync_id, s.external_id)) for s in request.sources]
    if (
        not selected
        or any(c is None for c in selected)
        or len({c.group_id for c in selected}) != 1
        or len({c.sync_id for c in selected}) != len(selected)
    ):
        raise InvalidExpectationError(
            "Choose current authorized references for one expectation"
        )
    expectation = get_expectation(db, expectation_id, user_id)
    if expectation.status.value in ("cancelled", "resolved"):
        raise InvalidExpectationError("Terminal expectations cannot be monitored")
    existing = list(
        db.scalars(
            select(ExpectationSourceBinding).where(
                ExpectationSourceBinding.expectation_id == expectation_id,
                ExpectationSourceBinding.user_id == user_id,
            )
        )
    )
    # This additive plan must not silently remove or overwrite prior user choices.
    if any(
        not any(
            b.sync_id == c.sync_id and b.rule == c.rule.model_dump(mode="json")
            for c in selected
        )
        for b in existing
    ):
        raise InvalidExpectationError(
            "Remove or review existing source bindings before applying this plan"
        )
    if len(existing) == len(selected):
        job = monitoring_service.get(db, expectation_id, user_id)
        return AppliedMonitoringPlan(
            expectation_id=expectation_id,
            job_id=job.id,
            binding_ids=[b.id for b in existing],
            status=job.status,
        )
    try:
        bindings = [
            provider_sync_service.bind(
                db,
                expectation_id,
                user_id,
                BindingCreate(sync_id=c.sync_id, rule=c.rule),
                commit=False,
            )
            for c in selected
        ]
        db.commit()
    except Exception:
        db.rollback()
        raise
    job = monitoring_service.get(db, expectation_id, user_id)
    record("monitoring_plans_applied", "confirmed")
    return AppliedMonitoringPlan(
        expectation_id=expectation_id,
        job_id=job.id,
        binding_ids=[b.id for b in bindings],
        status=job.status,
    )
