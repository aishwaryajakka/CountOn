"""Portable profiles and mandatory expectation ownership.

Revision ID: 2e0a91d54c31
Revises: 1bbc27e27689
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '2e0a91d54c31'
down_revision = '1bbc27e27689'
branch_labels = None
depends_on = None


def upgrade():
    # Abort atomically before assigning invented identities to legacy rows.
    op.execute('LOCK TABLE public.expectations IN ACCESS EXCLUSIVE MODE')
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM public.expectations) THEN
        RAISE EXCEPTION 'Ownership backfill required: export and map existing expectations to verified profile UUIDs before applying this migration';
      END IF;
    END $$""")
    op.create_table('profiles',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('display_name', sa.String(255), nullable=True),
        sa.Column('timezone', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.alter_column('expectations', 'user_id', nullable=False, existing_type=postgresql.UUID())
    op.create_foreign_key('fk_expectations_profile', 'expectations', 'profiles', ['user_id'], ['id'], ondelete='CASCADE')
    # ix_expectations_user_id already exists in the initial migration.


def downgrade():
    op.drop_constraint('fk_expectations_profile', 'expectations', type_='foreignkey')
    op.alter_column('expectations', 'user_id', nullable=True, existing_type=postgresql.UUID())
    op.drop_table('profiles')
