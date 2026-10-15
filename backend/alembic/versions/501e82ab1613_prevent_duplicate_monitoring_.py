
"""prevent duplicate monitoring notifications

Revision ID: 501e82ab1613
Revises: 8b10af011a55
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "501e82ab1613"
down_revision: Union[str, Sequence[str], None] = "8b10af011a55"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_monitoring_notification_expectation_type",
        "notifications",
        ["expectation_id", "user_id", "type"],
        unique=True,
        postgresql_where=sa.text(
            "evaluation_id IS NULL "
            "AND type IN ('expectation_overdue', 'missing_evidence')"
        ),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_monitoring_notification_expectation_type",
        table_name="notifications",
    )
