"""Add encrypted OAuth credentials.

Revision ID: e8b2dc123ad7
Revises: 501e82ab1613
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8b2dc123ad7"
down_revision: Union[str, Sequence[str], None] = "501e82ab1613"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "oauth_credentials",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("integration_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("access_token_encrypted", sa.String(), nullable=False),
        sa.Column("refresh_token_encrypted", sa.String(), nullable=True),
        sa.Column(
            "token_type",
            sa.String(length=40),
            nullable=False,
            server_default="Bearer",
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scopes", sa.String(), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "provider IN ('google', 'microsoft')",
            name="ck_oauth_credential_provider",
        ),
        sa.ForeignKeyConstraint(
            ["integration_id"],
            ["integration_connections.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["profiles.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "integration_id",
            name="uq_oauth_credential_integration",
        ),
    )

    op.create_index(
        "ix_oauth_credential_owner_provider",
        "oauth_credentials",
        ["user_id", "provider"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_oauth_credential_owner_provider",
        table_name="oauth_credentials",
    )
    op.drop_table("oauth_credentials")
