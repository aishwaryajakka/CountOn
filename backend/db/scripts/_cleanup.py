"""Remove only explicitly identified acceptance artifacts, including audit rows."""
from sqlalchemy import delete,select
from app.db.models import AuditEvent,Evidence,Evaluation,Expectation,Notification
from app.services.expectation_service import delete_expectation


def cleanup_expectations(db,owner,ids):
    owned=list(db.scalars(select(Expectation.id).where(Expectation.id.in_(ids),Expectation.user_id==owner)))
    resources=set(owned)
    for model in (Evidence,Evaluation,Notification):
        resources.update(db.scalars(select(model.id).where(model.expectation_id.in_(owned))))
    for eid in owned:
        delete_expectation(db,eid,owner)
    remove_audits(db,owner,resources)


def remove_audits(db,owner,resources):
    if resources:
        db.execute(delete(AuditEvent).where(AuditEvent.user_id==owner,AuditEvent.resource_id.in_(resources)))
        db.commit()
