"""Append-only, idempotent, redacted audit writes in the caller transaction."""

from hashlib import sha256

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.core.observability import request_id
from app.db.models import AuditEvent

SAFE_METADATA_KEYS = {
    "action", "bedrock_attempted", "bedrock_used", "capabilities", "certainty",
    "count", "deadline", "demo", "demo_tag", "duration_ms", "evaluator_result",
    "evaluation_id", "evidence_ids", "fallback_used", "grounded", "model_grounding_passed",
    "reason", "reported_date", "run_id", "safe_to_say", "source_decisions",
    "sources_used", "status", "channel", "notification_id",
}

EVENT_TYPES = {
    "expectation.created": "EXPECTATION_CREATED",
    "expectation.confirmed": "EXPECTATION_CONFIRMED",
    "expectation.updated": "EXPECTATION_UPDATED",
    "expectation.cancelled": "EXPECTATION_CANCELLED",
    "expectation.creation_failed": "EXPECTATION_CREATION_FAILED",
    "clarification.updated": "CLARIFICATION_UPDATED",
    "expectation.deleted": "EXPECTATION_CANCELLED",
    "provider.authorized": "SOURCE_AUTHORIZED",
    "provider.source_bound": "SOURCE_AUTHORIZED",
    "provider.disconnected": "SOURCE_DISCONNECTED",
    "provider.sync_completed": "SYNC_COMPLETED",
    "evidence.ingested": "EVIDENCE_INGESTED",
    "evidence.correlated": "EVIDENCE_CORRELATED",
    "expectation.evaluated": "EVALUATION_COMPLETED",
    "expectation.mismatch": "MISMATCH_DETECTED",
    "explanation.generated": "EXPLANATION_GENERATED",
    "notification.created": "NOTIFICATION_CREATED",
    "notification.sent": "NOTIFICATION_SENT",
    "notification.delivery_failed": "NOTIFICATION_DELIVERY_FAILED",
    "notification.acknowledged": "NOTIFICATION_ACKNOWLEDGED",
    "recommendation.approved": "RECOMMENDATION_APPROVED",
    "recommendation.dismissed": "RECOMMENDATION_DISMISSED",
}


def safe_reference(value: object | None) -> str | None:
    """Return a stable pseudonymous correlation reference, never raw provider data."""
    if value is None or not str(value):
        return None
    return "sha256:" + sha256(("counton-audit:" + str(value)).encode()).hexdigest()


def evidence_source(evidence) -> dict:
    source = evidence.source
    raw = evidence.raw_data if isinstance(evidence.raw_data, dict) else {}
    provenance = str(raw.get("provenance") or "USER_SUBMITTED").upper()
    provider, source_type = {
        "gmail_email": ("GMAIL", "EMAIL"),
        "gmail": ("GMAIL", "EMAIL"),
        "outlook_email": ("OUTLOOK", "EMAIL"),
        "google_calendar": ("GOOGLE", "CALENDAR"),
        "microsoft_calendar": ("MICROSOFT", "CALENDAR"),
        "outlook_calendar": ("MICROSOFT", "CALENDAR"),
        "ring_simulator": ("RING", "RING_EVENT"),
        "bee_simulator": ("BEE", "BEE_OBSERVATION"),
        "bee": ("BEE", "BEE_OBSERVATION"),
        "utility_bill": ("UTILITY_BILL", "NORMALIZED_EVIDENCE"),
        "utility_usage": ("UTILITY_USAGE", "NORMALIZED_EVIDENCE"),
        "tariff": ("TARIFF", "NORMALIZED_EVIDENCE"),
        "weather": ("WEATHER", "NORMALIZED_EVIDENCE"),
        "email": ("EMAIL", "NORMALIZED_EVIDENCE"),
    }.get(source, ("DECLARED_SOURCE", "NORMALIZED_EVIDENCE"))
    reference = (
        raw.get("provider_record_ref")
        or raw.get("source_event_id")
        or evidence.external_event_id
    )
    if raw.get("source_category") == "amazon_order_email":
        source_type = "AMAZON_ORDER_EMAIL"
    return {
        "source_provider": provider,
        "source_type": source_type,
        "source_provenance": provenance[:40],
        "source_reference": safe_reference(reference),
    }


def record(
    db, user_id, entity_type, entity_id, action, expectation_id=None, metadata=None,
    *, event_type=None, actor_type="SYSTEM", source_provider=None, source_type=None,
    source_provenance=None, source_reference=None, evidence_id=None,
    evaluation_id=None, result_status=None, idempotency_key=None,
):
    values = {
        "user_id": user_id,
        "entity_type": entity_type,
        "resource_id": entity_id,
        "expectation_id": expectation_id,
        "action": action,
        "event_type": event_type or EVENT_TYPES.get(action, "OPERATION_RECORDED"),
        "actor_type": actor_type,
        "source_provider": source_provider,
        "source_type": source_type,
        "source_provenance": source_provenance,
        "source_reference": safe_reference(source_reference)
        if source_reference and not str(source_reference).startswith("sha256:")
        else source_reference,
        "evidence_id": evidence_id,
        "evaluation_id": evaluation_id,
        "result_status": result_status,
        "idempotency_key": idempotency_key,
        "request_id": request_id.get(),
        "audit_metadata": {
            key: value for key, value in (metadata or {}).items()
            if key in SAFE_METADATA_KEYS
        },
    }
    statement = insert(AuditEvent).values(**values)
    if idempotency_key:
        statement = statement.on_conflict_do_nothing(
            constraint="uq_audit_owner_idempotency"
        )
    identity = db.scalar(statement.returning(AuditEvent.id))
    if identity is not None:
        return db.get(AuditEvent, identity)
    return db.scalar(select(AuditEvent).where(
        AuditEvent.user_id == user_id,
        AuditEvent.idempotency_key == idempotency_key,
    ))
