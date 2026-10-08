"""Exercise upgrade, ownership-backfill guard and downgrade in a new database."""
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import DBAPIError

pytestmark=pytest.mark.integration


def test_local_migration_cycle_and_backfill_guard(postgres_engine):
    name=f'counton_migration_{uuid4().hex}_test'
    with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
        allowed=admin.scalar(text('SELECT rolcreatedb OR rolsuper FROM pg_roles WHERE rolname=current_user'))
        if not allowed:
            pytest.skip('Migration cycle requires CREATEDB on the dedicated local test role')
        admin.execute(text(f'CREATE DATABASE "{name}"'))
    engine=create_engine(postgres_engine.url.set(database=name),pool_pre_ping=True)
    config=Config(str(Path(__file__).resolve().parents[1]/'alembic.ini'))
    def migrate(operation,revision):
        with engine.begin() as connection:
            config.attributes['connection']=connection
            operation(config,revision)
    try:
        migrate(command.upgrade,'1bbc27e27689')
        legacy_id=uuid4()
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO expectations (id,claim,type) VALUES (:id,'Migration guard fixture','boolean')"),{'id':legacy_id})
        with pytest.raises(DBAPIError,match='Ownership backfill required'):
            migrate(command.upgrade,'head')
        with engine.begin() as connection:
            assert connection.scalar(text('SELECT version_num FROM alembic_version'))=='1bbc27e27689'
            assert connection.scalar(text('SELECT count(*) FROM expectations WHERE id=:id'),{'id':legacy_id})==1
            assert 'profiles' not in inspect(connection).get_table_names()
            connection.execute(text('DELETE FROM expectations WHERE id=:id'),{'id':legacy_id})
        migrate(command.upgrade,'head')
        with engine.connect() as connection:
            inspector=inspect(connection)
            assert 'profiles' in inspector.get_table_names()
            assert not next(c for c in inspector.get_columns('expectations') if c['name']=='user_id')['nullable']
            fk=next(f for f in inspector.get_foreign_keys('expectations') if f['name']=='fk_expectations_profile')
            assert fk['referred_table']=='profiles'
            assert fk['options']['ondelete']=='CASCADE'
            assert connection.scalar(text("SELECT to_regclass('auth.users')")) is None
            assert connection.scalar(text("SELECT count(*) FROM pg_constraint WHERE conname='fk_profiles_auth_user'"))==0
        migrate(command.downgrade,'base')
        with engine.connect() as connection:
            assert set(inspect(connection).get_table_names())=={'alembic_version'}
        migrate(command.upgrade,'head')
    finally:
        engine.dispose()
        with postgres_engine.connect().execution_options(isolation_level='AUTOCOMMIT') as admin:
            admin.execute(text(f'DROP DATABASE "{name}"'))
