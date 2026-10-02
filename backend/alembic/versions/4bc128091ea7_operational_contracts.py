"""Operational persistence and Supabase RLS for the new tables.

Revision ID: 4bc128091ea7
Revises: 3a874e01bb52
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision='4bc128091ea7'
down_revision='3a874e01bb52'
branch_labels=None
depends_on=None


def timestamps():
    return [sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
            sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now())]


def upgrade():
    op.create_unique_constraint('uq_expectation_owner','expectations',['id','user_id'])
    op.create_unique_constraint('uq_evaluation_expectation','evaluations',['id','expectation_id'])
    op.add_column('evidence',sa.Column('idempotency_key',sa.String(128),nullable=True))
    op.create_unique_constraint('uq_evidence_idempotency','evidence',['expectation_id','idempotency_key'])
    op.create_table('monitoring_jobs',
        sa.Column('id',UUID(),primary_key=True),
        sa.Column('expectation_id',UUID(),nullable=False),sa.Column('user_id',UUID(),nullable=False),
        sa.Column('status',sa.String(20),nullable=False,server_default='pending'),
        sa.Column('next_run_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('last_run_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('attempt_count',sa.Integer(),nullable=False,server_default='0'),
        sa.Column('last_error',sa.String(100),nullable=True),*timestamps(),
        sa.ForeignKeyConstraint(['expectation_id','user_id'],['expectations.id','expectations.user_id'],ondelete='CASCADE',name='fk_job_owned_expectation'),
        sa.CheckConstraint("status IN ('pending','running','paused','completed','failed','cancelled')",name='ck_job_status'),
        sa.CheckConstraint('attempt_count >= 0',name='ck_job_attempts'))
    op.create_index('uq_job_active_expectation','monitoring_jobs',['expectation_id'],unique=True,postgresql_where=sa.text("status IN ('pending','running','paused')"))
    op.create_index('ix_job_due','monitoring_jobs',['status','next_run_at'])
    op.create_index('ix_monitoring_jobs_user_id','monitoring_jobs',['user_id'])
    op.create_table('notifications',sa.Column('id',UUID(),primary_key=True),
        sa.Column('expectation_id',UUID(),sa.ForeignKey('expectations.id',ondelete='CASCADE'),nullable=False),
        sa.Column('evaluation_id',UUID(),nullable=False),
        sa.Column('status',sa.String(20),nullable=False,server_default='pending'),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['evaluation_id','expectation_id'],['evaluations.id','evaluations.expectation_id'],ondelete='CASCADE',name='fk_notification_evaluation'),
        sa.UniqueConstraint('evaluation_id',name='uq_notification_evaluation'),
        sa.CheckConstraint("status IN ('pending','read')",name='ck_notification_status'))
    op.create_index('ix_notifications_expectation_id','notifications',['expectation_id'])
    op.create_table('audit_events',sa.Column('id',UUID(),primary_key=True),
        sa.Column('user_id',UUID(),sa.ForeignKey('profiles.id',ondelete='CASCADE'),nullable=False),
        sa.Column('expectation_id',UUID(),sa.ForeignKey('expectations.id',ondelete='SET NULL'),nullable=True),
        sa.Column('resource_id',UUID(),nullable=False),sa.Column('action',sa.String(50),nullable=False),
        sa.Column('request_id',sa.String(36),nullable=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()))
    op.create_index('ix_audit_events_user_id','audit_events',['user_id'])
    op.create_index('ix_audit_events_expectation_id','audit_events',['expectation_id'])
    op.execute("""DO $$ BEGIN
      IF to_regclass('auth.users') IS NOT NULL AND to_regprocedure('auth.uid()') IS NOT NULL THEN
        ALTER TABLE public.monitoring_jobs ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.notifications ENABLE ROW LEVEL SECURITY;
        ALTER TABLE public.audit_events ENABLE ROW LEVEL SECURITY;
        REVOKE ALL ON public.monitoring_jobs, public.notifications, public.audit_events FROM PUBLIC, anon, authenticated;
        GRANT SELECT ON public.monitoring_jobs, public.notifications, public.audit_events TO authenticated;
        GRANT ALL ON public.monitoring_jobs, public.notifications, public.audit_events TO service_role;
        CREATE POLICY monitoring_jobs_owner_select ON public.monitoring_jobs FOR SELECT TO authenticated USING ((SELECT auth.uid())=user_id);
        CREATE POLICY audit_events_owner_select ON public.audit_events FOR SELECT TO authenticated USING ((SELECT auth.uid())=user_id);
        CREATE POLICY notifications_owner_select ON public.notifications FOR SELECT TO authenticated USING (EXISTS (SELECT 1 FROM public.expectations p WHERE p.id=expectation_id AND p.user_id=(SELECT auth.uid())));
      END IF;
    END $$""")


def downgrade():
    # Only exercise in disposable local DBs: operational history is removed.
    for table in ('audit_events','notifications','monitoring_jobs'):
        op.drop_table(table)
    op.drop_constraint('uq_evidence_idempotency','evidence',type_='unique')
    op.drop_column('evidence','idempotency_key')
    op.drop_constraint('uq_evaluation_expectation','evaluations',type_='unique')
    op.drop_constraint('uq_expectation_owner','expectations',type_='unique')
