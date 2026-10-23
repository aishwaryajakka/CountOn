
"""Owner-scoped notification persistence; no delivery credentials or network."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.db.models import Notification
from sqlalchemy.dialects.postgresql import insert

def create_mismatch(db, expectation, evaluation):
    """Create one in-app notification for a mismatched evaluation."""
    values = {
        "user_id": expectation.user_id,
        "expectation_id": expectation.id,
        "evaluation_id": evaluation.id,
        "notification_metadata": {"result": "MISMATCH"},
    }

    if (
        expectation.compiler_metadata
        and expectation.compiler_metadata.get("demo_tag")
    ):
        values["notification_metadata"].update(
            demo=True,
            demo_tag=expectation.compiler_metadata["demo_tag"],
        )

    created_id = db.scalar(
        insert(Notification)
        .values(**values)
        .on_conflict_do_nothing(
            constraint="uq_notification_evaluation"
        )
        .returning(Notification.id)
    )

    item = db.scalar(
        select(Notification).where(
            Notification.evaluation_id == evaluation.id,
            Notification.user_id == expectation.user_id,
        )
    )

    return item, created_id is not None


def create_monitoring_notification(
    db,
    expectation,
    notification_type: str,
    message: str,
):
    """Create at most one monitoring notification per expectation and type."""
    metadata = {"source": "background_monitoring"}

    if (
        expectation.compiler_metadata
        and expectation.compiler_metadata.get("demo_tag")
    ):
        metadata.update(
            demo=True,
            demo_tag=expectation.compiler_metadata["demo_tag"],
        )

    created_id = db.scalar(
        insert(Notification)
        .values(
            expectation_id=expectation.id,
            user_id=expectation.user_id,
            evaluation_id=None,
            type=notification_type,
            channel="in_app",
            message=message,
            notification_metadata=metadata,
            status="pending",
        )
        .on_conflict_do_nothing(
            index_elements=[
                Notification.expectation_id,
                Notification.user_id,
                Notification.type,
            ],
            index_where=(
                Notification.evaluation_id.is_(None)
                & Notification.type.in_(
                    ["expectation_overdue", "missing_evidence"]
                )
            ),
        )
        .returning(Notification.id)
    )

    # No ID means the unique index prevented a duplicate insert.
    if created_id is None:
        return None, False

    item = db.scalar(
        select(Notification).where(
            Notification.id == created_id
        )
    )

    return item, True


def get(db, notification_id, user_id):
    """Get a notification belonging to the specified user."""
    return db.scalar(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == user_id,
        )
    )


def list_notifications(
    db,
    user_id,
    status=None,
    limit=100,
    offset=0,
):
    """List notifications belonging to the specified user."""
    statement = select(Notification).where(
        Notification.user_id == user_id
    )

    if status is not None:
        statement = statement.where(
            Notification.status == status
        )

    statement = (
        statement
        .order_by(
            Notification.created_at.desc(),
            Notification.id.desc(),
        )
        .limit(limit)
        .offset(offset)
    )

    return list(db.scalars(statement))


def update_status(db, item, status):
    """Update a notification's status."""
    item.status = status
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
