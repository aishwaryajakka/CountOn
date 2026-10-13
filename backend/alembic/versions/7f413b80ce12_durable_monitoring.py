"""Durable leases, evaluation/inbox deduplication and backend-only OAuth secrets."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "7f413b80ce12"
down_revision = "6e302a79bd01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint(
        "uq_integration_owner", "integration_connections", ["id", "user_id"]
    )
    op.add_column(
        "integration_connections", sa.Column("oauth_generation", sa.String(64))
    )
    columns = [
        sa.Column(
            "interval_seconds", sa.Integer(), nullable=False, server_default="3600"
        ),
        sa.Column("recurring", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column(
            "scheduled_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("window_start_at", sa.DateTime(timezone=True)),
        sa.Column(
            "max_evidence_age_seconds",
            sa.Integer(),
            nullable=False,
            server_default="86400",
        ),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="5"),
        sa.Column(
            "run_key",
            UUID(),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("lease_token", UUID()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("connection_id", UUID()),
        sa.Column(
            "provider_config",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    ]
    for column in columns:
        op.add_column("monitoring_jobs", column)
    op.execute("UPDATE monitoring_jobs SET scheduled_at=next_run_at")
    op.create_check_constraint(
        "ck_job_schedule",
        "monitoring_jobs",
        "interval_seconds >= 60 AND max_attempts BETWEEN 1 AND 20 AND max_evidence_age_seconds > 0",
    )
    op.create_foreign_key(
        "fk_job_owned_connection",
        "monitoring_jobs",
        "integration_connections",
        ["connection_id", "user_id"],
        ["id", "user_id"],
        ondelete="CASCADE",
    )
    op.create_index(
        "ix_monitoring_jobs_lease_expires_at", "monitoring_jobs", ["lease_expires_at"]
    )
    op.add_column("evaluations", sa.Column("idempotency_key", sa.String(128)))
    op.create_unique_constraint(
        "uq_evaluation_run", "evaluations", ["expectation_id", "idempotency_key"]
    )
    op.add_column("notifications", sa.Column("dedupe_key", sa.String(64)))
    op.add_column(
        "notifications", sa.Column("acknowledged_at", sa.DateTime(timezone=True))
    )
    op.create_unique_constraint(
        "uq_notification_observation", "notifications", ["expectation_id", "dedupe_key"]
    )
    op.create_table(
        "integration_credentials",
        sa.Column("connection_id", UUID(), primary_key=True),
        sa.Column("user_id", UUID(), nullable=False),
        sa.Column("encrypted_tokens", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["connection_id", "user_id"],
            ["integration_connections.id", "integration_connections.user_id"],
            name="fk_credential_owner",
            ondelete="CASCADE",
        ),
    )
    op.create_table(
        "provider_oauth_states",
        sa.Column("state_digest", sa.String(64), primary_key=True),
        sa.Column("connection_id", UUID(), nullable=False),
        sa.Column("user_id", UUID(), nullable=False),
        sa.Column("encrypted_verifier", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["connection_id", "user_id"],
            ["integration_connections.id", "integration_connections.user_id"],
            name="fk_oauth_owner",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_provider_oauth_states_expires_at", "provider_oauth_states", ["expires_at"]
    )
    # Never grant browser roles SELECT on encrypted credentials or PKCE material.
    for table in ("integration_credentials", "provider_oauth_states"):
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON public.{table} FROM PUBLIC")
        op.execute(f"""DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
            REVOKE ALL ON public.{table} FROM anon, authenticated;
            GRANT ALL ON public.{table} TO service_role;
          END IF;
        END $$""")


def downgrade():
    op.drop_table("provider_oauth_states")
    op.drop_table("integration_credentials")
    op.drop_constraint("uq_notification_observation", "notifications")
    op.drop_column("notifications", "acknowledged_at")
    op.drop_column("notifications", "dedupe_key")
    op.drop_constraint("uq_evaluation_run", "evaluations")
    op.drop_column("evaluations", "idempotency_key")
    op.drop_constraint("fk_job_owned_connection", "monitoring_jobs")
    op.drop_constraint("ck_job_schedule", "monitoring_jobs")
    op.drop_index("ix_monitoring_jobs_lease_expires_at", "monitoring_jobs")
    for column in (
        "provider_config",
        "connection_id",
        "lease_expires_at",
        "lease_token",
        "run_key",
        "max_attempts",
        "max_evidence_age_seconds",
        "window_start_at",
        "scheduled_at",
        "recurring",
        "interval_seconds",
    ):
        op.drop_column("monitoring_jobs", column)
    op.drop_constraint("uq_integration_owner", "integration_connections")
    op.drop_column("integration_connections", "oauth_generation")
