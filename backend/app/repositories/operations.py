"""Operational writes participate in the owning service transaction."""
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from app.db.models import AuditEvent, MonitoringJob, Notification, Expectation
from app.core.observability import request_id


def audit(db, expectation, action, resource_id=None):
    from app.repositories.audit import record
    entity_type = 'evidence' if action.startswith('evidence.') else ('evaluation' if action.endswith('.evaluated') else 'expectation')
    metadata={k:v for k,v in expectation.compiler_metadata.items() if k in ('demo','demo_tag')}
    return record(db,expectation.user_id,entity_type,resource_id or expectation.id,action,expectation.id,metadata)


def ensure_job(db, expectation):
    statement=insert(MonitoringJob).values(expectation_id=expectation.id,user_id=expectation.user_id)
    db.execute(statement.on_conflict_do_nothing(index_elements=['expectation_id'],index_where=text("status IN ('pending','running','paused')")))
