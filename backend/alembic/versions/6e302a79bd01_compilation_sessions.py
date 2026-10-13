"""Durable clarification lifecycle and capture replay protection.

Revision ID: 6e302a79bd01
Revises: 5d201f68ac90
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "6e302a79bd01"
down_revision = "5d201f68ac90"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "compilation_sessions",
        sa.Column("id", UUID(), primary_key=True),
        sa.Column("user_id", UUID(), nullable=False),
        sa.Column("state", JSONB(), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expectation_id", UUID(), nullable=True),
    )
    op.create_index(
        "ix_compilation_sessions_user_id", "compilation_sessions", ["user_id"]
    )
    op.create_index(
        "ix_compilation_sessions_expires_at", "compilation_sessions", ["expires_at"]
    )
    # Only the trusted backend DB role can use this ledger; no browser access.
    op.execute("ALTER TABLE public.compilation_sessions ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON public.compilation_sessions FROM PUBLIC")


def downgrade():
    op.drop_table("compilation_sessions")
