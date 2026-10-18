"""add calendar event persistence

Revision ID: 70e96a04757b
Revises: 298fc0cf83dc
Create Date: 2026-10-18 23:43:29.329729
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '70e96a04757b'
down_revision: Union[str, Sequence[str], None] = '298fc0cf83dc'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "calendar_events",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("connection_id", sa.UUID(), nullable=False),
        sa.Column("external_event_id", sa.String(length=512), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=True),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "is_cancelled",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column(
            "event_data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "last_synced_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["connection_id"],
            ["integration_connections.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "connection_id",
            "external_event_id",
            name="uq_calendar_event_connection_external_id",
        ),
    )
    op.create_index(
        "ix_calendar_events_start_at",
        "calendar_events",
        ["start_at"],
        unique=False,
    )

def downgrade() -> None:
    op.drop_index(
        "ix_calendar_events_start_at",
        table_name="calendar_events",
    )
    op.drop_table("calendar_events")
