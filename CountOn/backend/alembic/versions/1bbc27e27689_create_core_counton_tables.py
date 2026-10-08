"""create_core_counton_tables

Revision ID: 1bbc27e27689
Revises: 
Create Date: 2026-10-01 14:54:38.720312
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '1bbc27e27689'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('expectations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=True),
        sa.Column('claim', sa.Text(), nullable=False),
        sa.Column('type', sa.Enum('numeric_comparison', 'boolean', 'temporal', 'event', name='expectation_type'), nullable=False),
        sa.Column('metric', sa.String(length=100), nullable=True),
        sa.Column('comparison', sa.Enum('less_than', 'less_than_or_equal', 'greater_than', 'greater_than_or_equal', 'equal', 'not_equal', name='comparison_type'), nullable=True),
        sa.Column('baseline', sa.Numeric(), nullable=True),
        sa.Column('target_value', sa.Numeric(), nullable=True),
        sa.Column('deadline', sa.DateTime(timezone=True), nullable=True),
        sa.Column('evidence_sources', postgresql.ARRAY(sa.String()), server_default=sa.text('ARRAY[]::varchar[]'), nullable=False),
        sa.Column('materiality_threshold', sa.Float(), server_default='0.05', nullable=False),
        sa.Column('status', sa.Enum('monitoring', 'fulfilled', 'contradicted', 'unknown', 'resolved', 'cancelled', name='expectation_status'), server_default='monitoring', nullable=False),
        sa.Column('compiler_metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_expectations_status'), 'expectations', ['status'], unique=False)
    op.create_index(op.f('ix_expectations_user_id'), 'expectations', ['user_id'], unique=False)
    op.create_table('evaluations',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('expectation_id', sa.UUID(), nullable=False),
        sa.Column('result', sa.Enum('MATCH', 'UNKNOWN', 'MISMATCH', name='evaluation_result'), nullable=False),
        sa.Column('expected', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('observed', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('confidence', sa.Float(), server_default='1.0', nullable=False),
        sa.Column('reasoning', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['expectation_id'], ['expectations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_evaluations_expectation_id'), 'evaluations', ['expectation_id'], unique=False)
    op.create_index(op.f('ix_evaluations_result'), 'evaluations', ['result'], unique=False)
    op.create_table('evidence',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('expectation_id', sa.UUID(), nullable=False),
        sa.Column('source', sa.String(length=100), nullable=False),
        sa.Column('metric', sa.String(length=100), nullable=True),
        sa.Column('value', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('unit', sa.String(length=50), nullable=True),
        sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('confidence', sa.Float(), server_default='1.0', nullable=False),
        sa.Column('raw_data', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['expectation_id'], ['expectations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_evidence_expectation_id'), 'evidence', ['expectation_id'], unique=False)
    op.create_index(op.f('ix_evidence_source'), 'evidence', ['source'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_evidence_source'), table_name='evidence')
    op.drop_index(op.f('ix_evidence_expectation_id'), table_name='evidence')
    op.drop_table('evidence')
    op.drop_index(op.f('ix_evaluations_result'), table_name='evaluations')
    op.drop_index(op.f('ix_evaluations_expectation_id'), table_name='evaluations')
    op.drop_table('evaluations')
    op.drop_index(op.f('ix_expectations_user_id'), table_name='expectations')
    op.drop_index(op.f('ix_expectations_status'), table_name='expectations')
    op.drop_table('expectations')
    # Table removal does not automatically drop PostgreSQL enum types.
    for name in ("evaluation_result", "expectation_status", "comparison_type", "expectation_type"):
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
