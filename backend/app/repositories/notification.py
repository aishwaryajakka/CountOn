"""Owner-scoped notification persistence; no delivery credentials or network."""
from sqlalchemy import select
from app.db.models import Notification
from sqlalchemy.dialects.postgresql import insert

def create_mismatch(db,expectation,evaluation):
    values=dict(user_id=expectation.user_id,expectation_id=expectation.id,evaluation_id=evaluation.id,
        notification_metadata={'result':'MISMATCH'})
    if expectation.compiler_metadata.get('demo_tag'):
        values['notification_metadata'].update(demo=True,demo_tag=expectation.compiler_metadata['demo_tag'])
    created_id=db.scalar(insert(Notification).values(**values).on_conflict_do_nothing(constraint='uq_notification_evaluation').returning(Notification.id))
    item=db.scalar(select(Notification).where(Notification.evaluation_id==evaluation.id,Notification.user_id==expectation.user_id))
    return item,created_id is not None


def get(db,id,user_id):
    return db.scalar(select(Notification).where(Notification.id==id,Notification.user_id==user_id))


def list_notifications(db,user_id,status=None,limit=100,offset=0):
    stmt=select(Notification).where(Notification.user_id==user_id)
    if status is not None:stmt=stmt.where(Notification.status==status)
    return list(db.scalars(stmt.order_by(Notification.created_at.desc(),Notification.id.desc()).limit(limit).offset(offset)))


def update_status(db,item,status):
    item.status=status
    db.flush()
    return item


def create_monitoring_notification(
    db,
    expectation,
    notification_type: str,
    message: str,
):
    """Create one idempotent notification for a monitoring alert."""
    if notification_type not in {
        "expectation_overdue",
        "missing_evidence",
    }:
        raise ValueError("Unsupported monitoring notification type")

    values = {
        "user_id": expectation.user_id,
        "expectation_id": expectation.id,
        "evaluation_id": None,
        "type": notification_type,
        "channel": "in_app",
        "message": message,
        "notification_metadata": {},
    }

    statement = (
        insert(Notification)
        .values(**values)
        .on_conflict_do_nothing(
            index_elements=[
                Notification.expectation_id,
                Notification.user_id,
                Notification.type,
            ],
            index_where=(
                (Notification.evaluation_id.is_(None))
                & Notification.type.in_(
                    ["expectation_overdue", "missing_evidence"]
                )
            ),
        )
        .returning(Notification.id)
    )

    created_id = db.scalar(statement)

    if created_id is None:
        return db.scalar(
            select(Notification).where(
                Notification.expectation_id == expectation.id,
                Notification.user_id == expectation.user_id,
                Notification.type == notification_type,
                Notification.evaluation_id.is_(None),
            )
        )

    return db.scalar(
        select(Notification).where(Notification.id == created_id)
    )
