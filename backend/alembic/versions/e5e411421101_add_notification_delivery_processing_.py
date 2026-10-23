"""add notification delivery processing lease

Revision ID: e5e411421101
Revises: 07bc7f5ce116
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e5e411421101"
down_revision = "07bc7f5ce116"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "notification_deliveries",
        sa.Column(
            "processing_started_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column(
        "notification_deliveries",
        "processing_started_at",
    )