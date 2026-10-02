"""Supabase identity FK, grants and RLS; no-op on ordinary PostgreSQL.

Revision ID: 3a874e01bb52
Revises: 2e0a91d54c31
"""
from alembic import op

revision = '3a874e01bb52'
down_revision = '2e0a91d54c31'
branch_labels = None
depends_on = None

def upgrade():
    op.execute("""DO $$ BEGIN
      IF to_regclass('auth.users') IS NOT NULL AND to_regprocedure('auth.uid()') IS NOT NULL THEN
        ALTER TABLE public.profiles ADD CONSTRAINT fk_profiles_auth_user FOREIGN KEY (id) REFERENCES auth.users(id) ON DELETE CASCADE;
        ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
        REVOKE ALL ON public.profiles FROM PUBLIC, anon, authenticated;
        GRANT SELECT, INSERT, UPDATE ON public.profiles TO authenticated;
        GRANT ALL ON public.profiles TO service_role;
        CREATE POLICY profiles_owner_select ON public.profiles FOR SELECT TO authenticated USING ((SELECT auth.uid()) = id);
        CREATE POLICY profiles_owner_insert ON public.profiles FOR INSERT TO authenticated  WITH CHECK ((SELECT auth.uid()) = id);
        CREATE POLICY profiles_owner_update ON public.profiles FOR UPDATE TO authenticated USING ((SELECT auth.uid()) = id) WITH CHECK ((SELECT auth.uid()) = id);
        ALTER TABLE public.expectations ENABLE ROW LEVEL SECURITY;
        REVOKE ALL ON public.expectations FROM PUBLIC, anon, authenticated;
        GRANT SELECT, INSERT, UPDATE, DELETE ON public.expectations TO authenticated;
        GRANT ALL ON public.expectations TO service_role;
        CREATE POLICY expectations_owner_select ON public.expectations FOR SELECT TO authenticated USING ((SELECT auth.uid()) = user_id);
        CREATE POLICY expectations_owner_insert ON public.expectations FOR INSERT TO authenticated  WITH CHECK ((SELECT auth.uid()) = user_id);
        CREATE POLICY expectations_owner_update ON public.expectations FOR UPDATE TO authenticated USING ((SELECT auth.uid()) = user_id) WITH CHECK ((SELECT auth.uid()) = user_id);
        CREATE POLICY expectations_owner_delete ON public.expectations FOR DELETE TO authenticated USING ((SELECT auth.uid()) = user_id);
        ALTER TABLE public.evidence ENABLE ROW LEVEL SECURITY;
        REVOKE ALL ON public.evidence FROM PUBLIC, anon, authenticated;
        GRANT SELECT, INSERT ON public.evidence TO authenticated;
        GRANT ALL ON public.evidence TO service_role;
        CREATE POLICY evidence_owner_select ON public.evidence FOR SELECT TO authenticated USING (EXISTS (SELECT 1 FROM public.expectations AS parent WHERE parent.id = expectation_id AND parent.user_id = (SELECT auth.uid())));
        CREATE POLICY evidence_owner_insert ON public.evidence FOR INSERT TO authenticated  WITH CHECK (EXISTS (SELECT 1 FROM public.expectations AS parent WHERE parent.id = expectation_id AND parent.user_id = (SELECT auth.uid())));
        ALTER TABLE public.evaluations ENABLE ROW LEVEL SECURITY;
        REVOKE ALL ON public.evaluations FROM PUBLIC, anon, authenticated;
        GRANT SELECT ON public.evaluations TO authenticated;
        GRANT ALL ON public.evaluations TO service_role;
        CREATE POLICY evaluations_owner_select ON public.evaluations FOR SELECT TO authenticated USING (EXISTS (SELECT 1 FROM public.expectations AS parent WHERE parent.id = expectation_id AND parent.user_id = (SELECT auth.uid())));
      END IF;
    END $$""")


def downgrade():
    op.execute("""DO $$ BEGIN
      IF to_regclass('auth.users') IS NOT NULL AND to_regprocedure('auth.uid()') IS NOT NULL THEN
        DROP POLICY IF EXISTS profiles_owner_select ON public.profiles;
        DROP POLICY IF EXISTS profiles_owner_insert ON public.profiles;
        DROP POLICY IF EXISTS profiles_owner_update ON public.profiles;
        REVOKE ALL ON public.profiles FROM anon, authenticated;
        ALTER TABLE public.profiles DISABLE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS expectations_owner_select ON public.expectations;
        DROP POLICY IF EXISTS expectations_owner_insert ON public.expectations;
        DROP POLICY IF EXISTS expectations_owner_update ON public.expectations;
        DROP POLICY IF EXISTS expectations_owner_delete ON public.expectations;
        REVOKE ALL ON public.expectations FROM anon, authenticated;
        ALTER TABLE public.expectations DISABLE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS evidence_owner_select ON public.evidence;
        DROP POLICY IF EXISTS evidence_owner_insert ON public.evidence;
        REVOKE ALL ON public.evidence FROM anon, authenticated;
        ALTER TABLE public.evidence DISABLE ROW LEVEL SECURITY;
        DROP POLICY IF EXISTS evaluations_owner_select ON public.evaluations;
        REVOKE ALL ON public.evaluations FROM anon, authenticated;
        ALTER TABLE public.evaluations DISABLE ROW LEVEL SECURITY;
        ALTER TABLE public.profiles DROP CONSTRAINT IF EXISTS fk_profiles_auth_user;
      END IF;
    END $$""")
