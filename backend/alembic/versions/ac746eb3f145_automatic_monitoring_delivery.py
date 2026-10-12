"""Automatic monitoring coverage and durable notification delivery.

Revision ID: ac746eb3f145
Revises: 9b635da2e034
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "ac746eb3f145"
down_revision: str | Sequence[str] | None = "9b635da2e034"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for field in (
        "coverage_start_at",
        "coverage_through_at",
        "round_started_at",
        "wake_requested_at",
    ):
        op.add_column(
            "provider_sync_states",
            sa.Column(field, sa.DateTime(timezone=True), nullable=True),
        )
    op.alter_column(
        "notifications", "evaluation_id", existing_type=sa.UUID(), nullable=True
    )
    op.create_unique_constraint(
        "uq_notification_owner", "notifications", ["id", "user_id"]
    )
    op.create_table(
        "notification_preferences",
        sa.Column(
            "user_id",
            sa.UUID(),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "email_enabled", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column("encrypted_recipient", sa.Text()),
        sa.Column(
            "mismatch_enabled", sa.Boolean(), nullable=False, server_default="true"
        ),
        sa.Column(
            "deadline_enabled", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "connection_enabled", sa.Boolean(), nullable=False, server_default="true"
        ),
        sa.Column(
            "quiet_enabled", sa.Boolean(), nullable=False, server_default="false"
        ),
        sa.Column(
            "quiet_start_hour", sa.Integer(), nullable=False, server_default="22"
        ),
        sa.Column("quiet_end_hour", sa.Integer(), nullable=False, server_default="8"),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="UTC"),
        sa.CheckConstraint(
            "quiet_start_hour BETWEEN 0 AND 23 AND quiet_end_hour BETWEEN 0 AND 23",
            name="ck_preference_hours",
        ),
    )
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("notification_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False, server_default="email"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column(
            "next_run_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("lease_token", sa.UUID()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_attempt_at", sa.DateTime(timezone=True)),
        sa.Column("encrypted_payload", sa.Text()),
        sa.Column("last_error", sa.String(50)),
        sa.Column("sent_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["notification_id", "user_id"],
            ["notifications.id", "notifications.user_id"],
            ondelete="CASCADE",
            name="fk_delivery_owner",
        ),
        sa.UniqueConstraint("notification_id", "channel", name="uq_delivery_channel"),
        sa.CheckConstraint(
            "channel = 'email' AND status IN ('pending','running','sent','failed','cancelled')",
            name="ck_delivery_status",
        ),
    )
    op.create_index(
        "ix_delivery_due", "notification_deliveries", ["status", "next_run_at"]
    )
    for table in ("notification_preferences", "notification_deliveries"):
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON public.{table} FROM PUBLIC")
        for role in ("anon", "authenticated"):
            op.execute(
                f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='{role}') THEN REVOKE ALL ON public.{table} FROM {role}; END IF; END $$"
            )
        op.execute(
            f"DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='service_role') THEN GRANT ALL ON public.{table} TO service_role; END IF; END $$"
        )


def downgrade() -> None:
    # Refuse destructive rollback if warnings without an evaluation exist.
    # Operators export/archive these rows explicitly before rollback.
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM notifications WHERE evaluation_id IS NULL) THEN RAISE EXCEPTION 'Archive evaluation-free notifications before downgrade'; END IF; END $$"
    )
    op.drop_table("notification_deliveries")
    op.drop_table("notification_preferences")
    op.drop_constraint("uq_notification_owner", "notifications", type_="unique")
    op.alter_column(
        "notifications", "evaluation_id", existing_type=sa.UUID(), nullable=False
    )
    for field in (
        "wake_requested_at",
        "round_started_at",
        "coverage_through_at",
        "coverage_start_at",
    ):
        op.drop_column("provider_sync_states", field)
