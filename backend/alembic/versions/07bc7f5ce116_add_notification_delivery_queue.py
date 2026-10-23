"""add notification delivery queue

Revision ID: 07bc7f5ce116
Revises: 5d201f68ac90
Revises: 4c35f2c88019
Create Date: 2026-10-15 19:11:00.544990
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "07bc7f5ce116"
down_revision: Union[str, Sequence[str], None] = "5d201f68ac90"
down_revision: Union[str, Sequence[str], None] = "4c35f2c88019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "notification_deliveries",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "notification_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("notifications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "channel",
            sa.String(length=30),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "max_attempts",
            sa.Integer(),
            nullable=False,
            server_default="5",
        ),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "last_attempt_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "delivered_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column(
            "last_error",
            sa.String(length=100),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "notification_id",
            "channel",
            name="uq_notification_delivery_channel",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'delivered', 'failed')",
            name="ck_notification_delivery_status",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="ck_notification_delivery_attempt_count",
        ),
        sa.CheckConstraint(
            "max_attempts > 0",
            name="ck_notification_delivery_max_attempts",
        ),
    )

    op.create_index(
        "ix_notification_deliveries_due",
        "notification_deliveries",
        ["status", "next_attempt_at"],
    )

    op.create_index(
        "ix_notification_deliveries_notification",
        "notification_deliveries",
        ["notification_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notification_deliveries_notification",
        table_name="notification_deliveries",
    )
    op.drop_index(
        "ix_notification_deliveries_due",
        table_name="notification_deliveries",
    )
    op.drop_table("notification_deliveries")
