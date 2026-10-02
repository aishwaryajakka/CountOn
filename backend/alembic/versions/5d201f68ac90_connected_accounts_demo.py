"""Connected accounts and expanded application contracts, with Supabase policies.

Revision ID: 5d201f68ac90
Revises: 4bc128091ea7
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY,JSONB,UUID

revision='5d201f68ac90'
down_revision='4bc128091ea7'
branch_labels=None
depends_on=None


def upgrade():
    op.add_column('profiles',sa.Column('demo_tag',sa.String(64),nullable=True))
    op.create_table('integration_connections',
        sa.Column('id',UUID(),primary_key=True),
        sa.Column('user_id',UUID(),sa.ForeignKey('profiles.id',ondelete='CASCADE'),nullable=False),
        sa.Column('provider',sa.String(20),nullable=False),sa.Column('connection_type',sa.String(20),nullable=False),
        sa.Column('external_account_id',sa.String(255),nullable=True),sa.Column('display_name',sa.String(255),nullable=True),
        sa.Column('status',sa.String(20),nullable=False,server_default='pending'),
        sa.Column('scopes',ARRAY(sa.String(100)),nullable=False,server_default=sa.text('ARRAY[]::varchar[]')),
        sa.Column('metadata',JSONB(),nullable=False,server_default=sa.text("'{}'::jsonb")),
        sa.Column('last_synced_at',sa.DateTime(timezone=True),nullable=True),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False,server_default=sa.func.now()),
        sa.CheckConstraint("provider IN ('google','microsoft','ring','bee','utility','delivery')",name='ck_integration_provider'),
        sa.CheckConstraint("connection_type IN ('email','calendar','camera','wearable','utility','delivery')",name='ck_integration_type'),
        sa.CheckConstraint("status IN ('pending','connected','disconnected','error')",name='ck_integration_status'))
    op.create_index('ix_integration_connections_user_id','integration_connections',['user_id'])
    op.create_index('ix_integration_owner_filters','integration_connections',['user_id','provider','connection_type','status'])
    op.add_column('notifications',sa.Column('user_id',UUID(),nullable=True))
    op.execute('UPDATE public.notifications n SET user_id=e.user_id FROM public.expectations e WHERE e.id=n.expectation_id')
    op.alter_column('notifications','user_id',nullable=False)
    op.create_foreign_key('fk_notification_profile','notifications','profiles',['user_id'],['id'],ondelete='CASCADE')
    op.create_foreign_key('fk_notification_owner','notifications','expectations',['expectation_id','user_id'],['id','user_id'],ondelete='CASCADE')
    for name,type_,default in [('type',sa.String(50),'expectation_mismatch'),('channel',sa.String(20),'in_app'),
        ('message',sa.String(500),'An expectation was contradicted by the latest evidence.')]:
        op.add_column('notifications',sa.Column(name,type_,nullable=False,server_default=default))
    op.add_column('notifications',sa.Column('metadata',JSONB(),nullable=False,server_default=sa.text("'{}'::jsonb")))
    op.add_column('notifications',sa.Column('sent_at',sa.DateTime(timezone=True),nullable=True))
    op.drop_constraint('ck_notification_status','notifications',type_='check')
    op.create_check_constraint('ck_notification_status','notifications',"status IN ('pending','read','sent','failed','dismissed')")
    op.create_index('ix_notification_owner_created','notifications',['user_id','created_at'])
    op.add_column('audit_events',sa.Column('entity_type',sa.String(50),nullable=False,server_default='expectation'))
    op.add_column('audit_events',sa.Column('metadata',JSONB(),nullable=False,server_default=sa.text("'{}'::jsonb")))
    op.execute("UPDATE public.audit_events SET entity_type=CASE WHEN action LIKE 'evidence.%' THEN 'evidence' WHEN action='expectation.evaluated' THEN 'evaluation' ELSE 'expectation' END")
    op.create_index('ix_audit_owner_created','audit_events',['user_id','created_at'])
    op.add_column('evidence',sa.Column('external_event_id',sa.String(255),nullable=True))
    op.create_index('uq_evidence_external_event','evidence',['expectation_id','source','external_event_id'],unique=True,postgresql_where=sa.text('external_event_id IS NOT NULL'))
    op.execute("""DO $$ BEGIN
      IF to_regclass('auth.users') IS NOT NULL AND to_regprocedure('auth.uid()') IS NOT NULL THEN
        ALTER TABLE public.integration_connections ENABLE ROW LEVEL SECURITY;
        REVOKE ALL ON public.integration_connections FROM PUBLIC, anon, authenticated;
        GRANT SELECT ON public.integration_connections TO authenticated;
        GRANT ALL ON public.integration_connections TO service_role;
        CREATE POLICY integration_owner_select ON public.integration_connections FOR SELECT TO authenticated USING ((SELECT auth.uid())=user_id);
        -- Writes remain backend-only so metadata validation and audits cannot be bypassed.
      END IF;
    END $$""")


def downgrade():
    # Refuse lossy conversion of new lifecycle states instead of silently rewriting history.
    op.execute("""DO $$ BEGIN
      IF EXISTS (SELECT 1 FROM public.notifications WHERE status NOT IN ('pending','read')) THEN
        RAISE EXCEPTION 'Notification lifecycle export/backfill required before downgrade';
      END IF;
    END $$""")
    op.drop_index('uq_evidence_external_event',table_name='evidence')
    op.drop_column('evidence','external_event_id')
    op.drop_index('ix_audit_owner_created',table_name='audit_events')
    op.drop_column('audit_events','metadata');op.drop_column('audit_events','entity_type')
    op.drop_index('ix_notification_owner_created',table_name='notifications')
    op.drop_constraint('ck_notification_status','notifications',type_='check')
    op.create_check_constraint('ck_notification_status','notifications',"status IN ('pending','read')")
    op.drop_constraint('fk_notification_owner','notifications',type_='foreignkey')
    op.drop_constraint('fk_notification_profile','notifications',type_='foreignkey')
    for name in ('user_id','type','channel','message','metadata','sent_at'):
        op.drop_column('notifications',name)
    op.drop_table('integration_connections')
    op.drop_column('profiles','demo_tag')
