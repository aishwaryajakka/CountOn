"""Exercise Supabase-aware RLS in a disposable DB, not on the live project."""
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from alembic import command
from app.schemas.expectation import ExpectationCreate
from app.services.expectation_service import create_expectation

pytestmark = pytest.mark.integration


def test_supabase_identity_fk_and_owner_rls(postgres_engine):
    name = 'counton_auth_rls_' + uuid4().hex + '_test'
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
        for role in ('anon', 'authenticated', 'service_role'):
            if not admin.scalar(text('SELECT 1 FROM pg_roles WHERE rolname=:name'), {'name': role}):
                admin.execute(text('CREATE ROLE ' + role + ' NOLOGIN'))
        admin.execute(text(f'CREATE DATABASE "{name}"'))
    engine = create_engine(postgres_engine.url.set(database=name))
    first, second = uuid4(), uuid4()
    try:
        with engine.begin() as db:
            db.execute(text('CREATE SCHEMA auth'))
            db.execute(text('CREATE TABLE auth.users (id uuid PRIMARY KEY)'))
            db.execute(text("CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT nullif(current_setting('request.jwt.claim.sub',true),'')::uuid $$"))
            db.execute(text("CREATE FUNCTION auth.jwt() RETURNS jsonb LANGUAGE sql STABLE AS $$ SELECT '{}'::jsonb $$"))
            db.execute(text('GRANT USAGE ON SCHEMA auth TO authenticated'))
            db.execute(text('INSERT INTO auth.users(id) VALUES (:a),(:b)'), {'a': first, 'b': second})
            config = Config(str(Path(__file__).resolve().parents[1] / 'alembic.ini'))
            config.attributes['connection'] = db
            command.upgrade(config, 'head')
        with Session(engine) as db:
            a = create_expectation(db, ExpectationCreate(claim='Owned A', type='boolean', metric='confirmed'), first)
            b = create_expectation(db, ExpectationCreate(claim='Owned B', type='boolean', metric='confirmed'), second)
            aid, bid = a.id, b.id
        with engine.connect() as db:
            db.execute(text('SET ROLE authenticated'))
            db.execute(text("SELECT set_config('request.jwt.claim.sub',:id,false)"), {'id': str(first)})
            assert db.execute(text('SELECT id FROM expectations')).scalars().all() == [aid]
            assert db.execute(text('SELECT id FROM profiles')).scalars().all() == [first]
            assert db.execute(text('UPDATE expectations SET claim=\'Stolen\' WHERE id=:id'), {'id': bid}).rowcount == 0
        with engine.connect() as db:
            db.execute(text('SET ROLE authenticated'))
            db.execute(text("SELECT set_config('request.jwt.claim.sub',:id,false)"), {'id': str(first)})
            insert = text("INSERT INTO evidence(id,expectation_id,source,value,observed_at,raw_data) VALUES (:row,:id,'ring_simulator','{}',now(),'{}')")
            assert db.execute(insert, {'row': uuid4(), 'id': aid}).rowcount == 1
            with pytest.raises(DBAPIError) as denied:
                db.execute(insert, {'row': uuid4(), 'id': bid})
            assert denied.value.orig.sqlstate == '42501'  # RLS denial, not a missing default.
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
            admin.execute(text(f'DROP DATABASE "{name}"'))
