"""Encrypted durable agent/Alexa state and isolate OAuth clients from direct SQL."""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision = "8a524c91df23"
down_revision = "7f413b80ce12"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "conversation_records",
        sa.Column("record_key", sa.String(64), primary_key=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column(
            "user_id",
            UUID(),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reference_digest", sa.String(64), unique=True),
        sa.Column("encrypted_payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_token", UUID()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("kind IN ('agent','alexa')", name="ck_conversation_kind"),
    )
    op.create_index(
        "ix_conversation_records_user_id", "conversation_records", ["user_id"]
    )
    op.create_index("ix_conversation_expiry", "conversation_records", ["expires_at"])
    op.execute("ALTER TABLE public.conversation_records ENABLE ROW LEVEL SECURITY")
    op.execute("REVOKE ALL ON public.conversation_records FROM PUBLIC")
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        REVOKE ALL ON public.conversation_records FROM anon, authenticated;
        GRANT ALL ON public.conversation_records TO service_role;
      END IF;
    END $$""")
    # Linked third-party clients act through verified CountOn services only.
    # Restrictive policies combine with existing owner policies, preserving web JWTs.
    for table in (
        "profiles",
        "expectations",
        "evidence",
        "evaluations",
        "monitoring_jobs",
        "notifications",
        "audit_events",
        "integration_connections",
        "compilation_sessions",
    ):
        op.execute(f"""DO $$ BEGIN
          IF to_regprocedure('auth.jwt()') IS NOT NULL THEN
            CREATE POLICY counton_oauth_no_direct_sql ON public.{table}
            AS RESTRICTIVE FOR ALL TO authenticated
            USING ((auth.jwt()->>'client_id') IS NULL)
            WITH CHECK ((auth.jwt()->>'client_id') IS NULL);
          END IF;
        END $$""")


def downgrade():
    for table in (
        "profiles",
        "expectations",
        "evidence",
        "evaluations",
        "monitoring_jobs",
        "notifications",
        "audit_events",
        "integration_connections",
        "compilation_sessions",
    ):
        op.execute(
            f"DROP POLICY IF EXISTS counton_oauth_no_direct_sql ON public.{table}"
        )
    op.drop_table("conversation_records")
