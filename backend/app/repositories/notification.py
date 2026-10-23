"""Owner-scoped notification persistence; no delivery credentials or network."""
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import Notification


def create_mismatch(db,expectation,evaluation,*,dedupe_key=None):
    values={'user_id': expectation.user_id,'expectation_id': expectation.id,'evaluation_id': evaluation.id,
        'notification_metadata': {'result':'MISMATCH'}, 'dedupe_key': dedupe_key}
    if expectation.compiler_metadata.get('demo_tag'):
        values['notification_metadata'].update(demo=True,demo_tag=expectation.compiler_metadata['demo_tag'])
    created_id=db.scalar(insert(Notification).values(**values).on_conflict_do_nothing().returning(Notification.id))
    item=db.scalar(select(Notification).where(Notification.evaluation_id==evaluation.id,Notification.user_id==expectation.user_id))
    return item,created_id is not None


def get(db,id,user_id):
    return db.scalar(select(Notification).where(Notification.id==id,Notification.user_id==user_id))


def list_notifications(db,user_id,status=None,limit=100,offset=0):
    stmt=select(Notification).where(Notification.user_id==user_id)
    if status is not None:stmt=stmt.where(Notification.status==status)
    return list(db.scalars(stmt.order_by(Notification.created_at.desc(),Notification.id.desc()).limit(limit).offset(offset)))


def update_status(db,item,status):
    from datetime import datetime, timezone
    item.status=status
    if status in ('read','dismissed') and item.acknowledged_at is None:
        item.acknowledged_at = datetime.now(timezone.utc)
    db.flush()
    return item
