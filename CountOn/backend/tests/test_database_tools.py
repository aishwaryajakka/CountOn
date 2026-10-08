"""Verification tools must preserve unrelated rows and sanitize failures."""

from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db import session as application_database
from app.db.models import Evidence, Evaluation, Expectation
from app.schemas.expectation import ExpectationCreate
from app.schemas.evidence import EvidenceCreate
from app.services import evidence_service, evaluation_service, expectation_service
from db.scripts._acceptance import run_acceptance
from db.scripts._common import run_cli


def test_cli_does_not_print_secret_bearing_exception(capsys):
    def fail():
        raise RuntimeError("postgresql+psycopg://user:private_password@host/database")
    assert run_cli(fail) == 1
    output = capsys.readouterr().out
    assert "FAIL" in output
    assert "private_password" not in output
    assert "postgresql" not in output
    assert "Traceback" not in output


@pytest.mark.integration
@pytest.mark.parametrize("inject_failure", [False, True])
def test_acceptance_cleans_only_its_own_rows(postgres_engine, monkeypatch, capsys, inject_failure):
    factory = sessionmaker(bind=postgres_engine, autoflush=False, expire_on_commit=False)
    monkeypatch.setattr(application_database, "engine", postgres_engine)
    monkeypatch.setattr(application_database, "SessionLocal", factory)
    owner = uuid4()
    with factory() as db:
        unrelated = expectation_service.create_expectation(db, ExpectationCreate(
            claim="Unrelated test data must survive acceptance cleanup",
            type="numeric_comparison", metric="total_cost", comparison="less_than", baseline=142.10,
        ), user_id=owner)
        unrelated_id = unrelated.id
        evidence_service.add_evidence(db, unrelated_id, EvidenceCreate(
            source="utility_bill", metric="total_cost", value={"amount": 130},
            observed_at="2026-10-01T20:00:00Z",
        ), owner)
        evaluation_service.evaluate_expectation(db, unrelated_id, owner)
    try:
        with factory() as db:
            before = [db.scalar(select(func.count()).select_from(model)) for model in (Expectation, Evidence, Evaluation)]
        if inject_failure:
            def fail_evaluation(*args, **kwargs):
                raise RuntimeError("Injected failure after expectation and evidence commit")
            monkeypatch.setattr(evaluation_service, "evaluate_expectation", fail_evaluation)
            with pytest.raises(RuntimeError, match="Injected failure"):
                run_acceptance("LOCAL")
        else:
            assert run_acceptance("LOCAL") == 0
            assert capsys.readouterr().out.splitlines() == [
                "PASS MISMATCH", "PASS MATCH", "PASS UNKNOWN", "LOCAL ACCEPTANCE PASSED",
            ]
        with factory() as db:
            after = [db.scalar(select(func.count()).select_from(model)) for model in (Expectation, Evidence, Evaluation)]
            assert after == before
            assert expectation_service.get_expectation(db, unrelated_id, owner).claim.startswith("Unrelated")
    finally:
        with factory() as db:
            expectation_service.delete_expectation(db, unrelated_id, owner)
            from app.repositories.profile import delete_profile
            delete_profile(db, owner)
            db.commit()
