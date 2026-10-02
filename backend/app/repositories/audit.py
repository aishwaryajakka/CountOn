"""Backend-owned, redacted audit writes within the caller's transaction."""
from app.db.models import AuditEvent
from app.core.observability import request_id


def record(db,user_id,entity_type,entity_id,action,expectation_id=None,metadata=None):
    event=AuditEvent(user_id=user_id,entity_type=entity_type,resource_id=entity_id,
        expectation_id=expectation_id,action=action,request_id=request_id.get(),audit_metadata=metadata or {})
    db.add(event)
    return event
