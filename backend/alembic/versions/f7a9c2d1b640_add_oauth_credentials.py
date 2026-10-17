
"""Add encrypted OAuth credentials and one-time OAuth state storage."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "f7a9c2d1b640"
down_revision = "5d201f68ac90"
branch_labels = None
depends_on = None


def _table_exists(table_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return inspector.has_table(table_name, schema="public")


def upgrade() -> None:
    # Preserve existing Supabase tables and their data.
    if not _table_exists("oauth_credentials"):
        op.create_table(
            "oauth_credentials",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "integration_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("integration_connections.id", ondelete="CASCADE"),
                nullable=False,
                unique=True,
            ),
            sa.Column(
                "user_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("profiles.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("provider", sa.String(50), nullable=False),
            sa.Column("access_token_encrypted", sa.String(), nullable=False),
            sa.Column("refresh_token_encrypted", sa.String(), nullable=True),
            sa.Column("token_type", sa.String(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("scopes", sa.String(), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

        op.create_index(
            "ix_oauth_credential_owner_provider",
            "oauth_credentials",
            ["user_id", "provider"],
        )

    if not _table_exists("oauth_states"):
        op.create_table(
            "oauth_states",
            sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column(
                "user_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("profiles.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("provider", sa.String(50), nullable=False),
            sa.Column("state_hash", sa.String(64), nullable=False, unique=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=False,
            ),
        )

        op.create_index(
            "ix_oauth_state_expiry",
            "oauth_states",
            ["expires_at"],
        )


def downgrade() -> None:
    if _table_exists("oauth_states"):
        op.drop_table("oauth_states")

    if _table_exists("oauth_credentials"):
        op.drop_table("oauth_credentials")
