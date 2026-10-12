"""Restore an isolated loopback *_test backup; never uses application/production DB.

Requires quiescent test PostgreSQL, pg_dump/pg_restore, and local CREATEDB permission.
Adds one tagged fixture, restores to a generated database, and cleans only its own data.
No archive, password, private row or database URL is printed or retained.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import Evaluation, Evidence, Expectation, Notification, Profile
from app.schemas.evidence import EvidenceCreate
from app.schemas.expectation import ExpectationCreate
from app.services import evaluation_service, evidence_service, expectation_service


def test_url(value, application_database):
    url = make_url(value)
    if (
        url.drivername != "postgresql+psycopg"
        or url.host not in ("localhost", "127.0.0.1", "::1")
        or not re.fullmatch(r"[A-Za-z0-9_]+_test", url.database or "")
        or url.database == application_database
        or url.query
    ):
        raise ValueError("Use a distinct loopback *_test database without URL options")
    return url


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--local-test", required=True, action="store_true")
    parser.parse_args()
    source = target = None
    owner, destination = uuid4(), "counton_restore_" + uuid4().hex + "_test"
    made = False
    result = 1
    try:
        url = test_url(
            os.environ["TEST_DATABASE_URL"],
            make_url(get_settings().database_url).database,
        )
        dump, restore = shutil.which("pg_dump"), shutil.which("pg_restore")
        if not dump or not restore:
            print("BLOCKED isolated restore: install matching PostgreSQL client tools")
            return 2
        # Explicit loopback address prevents inherited libpq PGHOSTADDR routing.
        connect_args = {"hostaddr": "::1" if url.host == "::1" else "127.0.0.1"}
        source = create_engine(url, pool_pre_ping=True, connect_args=connect_args)
        with Session(source) as db:
            row = expectation_service.create_expectation(
                db,
                ExpectationCreate(
                    claim="[counton-backup-smoke] local isolated fixture",
                    type="numeric_comparison",
                    metric="total_cost",
                    comparison="less_than",
                    baseline=142.1,
                ),
                owner,
            )
            evidence_service.add_evidence(
                db,
                row.id,
                EvidenceCreate(
                    source="utility_bill",
                    metric="total_cost",
                    value={"amount": 162},
                    unit="USD",
                    observed_at=datetime.now(timezone.utc),
                ),
                owner,
            )
            evaluation_service.evaluate_expectation(db, row.id, owner)
            identity = row.id
        # Pass credentials only through subprocess environment, never argv or output.
        environment = {
            **{
                k: v
                for k, v in os.environ.items()
                if k in {"PATH", "LANG", "LC_ALL", "SYSTEMROOT"}
            },
            "PGHOST": url.host,
            "PGPORT": str(url.port or 5432),
            "PGUSER": url.username or "",
            "PGPASSWORD": url.password or "",
            "PGDATABASE": url.database,
            "PGCONNECT_TIMEOUT": "5",
            "PGSSLMODE": "prefer",
        }
        with source.connect().execution_options(isolation_level="AUTOCOMMIT") as admin:
            admin.execute(text(f'CREATE DATABASE "{destination}"'))
            made = True
        with tempfile.TemporaryDirectory(prefix="counton-restore-") as folder:
            archive = Path(folder) / "isolated.dump"
            with archive.open("wb") as output:
                os.chmod(archive, 0o600)
                subprocess.run(
                    [dump, "--format=custom", "--no-owner"],
                    env=environment,
                    stdout=output,
                    stderr=subprocess.PIPE,
                    check=True,
                    timeout=90,
                )
            with archive.open("rb") as input_:
                subprocess.run(
                    [restore, "--no-owner", "--exit-on-error", "--dbname", destination],
                    env={**environment, "PGDATABASE": destination},
                    stdin=input_,
                    capture_output=True,
                    check=True,
                    timeout=90,
                )
        target = create_engine(
            url.set(database=destination), pool_pre_ping=True, connect_args=connect_args
        )
        from alembic.autogenerate import compare_metadata
        from alembic.migration import MigrationContext

        from app.db.base import Base

        with Session(target) as restored:
            if compare_metadata(
                MigrationContext.configure(
                    restored.connection(), opts={"compare_type": True}
                ),
                Base.metadata,
            ):
                raise ValueError("Restored metadata differs")
            if restored.get(Expectation, identity).user_id != owner:
                raise ValueError("Owned fixture missing")
            evaluation = restored.scalar(
                select(Evaluation).where(Evaluation.expectation_id == identity)
            )
            notices = list(
                restored.scalars(
                    select(Notification).where(Notification.expectation_id == identity)
                )
            )
            if (
                evaluation.result.value != "MISMATCH"
                or len(notices) != 1
                or notices[0].evaluation_id != evaluation.id
            ):
                raise ValueError("Restored history differs")
            evidence = restored.scalar(
                select(Evidence).where(Evidence.expectation_id == identity)
            )
            if (
                evidence is None
                or str(evidence.id) != evaluation.observed.get("evidence_id")
                or evidence.value != {"amount": 162}
            ):
                raise ValueError("Restored evidence reference differs")
        print(
            "PASS isolated PostgreSQL archive restore: schema, owned expectation, evidence-backed evaluation and single notification"
        )
        result = 0
    except Exception:  # noqa: BLE001 -- tools/SQL/errors can include credentials or row data
        print(
            "FAIL isolated restore; private details suppressed; check tool versions and local permissions"
        )
    finally:
        if target is not None:
            target.dispose()
        if source is not None:
            try:
                with Session(source) as db:
                    db.execute(delete(Profile).where(Profile.id == owner))
                    db.commit()
                if made:
                    with source.connect().execution_options(
                        isolation_level="AUTOCOMMIT"
                    ) as admin:
                        admin.execute(text(f'DROP DATABASE "{destination}"'))
                print(
                    "PASS restore cleanup: only generated database and tagged fixture removed"
                )
            except Exception:  # noqa: BLE001 -- do not expose DB diagnostics
                print(
                    "FAIL isolated restore cleanup; inspect generated counton_restore_*_test databases privately"
                )
                result = 1
            source.dispose()
    return result


if __name__ == "__main__":
    raise SystemExit(main())
