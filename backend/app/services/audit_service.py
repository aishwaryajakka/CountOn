"""Owner-scoped, redacted and filterable audit history reads."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import select

from app.db.models import AuditEvent, Evidence, Expectation
from app.repositories.audit import SAFE_METADATA_KEYS


def list_events(
    db, user_id: UUID, *, expectation_id: UUID | None = None,
    source_provider: str | None = None, result_status: str | None = None,
    occurred_after: datetime | None = None, occurred_before: datetime | None = None,
    limit: int = 100, offset: int = 0,
) -> list[dict]:
    query = (
        select(AuditEvent, Expectation, Evidence)
        .outerjoin(Expectation, (Expectation.id == AuditEvent.expectation_id) & (Expectation.user_id == AuditEvent.user_id))
        .outerjoin(Evidence, Evidence.id == AuditEvent.evidence_id)
        .where(AuditEvent.user_id == user_id)
    )
    if expectation_id is not None:
        query = query.where(AuditEvent.expectation_id == expectation_id)
    if source_provider is not None:
        query = query.where(AuditEvent.source_provider == source_provider.strip().upper())
    if result_status is not None:
        query = query.where(AuditEvent.result_status == result_status)
    if occurred_after is not None:
        query = query.where(AuditEvent.created_at >= occurred_after)
    if occurred_before is not None:
        query = query.where(AuditEvent.created_at < occurred_before)
    rows = db.execute(query.order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc()).limit(limit).offset(offset))
    return [{
        "audit_event_id": event.id,
        "counton_user_id": event.user_id,
        "expectation_id": event.expectation_id,
        "event_type": event.event_type,
        "occurred_at": event.created_at,
        "source_provider": event.source_provider,
        "source_type": event.source_type,
        "source_provenance": event.source_provenance,
        "source_reference": event.source_reference,
        "evidence_id": event.evidence_id,
        "evaluation_id": event.evaluation_id,
        "result_status": event.result_status,
        "action_taken": event.action,
        "actor_type": event.actor_type,
        "action_metadata": {key: value for key, value in event.audit_metadata.items() if key in SAFE_METADATA_KEYS},
        "request_id": event.request_id,
        "expectation": {"id": expectation.id, "claim": expectation.claim, "status": expectation.status.value} if expectation else None,
        "evidence": {
            "id": evidence.id, "source": evidence.source, "metric": evidence.metric,
            "value": evidence.value, "unit": evidence.unit, "observed_at": evidence.observed_at,
        } if evidence else None,
    } for event, expectation, evidence in rows]
