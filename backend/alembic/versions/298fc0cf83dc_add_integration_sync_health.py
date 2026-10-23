"""add integration sync health

Revision ID: 298fc0cf83dc
Revises: f7a9c2d1b640
Create Date: 2026-10-17 06:39:10.409927
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '298fc0cf83dc'
down_revision: Union[str, Sequence[str], None] = 'f7a9c2d1b640'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None



def upgrade() -> None:
    op.add_column(
        "integration_connections",
        sa.Column(
            "sync_status",
            sa.String(length=20),
            nullable=False,
            server_default="idle",
        ),
    )
    op.add_column(
        "integration_connections",
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "integration_connections",
        sa.Column("last_error_code", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "integration_connections",
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "integration_connections",
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_check_constraint(
        "ck_integration_sync_status",
        "integration_connections",
        "sync_status IN ('idle','success','error','retrying')",
    )
    op.create_check_constraint(
        "ck_integration_consecutive_failures",
        "integration_connections",
        "consecutive_failures >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_integration_consecutive_failures",
        "integration_connections",
        type_="check",
    )
    op.drop_constraint(
        "ck_integration_sync_status",
        "integration_connections",
        type_="check",
    )

    op.drop_column("integration_connections", "next_retry_at")
    op.drop_column("integration_connections", "consecutive_failures")
    op.drop_column("integration_connections", "last_error_code")
    op.drop_column("integration_connections", "last_attempt_at")
    op.drop_column("integration_connections", "sync_status")
