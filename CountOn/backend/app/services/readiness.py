"""Read-only readiness checks against the current Alembic head."""
from functools import lru_cache
from pathlib import Path
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from app.db.base import Base


@lru_cache
def expected_revisions():
    config=Config(str(Path(__file__).resolve().parents[2]/'alembic.ini'))
    return set(ScriptDirectory.from_config(config).get_heads())


def database_ready(db):
    try:
        db.execute(text('SET LOCAL statement_timeout = 1000'))
        required=set(Base.metadata.tables)
        found=set(db.scalars(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")))
        if not required <= found or 'alembic_version' not in found:
            return False
        revisions=set(db.scalars(text('SELECT version_num FROM public.alembic_version')))
        return revisions==expected_revisions()
    except SQLAlchemyError:
        db.rollback()
        return False
