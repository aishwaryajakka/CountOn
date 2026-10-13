"""Connect existing source sync and monitoring leases, without network I/O."""

from datetime import datetime
from uuid import uuid4

from sqlalchemy import select

from app.db.models import (
    Expectation,
    ExpectationSourceBinding,
    MonitoringJob,
    ProviderSyncState,
)
from app.db.models.integration import IntegrationConnection, IntegrationCredential
from app.integrations.normalization import version


def bindings(db, expectation):
    return list(
        db.scalars(
            select(ExpectationSourceBinding).where(
                ExpectationSourceBinding.expectation_id == expectation.id,
                ExpectationSourceBinding.user_id == expectation.user_id,
            )
        )
    )


def wake(db, expectation, now: datetime):
    """Atomic coalescing: invalidate an old claim, respect an explicit pause."""
    db.flush()
    expectation = db.scalar(
        select(Expectation)
        .where(
            Expectation.id == expectation.id, Expectation.user_id == expectation.user_id
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if expectation is None or expectation.status.value in ("cancelled", "resolved"):
        return
    job = db.scalar(
        select(MonitoringJob)
        .where(
            MonitoringJob.expectation_id == expectation.id,
            MonitoringJob.user_id == expectation.user_id,
        )
        .order_by(
            MonitoringJob.status.in_(["pending", "running", "paused"]).desc(),
            MonitoringJob.created_at.desc(),
        )
        .with_for_update()
        .limit(1)
    )
    if job is None:
        job = MonitoringJob(expectation_id=expectation.id, user_id=expectation.user_id)
        db.add(job)
    if job.status in ("paused", "cancelled"):
        return
    job.status, job.next_run_at, job.scheduled_at = "pending", now, now
    job.run_key, job.attempt_count = uuid4(), 0
    job.lease_token = job.lease_expires_at = job.last_error = None


def context(db, expectation, now: datetime, max_age: int, *, binding_override=None):
    """Only current, explicit owned source/rule/generation evidence is eligible."""
    selected = bindings(db, expectation)
    if binding_override is not None:
        selected = [b for b in selected if b.id == binding_override.id]
    if not selected:
        # Don't silently fall back to old provider rows after disconnect/unbind.
        if any(
            s in expectation.evidence_sources
            for s in (
                "gmail_email",
                "outlook_email",
                "google_calendar",
                "microsoft_calendar",
            )
        ):
            return None, "source_not_bound"
        return None, None
    if len(selected) != 1:
        return None, "ambiguous_sources"
    binding = selected[0]
    sync = db.get(ProviderSyncState, binding.sync_id)
    connection = db.get(IntegrationConnection, sync.connection_id) if sync else None
    if (
        not connection
        or connection.user_id != expectation.user_id
        or connection.status != "connected"
        or not connection.oauth_generation
        or db.get(IntegrationCredential, connection.id) is None
        or sync.status in ("auth_required", "error", "paused")
    ):
        return None, "source_unavailable"
    from app.core.config import get_settings
    from app.integrations.accounts import account_oauth
    from app.integrations.provider import ProviderError

    try:
        account_oauth(get_settings(), connection).authorize_projection(
            db, connection, now
        )
    except (ProviderError, ValueError, TypeError):
        return None, "source_unavailable"
    if (
        not sync.last_success_at
        or (now - sync.last_success_at).total_seconds() > max_age
    ):
        return None, "stale_source"
    return {
        "binding_id": str(binding.id),
        "binding_rule": version(binding.rule),
        "connection_id": str(connection.id),
        "account_id": connection.external_account_id,
        "oauth_generation": str(connection.oauth_generation),
    }, None


def current_calendar_fact(db, expectation, evidence):
    """A completed delta/reconciliation attests to an unchanged calendar fact."""
    from app.db.models import ProviderSourceEvent

    selected = bindings(db, expectation)
    selected = [b for b in selected if str(b.id) == evidence.raw_data.get("binding_id")]
    if len(selected) != 1 or selected[0].rule.get("kind") != "calendar":
        return False
    source = db.scalar(
        select(ProviderSourceEvent).where(
            ProviderSourceEvent.sync_id == selected[0].sync_id,
            ProviderSourceEvent.external_id == evidence.raw_data.get("source_event_id"),
        )
    )
    return bool(
        source and source.version == version(evidence.raw_data.get("facts", {}))
    )


def absence_signature(identity: str) -> str:
    import hashlib
    import hmac

    from app.core.config import get_settings

    key = get_settings().integration_token_encryption_key
    if not key:
        return ""
    return hmac.new(
        key.get_secret_value().encode(),
        ("counton:verified-absence:" + identity).encode(),
        hashlib.sha256,
    ).hexdigest()


def verify_absence(evidence, expectation, binding) -> bool:
    import hmac

    if not binding or not expectation.deadline:
        return False
    identity = version(
        {
            "binding": str(binding.id),
            "rule": binding.rule,
            "deadline": expectation.deadline.isoformat(),
            "generation": evidence.raw_data.get("oauth_generation"),
            "coverage": evidence.raw_data.get("coverage_through_at"),
        }
    )
    if identity != evidence.external_event_id:
        return False
    signature = absence_signature(evidence.external_event_id or "")
    signed = bool(
        signature
        and hmac.compare_digest(
            signature, str(evidence.raw_data.get("coverage_signature", ""))
        )
    )
    return signed


def absence_still_current(db, expectation, binding, *, before_deadline_only=False):
    """An earlier empty snapshot cannot override subsequently discovered evidence."""
    from app.core.config import get_settings
    from app.db.models import ProviderSourceEvent
    from app.integrations.accounts import account_oauth
    from app.integrations.provider import ProviderError
    from app.integrations.worker import matches
    from app.schemas.provider_sync import SourceRule

    sync = db.get(ProviderSyncState, binding.sync_id)
    connection = db.get(IntegrationConnection, sync.connection_id)
    rule = SourceRule.model_validate(binding.rule)
    sources = list(
        db.scalars(
            select(ProviderSourceEvent)
            .where(ProviderSourceEvent.sync_id == sync.id)
            .limit(10001)
        )
    )
    if len(sources) > 10000:
        return False
    crypto = account_oauth(get_settings(), connection)
    try:
        for source in sources:
            facts = crypto.decrypt(source.encrypted_facts, sync.id)
            if facts.get("unavailable") and not facts.get("sender"):
                return False
            if matches(facts, source.external_id, rule) and (
                facts.get("unavailable")
                or not facts.get("source_timestamp")
                or (
                    datetime.fromisoformat(facts["source_timestamp"])
                    >= expectation.created_at
                    and (
                        not before_deadline_only
                        or datetime.fromisoformat(facts["source_timestamp"])
                        <= expectation.deadline
                    )
                )
            ):
                return False
        return True
    except (ProviderError, ValueError, TypeError):
        return False


def publish_absence(db, expectation, binding, sync, connection, relevant, now):
    """Prove selected-inbox absence only; silence by itself never proves failure."""
    from app.schemas.evidence import EvidenceCreate
    from app.services.evidence_service import add_evidence

    if (
        binding.rule.get("kind") != "reply"
        or expectation.metric != "reply_received"
        or not expectation.deadline
        or now < expectation.deadline
        or not sync.coverage_start_at
        or sync.coverage_start_at > expectation.created_at
        or not sync.coverage_through_at
        or sync.coverage_through_at < expectation.deadline
    ):
        return
    # An unavailable/deleted candidate cannot be treated as a proved absence.
    if any(
        facts.get("unavailable")
        or not facts.get("source_timestamp")
        or datetime.fromisoformat(facts["source_timestamp"]) >= expectation.created_at
        for _, facts in relevant
    ):
        return
    identity = version(
        {
            "binding": str(binding.id),
            "rule": binding.rule,
            "deadline": expectation.deadline.isoformat(),
            "generation": str(connection.oauth_generation),
            "coverage": sync.coverage_through_at.isoformat(),
        }
    )
    signature = absence_signature(identity)
    if not signature:
        return  # key removal impairs monitoring, never silently trust absence
    from app.services.provider_sync_service import source_name

    add_evidence(
        db,
        expectation.id,
        EvidenceCreate(
            source=source_name(connection),
            metric="reply_received",
            value={"value": False},
            observed_at=now,
            confidence=1,
            external_event_id=identity,
            raw_data={
                "binding_id": str(binding.id),
                "binding_rule": version(binding.rule),
                "connection_id": str(connection.id),
                "account_id": connection.external_account_id,
                "oauth_generation": str(connection.oauth_generation),
                "absence_verified": True,
                "coverage_signature": signature,
                "coverage_start_at": sync.coverage_start_at.isoformat(),
                "coverage_through_at": sync.coverage_through_at.isoformat(),
                "provenance": "official_api",
                "scope": sync.stream,
            },
        ),
        expectation.user_id,
        identity,
        commit=False,
    )
    wake(db, expectation, now)


def grounded_provider_fact(db, expectation, evidence):
    """Verify the evidence payload against the backend-only current projection."""
    from app.db.models import ProviderSourceEvent
    from app.evaluators.numeric import extract_numeric
    from app.integrations.worker import matches, value_for
    from app.schemas.provider_sync import SourceRule
    from app.services.provider_sync_service import source_name

    selected = bindings(db, expectation)
    selected = [b for b in selected if str(b.id) == evidence.raw_data.get("binding_id")]
    if len(selected) != 1:
        return False
    binding = selected[0]
    sync = db.get(ProviderSyncState, binding.sync_id)
    connection = db.get(IntegrationConnection, sync.connection_id)
    source = db.scalar(
        select(ProviderSourceEvent).where(
            ProviderSourceEvent.sync_id == sync.id,
            ProviderSourceEvent.external_id == evidence.raw_data.get("source_event_id"),
        )
    )
    facts = evidence.raw_data.get("facts")
    if not source or not isinstance(facts, dict) or version(facts) != source.version:
        return False
    rule = SourceRule.model_validate(binding.rule)
    if evidence.source != source_name(connection) or not matches(
        facts, source.external_id, rule
    ):
        return False
    normalized = value_for(facts, rule, expectation.metric)
    if normalized is None:
        return False
    expected, unit = normalized
    if (
        expectation.metric in ("delivery_reported", "package_delivery")
        and expectation.deadline
        and expected.get("value") is True
        and not facts.get("delivery_timestamp")
    ):
        expected = {"value": None}
    if expectation.type.value == "numeric_comparison":
        equal = extract_numeric(evidence.value) == extract_numeric(expected)
    else:
        equal = evidence.value == expected
    if not equal or evidence.unit != unit:
        return False
    try:
        if connection.connection_type == "email":
            instant = (
                facts.get("delivery_timestamp")
                if expectation.metric in ("delivery_reported", "package_delivery")
                and expected.get("value") is True
                else facts.get("source_timestamp")
            )
            return bool(
                instant
                and evidence.observed_at == datetime.fromisoformat(instant)
                and evidence.confidence <= 0.8
            )
        modified = facts.get("source_timestamp")
        return not modified or evidence.observed_at >= datetime.fromisoformat(modified)
    except (ValueError, TypeError):
        return False
