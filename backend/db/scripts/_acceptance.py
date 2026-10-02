"""One acceptance flow shared by local and Supabase entry points."""

from datetime import datetime, timezone
from uuid import uuid4


def run_acceptance(target: str) -> int:
    from sqlalchemy import select
    from app.db.models import Expectation
    from app.db.session import SessionLocal, engine
    from app.schemas.expectation import ExpectationCreate
    from app.schemas.evidence import EvidenceCreate
    from app.services import evidence_service, evaluation_service, expectation_service

    # This unique marker also identifies a committed row if a refresh fails
    # before create_expectation can return its ID. It is never used elsewhere.
    run_id = uuid4()
    claim = f"My next electricity bill will be lower [acceptance:{run_id}]"
    if target.upper() == "SUPABASE":
        from db.scripts._token import access_token
        from app.core.auth import get_token_verifier
        owner = get_token_verifier().verify(access_token()).id
    else:
        owner = run_id
    scenarios = (("MISMATCH", 162, "contradicted"), ("MATCH", 130, "fulfilled"), ("UNKNOWN", None, "monitoring"))
    passed = []
    try:
        try:
            for result, amount, status in scenarios:
                with SessionLocal() as db:
                    expectation = expectation_service.create_expectation(db, ExpectationCreate(
                        claim=claim,
                        type="numeric_comparison", metric="total_cost", comparison="less_than",
                        baseline=142.10, evidence_sources=["utility_bill", "utility_usage"],
                        materiality_threshold=0.05,
                    ), user_id=owner)
                    expectation_id = expectation.id
                    evidence_service.add_evidence(db, expectation_id, EvidenceCreate(
                        source="utility_bill" if amount is not None else "utility_usage",
                        metric="total_cost" if amount is not None else "energy_usage_change",
                        value={"amount": amount} if amount is not None else {"percentage": -18},
                        unit="USD" if amount is not None else "percent",
                        observed_at=datetime(2026, 10, 1, 20, tzinfo=timezone.utc),
                        confidence=1.0, raw_data={},
                    ), owner)
                    evaluation_id = evaluation_service.evaluate_expectation(db, expectation_id, owner).id
                # A fresh session verifies that both writes actually persisted.
                with SessionLocal() as db:
                    persisted = evaluation_service.get_latest_evaluation(db, expectation_id, owner)
                    expectation = expectation_service.get_expectation(db, expectation_id, owner)
                    correct = (
                        persisted.id == evaluation_id and persisted.result.value == result
                        and expectation.status.value == status
                        and persisted.expected["metric"] == "total_cost"
                        and persisted.expected["comparison"] == "less_than"
                        and persisted.expected["target"] == 142.10
                    )
                    if amount is None:
                        correct = correct and persisted.reasoning.get("reason") == "no_relevant_evidence"
                    else:
                        correct = correct and persisted.observed.get("value") == amount
                    if not correct:
                        print(f"FAIL {result}")
                        raise RuntimeError("Acceptance scenario did not match its contract")
                passed.append(result)
        finally:
            # Delete only expectations tagged by this invocation. The database
            # cascades their evidence/evaluations. No truncate or broad delete.
            with SessionLocal() as db:
                ids = list(db.scalars(select(Expectation.id).where(Expectation.user_id == owner, Expectation.claim == claim)))
                from db.scripts._cleanup import cleanup_expectations
                cleanup_expectations(db, owner, ids)
                if target.upper() == "LOCAL":
                    from app.repositories.profile import delete_profile
                    delete_profile(db, owner)
                    db.commit()
        for result in passed:
            print(f"PASS {result}")
        print(f"{target} ACCEPTANCE PASSED")
        return 0
    finally:
        engine.dispose()
