"""MATCH/UNKNOWN are silent; MISMATCH produces one in-app row per evaluation."""
from typing import Protocol

from app.core.exceptions import ResourceNotFoundError
from app.repositories import audit
from app.repositories import notification as repository


class NotificationChannel(Protocol):
    def publish(self, db, expectation, evaluation, *, dedupe_key=None): ...


class InAppChannel:
    """Persistence is delivery; keep pending as the existing unread inbox state."""
    def publish(self, db, expectation, evaluation, *, dedupe_key=None):
        return repository.create_mismatch(db, expectation, evaluation, dedupe_key=dedupe_key)


def for_evaluation(db,expectation,evaluation,*,dedupe_key=None):
    if evaluation.result.value != 'MISMATCH':return None
    item,created=InAppChannel().publish(db,expectation,evaluation,dedupe_key=dedupe_key)
    if created:
        metadata={k:v for k,v in expectation.compiler_metadata.items() if k in ('demo','demo_tag')}
        audit.record(db,expectation.user_id,'notification',item.id,'notification.created',expectation.id,metadata)
    return item if created else None


def get(db,id,user_id):
    item=repository.get(db,id,user_id)
    if item is None:raise ResourceNotFoundError('NOTIFICATION_NOT_FOUND','Notification not found')
    return item


def list_notifications(db,user_id,**filters):return repository.list_notifications(db,user_id,**filters)


def update(db,id,status,user_id):
    item=get(db,id,user_id)
    if item.status==status:return item
    try:
        repository.update_status(db,item,status)
        audit.record(db,user_id,'notification',item.id,'notification.updated',item.expectation_id,{k:v for k,v in item.notification_metadata.items() if k in ('demo','demo_tag')})
        db.commit();db.refresh(item)
    except Exception:
        db.rollback();raise
    return item
