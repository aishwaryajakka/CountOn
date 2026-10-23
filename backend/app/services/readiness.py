"""Read-only schema readiness with bounded, credential-free internal diagnostics."""

import logging
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError, TimeoutError
from sqlalchemy.orm import Session

from app.db import models  # noqa: F401 -- readiness also works outside API startup
from app.db.base import Base

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Readiness:
    code: str
    missing_tables: tuple[str, ...] = ()
    missing_columns: tuple[str, ...] = ()
    expected: tuple[str, ...] = ()
    observed: tuple[str, ...] = ()

    @property
    def ready(self) -> bool:
        return self.code == "READY"


@lru_cache
def expected_revisions() -> set[str]:
    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    return set(ScriptDirectory.from_config(config).get_heads())


def _revision(value: object) -> str:
    return value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_]{1,64}", value) else "INVALID_REVISION"


def _database_error(error: SQLAlchemyError) -> str:
    if isinstance(error, TimeoutError):
        return "DATABASE_POOL_TIMEOUT"
    original = getattr(error, "orig", None)
    state = getattr(original, "sqlstate", None)
    if state in ("28P01", "28000"):
        return "DATABASE_AUTHENTICATION"
    if state == "42501":
        return "DATABASE_PERMISSION"
    if state == "57014":
        return "DATABASE_QUERY_TIMEOUT"
    # Classify privately: driver messages may contain hosts, URLs or passwords.
    message = str(original).lower()
    if any(word in message for word in ("password authentication", "tenant or user not found")):
        return "DATABASE_AUTHENTICATION"
    if any(word in message for word in ("ssl", "tls", "certificate")):
        return "DATABASE_TLS"
    if any(word in message for word in ("resolve", "resolution", "nodename", "getaddrinfo")):
        return "DATABASE_DNS"
    if "timeout" in message or "timed out" in message:
        return "DATABASE_CONNECTION_TIMEOUT"
    return "DATABASE_UNAVAILABLE"


def inspect_readiness(db: Session) -> Readiness:
    try:
        expected = tuple(sorted(_revision(r) for r in expected_revisions()))
        if not expected:
            return Readiness("MIGRATION_FILES_UNAVAILABLE")
    except Exception:  # noqa: BLE001 -- configuration exceptions may contain private paths
        return Readiness("MIGRATION_FILES_UNAVAILABLE")
    try:
        db.execute(text("SET LOCAL statement_timeout = 1000"))
        required = set(Base.metadata.tables) | {"alembic_version"}
        found = set(db.scalars(text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")))
        missing = tuple(sorted(required - found))
        observed = tuple(sorted(_revision(r) for r in db.scalars(text("SELECT version_num FROM public.alembic_version")))) if "alembic_version" in found else ()
        if missing:
            return Readiness("SCHEMA_TABLES_MISSING", missing_tables=missing, expected=expected, observed=observed)
        if observed != expected:
            return Readiness("SCHEMA_REVISION_MISMATCH", expected=expected, observed=observed)
        columns = set(db.execute(text("SELECT table_name, column_name FROM information_schema.columns WHERE table_schema='public'")))
        missing_columns = tuple(sorted(f"{name}.{column.name}" for name, table in Base.metadata.tables.items() for column in table.columns if (name, column.name) not in columns))
        if missing_columns:
            return Readiness("SCHEMA_COLUMNS_MISSING", missing_columns=missing_columns, expected=expected, observed=observed)
        return Readiness("READY", expected=expected, observed=observed)
    except SQLAlchemyError as error:
        try:
            db.rollback()
        except SQLAlchemyError:
            pass  # disconnected sessions still fail closed
        return Readiness(_database_error(error), expected=expected)


def database_ready(db: Session) -> bool:
    result = inspect_readiness(db)
    if not result.ready:
        logger.warning("Database readiness failed", extra={
            "readiness_code": result.code,
            "missing_table_count": len(result.missing_tables),
            "missing_column_count": len(result.missing_columns),
            "expected_revisions": result.expected,
            "observed_revisions": result.observed,
        })
    return result.ready
