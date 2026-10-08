"""Opt-in PostgreSQL API tests; never migrate the application's database.

TEST_DATABASE_URL must name a distinct database ending in `_test`.
Migrations are applied once, then each test runs in an outer transaction that
is rolled back; service commits release savepoints rather than test isolation.
"""

import os
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_current_user
from app.core.auth import AuthenticatedUser
from app.repositories.profile import ensure_profile
from app.core.config import get_settings
from app.main import app


@pytest.fixture(scope="session")
def postgres_engine():
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("Set TEST_DATABASE_URL to a dedicated PostgreSQL database ending in _test")
    url = make_url(database_url)
    application_url = make_url(get_settings().database_url)
    # Require a different database name even when host aliases differ.
    same_database = url.database == application_url.database
    if (url.drivername != "postgresql+psycopg" or url.host not in ("localhost", "127.0.0.1", "::1")
            or not (url.database or "").endswith("_test") or same_database):
        pytest.fail("TEST_DATABASE_URL must use postgresql+psycopg, loopback PostgreSQL, and a separate database ending in _test")
    engine = create_engine(url, pool_pre_ping=True)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db(postgres_engine):
    with postgres_engine.connect() as connection:
        transaction = connection.begin()
        session = Session(
            bind=connection, join_transaction_mode="create_savepoint",
            autoflush=False, expire_on_commit=False,
        )
        try:
            yield session
        finally:
            session.close()
            transaction.rollback()


@pytest.fixture
def users(db):
    identities = [AuthenticatedUser(UUID('10000000-0000-4000-8000-000000000001')),
                  AuthenticatedUser(UUID('10000000-0000-4000-8000-000000000002'))]
    for user in identities:
        ensure_profile(db, user.id)
    return identities


@pytest.fixture
def client(db, users):
    def override_get_db():
        yield db

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: users[0]
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def numeric_payload():
    return {
        "claim": "My next electricity bill will be lower",
        "type": "numeric_comparison", "metric": "total_cost",
        "comparison": "less_than", "baseline": 142.10,
        "evidence_sources": ["utility_bill", "utility_usage", "tariff", "weather"],
        "materiality_threshold": 0.05,
    }


@pytest.fixture
def bill_payload():
    return {
        "source": "utility_bill", "metric": "total_cost", "value": {"amount": 162},
        "unit": "USD", "observed_at": "2026-10-02T12:00:00Z", "confidence": 1.0,
    }
