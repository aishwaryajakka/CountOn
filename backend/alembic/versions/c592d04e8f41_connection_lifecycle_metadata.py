"""Add safe connected-account lifecycle metadata.

Revision ID: c592d04e8f41
Revises: b4819ac72e30
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c592d04e8f41"
down_revision: str | Sequence[str] | None = "b4819ac72e30"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "integration_connections",
        sa.Column("connected_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "integration_connections",
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.add_column(
        "integration_connections",
        sa.Column("failure_status", sa.String(64)),
    )
    op.execute(
        """
        UPDATE integration_connections
        SET connected_at = created_at
        WHERE status = 'connected' AND connected_at IS NULL
        """
    )
    op.execute(
        """
        UPDATE integration_connections
        SET revoked_at = updated_at
        WHERE status = 'disconnected' AND revoked_at IS NULL
        """
    )


def downgrade() -> None:
    op.drop_column("integration_connections", "failure_status")
    op.drop_column("integration_connections", "revoked_at")
    op.drop_column("integration_connections", "connected_at")
