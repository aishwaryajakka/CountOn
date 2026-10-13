"""Bee CLI connector authorization and import staging.

Revision ID: b4819ac72e30
Revises: ac746eb3f145
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b4819ac72e30"
down_revision: str | Sequence[str] | None = "ac746eb3f145"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bee_cli_pairings",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("code_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"], ondelete="CASCADE", name="fk_bee_pairing_user"),
    )
    op.create_index("ix_bee_cli_pairings_user_id", "bee_cli_pairings", ["user_id"])
    op.create_index("ix_bee_cli_pairings_expires_at", "bee_cli_pairings", ["expires_at"])
    op.create_table(
        "bee_cli_credentials",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("connection_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("cli_version", sa.String(64), nullable=False),
        sa.Column("checkpoint", sa.String(512)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("last_sync_at", sa.DateTime(timezone=True)),
        sa.Column("last_error", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["connection_id", "user_id"], ["integration_connections.id", "integration_connections.user_id"], ondelete="CASCADE", name="fk_bee_cli_connection_owner"),
        sa.UniqueConstraint("connection_id", name="uq_bee_cli_connection"),
    )
    op.create_index("ix_bee_cli_credentials_user_id", "bee_cli_credentials", ["user_id"])
    op.create_table(
        "bee_import_candidates",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("connection_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=False),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("category", sa.String(20), nullable=False),
        sa.Column("summary", sa.String(1000), nullable=False),
        sa.Column("fact", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("imported_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["connection_id", "user_id"], ["integration_connections.id", "integration_connections.user_id"], ondelete="CASCADE", name="fk_bee_candidate_connection_owner"),
        sa.UniqueConstraint("connection_id", "external_id", name="uq_bee_candidate_external"),
        sa.CheckConstraint("category IN ('fact','todo','conversation','journal')", name="ck_bee_candidate_category"),
        sa.CheckConstraint("status IN ('pending','imported','rejected')", name="ck_bee_candidate_status"),
    )
    op.create_index("ix_bee_import_candidates_user_id", "bee_import_candidates", ["user_id"])
    op.create_table(
        "bee_expectation_bindings",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("connection_id", sa.UUID(), nullable=False),
        sa.Column("expectation_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["connection_id", "user_id"], ["integration_connections.id", "integration_connections.user_id"], ondelete="CASCADE", name="fk_bee_binding_connection_owner"),
        sa.ForeignKeyConstraint(["expectation_id", "user_id"], ["expectations.id", "expectations.user_id"], ondelete="CASCADE", name="fk_bee_binding_expectation_owner"),
        sa.UniqueConstraint("connection_id", "expectation_id", name="uq_bee_expectation_binding"),
    )
    op.create_index("ix_bee_expectation_bindings_user_id", "bee_expectation_bindings", ["user_id"])
    for table in ("bee_cli_pairings", "bee_cli_credentials", "bee_import_candidates", "bee_expectation_bindings"):
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON public.{table} FROM PUBLIC")
        for role in ("anon", "authenticated"):
            op.execute(f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN REVOKE ALL ON public.{table} FROM {role}; END IF; END $$")
        op.execute(f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN GRANT ALL ON public.{table} TO service_role; END IF; END $$")


def downgrade() -> None:
    op.drop_table("bee_expectation_bindings")
    op.drop_table("bee_import_candidates")
    op.drop_table("bee_cli_credentials")
    op.drop_table("bee_cli_pairings")
