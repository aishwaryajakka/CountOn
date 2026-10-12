"""Golden contract and human-review gates; never label automated fixtures reviewed."""

import json

from db.scripts.orchestration_eval import DATASET, benchmark, evaluate


def test_synthetic_goldens_match_without_cloud_calls():
    result = evaluate(json.loads(DATASET.read_text()))
    assert result["passed"] == result["cases"] == 26
    assert result["matching_false_positive"] == result["matching_false_negative"] == 0
    assert result["bedrock_calls"] == 0 and result["pending_human_review"] == 26


def test_critical_goldens_require_human_review_before_acceptance():
    assert evaluate(json.loads(DATASET.read_text()), require_review=True) == {
        "blocked": True,
        "pending_human_review": 26,
    }


def test_unchanged_batch_cost_is_zero_model_calls():
    result = benchmark(200)
    assert (
        result["records"] == 200
        and result["normalizations"] == 1
        and result["hits"] == 199
    )
    assert result["bedrock_calls"] == 0


def test_verification_categories_do_not_invent_external_acceptance():
    from db.scripts.orchestration_eval import categories

    dataset = json.loads(DATASET.read_text())
    report = categories(dataset, evaluate(dataset))
    assert report["synthetic_agreement"]["status"] == "PASS"
    for category in (
        "human_reviewed",
        "mocked_provider_regressions",
        "live_provider_verification",
        "real_bedrock_verification",
    ):
        assert report[category]["status"] == "BLOCKED"


def test_unknown_operation_is_rejected():
    import pytest

    from db.scripts.orchestration_eval import run_case

    with pytest.raises(ValueError, match="Unknown golden operation"):
        run_case({"operation": "typo"})


def test_mocked_runner_requires_explicit_isolated_database(monkeypatch):
    from db.scripts.orchestration_eval import mocked_regressions

    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql://localhost/counton")
    assert mocked_regressions()["status"] == "BLOCKED"
