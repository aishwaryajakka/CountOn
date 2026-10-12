"""Readiness diagnoses fail closed and never expose driver/configuration payloads."""

import json
import logging
from unittest.mock import Mock

import pytest
from sqlalchemy.exc import OperationalError, TimeoutError

from app.core.logging import StructuredFormatter
from app.db.base import Base
from app.services import readiness


class Schema:
    def __init__(self, *, missing_table=None, revision="8a524c91df23", missing_column=None):
        self.tables = set(Base.metadata.tables) | {"alembic_version"}
        self.tables.discard(missing_table)
        self.revision = revision
        self.columns = {(name, column.name) for name, table in Base.metadata.tables.items() for column in table.columns}
        self.columns.discard(missing_column)
        self.queries = []

    def execute(self, statement):
        self.queries.append(str(statement))
        return self.columns if "information_schema.columns" in str(statement) else None

    def scalars(self, statement):
        self.queries.append(str(statement))
        return self.tables if "information_schema.tables" in str(statement) else [self.revision]


@pytest.fixture(autouse=True)
def head(monkeypatch, request):
    # Unit schemas use a fixed fixture revision; real DB tests validate the actual packaged head.
    if "db" not in request.fixturenames:
        monkeypatch.setattr(readiness, "expected_revisions", lambda: {"8a524c91df23"})


def test_ready_checks_all_registered_tables_columns_and_revision():
    db = Schema()
    assert readiness.inspect_readiness(db).ready
    assert all("SELECT" in q or q == "SET LOCAL statement_timeout = 1000" for q in db.queries)


def test_missing_conversation_table_reports_drift_and_observed_revision():
    report = readiness.inspect_readiness(Schema(missing_table="conversation_records", revision="6e302a79bd01"))
    assert report.code == "SCHEMA_TABLES_MISSING"
    assert report.missing_tables == ("conversation_records",)
    assert report.observed == ("6e302a79bd01",)
    assert not report.ready


def test_revision_mismatch_even_when_all_tables_exist():
    assert readiness.inspect_readiness(Schema(revision="6e302a79bd01")).code == "SCHEMA_REVISION_MISMATCH"


def test_stamped_head_without_monitoring_column_fails():
    result = readiness.inspect_readiness(Schema(missing_column=("monitoring_jobs", "lease_token")))
    assert result.code == "SCHEMA_COLUMNS_MISSING"
    assert result.missing_columns == ("monitoring_jobs.lease_token",)


def test_missing_alembic_table_does_not_query_it():
    db = Schema(missing_table="alembic_version")
    result = readiness.inspect_readiness(db)
    assert result.observed == ()
    assert not any("FROM public.alembic_version" in q for q in db.queries)


def test_corrupted_revision_cannot_inject_log_content(caplog):
    with caplog.at_level(logging.WARNING):
        assert not readiness.database_ready(Schema(revision="password=private-secret\nforged log"))
    formatted = StructuredFormatter().format(caplog.records[-1])
    assert "private-secret" not in formatted
    assert json.loads(formatted)["observed_revisions"] == ["INVALID_REVISION"]


@pytest.mark.parametrize("state,message,code", [
    ("28P01", "password=private-secret", "DATABASE_AUTHENTICATION"),
    ("42501", "private SQL", "DATABASE_PERMISSION"),
    ("57014", "private SQL", "DATABASE_QUERY_TIMEOUT"),
    (None, "certificate error private-secret", "DATABASE_TLS"),
    (None, "could not resolve private-host", "DATABASE_DNS"),
    (None, "connection timeout private-host", "DATABASE_CONNECTION_TIMEOUT"),
    (None, "connection refused private-host", "DATABASE_UNAVAILABLE"),
])
def test_driver_failures_are_classified_without_payload(state, message, code, caplog):
    original = Exception(message)
    original.sqlstate = state
    db = Mock()
    db.execute.side_effect = OperationalError("private SQL", {}, original)
    with caplog.at_level(logging.WARNING):
        assert not readiness.database_ready(db)
    record = caplog.records[-1]
    assert record.readiness_code == code
    assert "private" not in StructuredFormatter().format(record)
    db.rollback.assert_called_once()


def test_pool_timeout_and_failed_rollback_still_fail_closed():
    db = Mock()
    db.execute.side_effect = TimeoutError("private pool")
    db.rollback.side_effect = OperationalError("private SQL", {}, Exception("private"))
    assert readiness.inspect_readiness(db).code == "DATABASE_POOL_TIMEOUT"


def test_missing_packaged_migrations_fail_closed(monkeypatch):
    monkeypatch.setattr(readiness, "expected_revisions", Mock(side_effect=ValueError("private path")))
    db = Mock()
    assert readiness.inspect_readiness(db).code == "MIGRATION_FILES_UNAVAILABLE"
    db.execute.assert_not_called()


def test_real_migrated_database_ready(db):
    assert readiness.inspect_readiness(db).ready


def test_schema_cli_includes_backend_only_tables_and_diagnostics(monkeypatch, capsys):
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "db/scripts"))
    from db.scripts import check_schema
    engine = Mock()
    monkeypatch.setattr("app.db.session.engine", engine)
    # A real context-manager mock avoids touching any configured database.
    session = Mock()
    session.__enter__ = Mock(return_value=Schema(missing_table="conversation_records", revision="6e302a79bd01"))
    session.__exit__ = Mock(return_value=False)
    monkeypatch.setattr("sqlalchemy.orm.Session", lambda _: session)
    assert check_schema.main() == 1
    output = capsys.readouterr().out
    assert "FAIL conversation_records" in output
    assert "PASS compilation_sessions" in output
    assert "6e302a79bd01" in output and "8a524c91df23" in output
    assert "SCHEMA_TABLES_MISSING" in output
    engine.dispose.assert_called_once()
