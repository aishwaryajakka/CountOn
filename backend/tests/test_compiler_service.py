"""Unit tests for AI Compiler & Investigator Integration in CountOn-main backend."""

import pytest
from app.ai.compiler import compile_expectation
from app.ai.investigator import investigate_mismatch
from app.ai.models.expectation import Expectation, EvaluationResult, Evidence


def test_compile_expectation_hero_scenario():
    result = compile_expectation("I've been running the AC less, so my next bill should be lower.", mock_mode=True)
    assert result.kind == "expectation"
    assert result.expectation is not None
    assert result.expectation.type == "numeric_comparison"
    assert result.expectation.metric == "total_cost"
    assert result.expectation.comparison == "less_than"


def test_compile_expectation_clarification_scenario():
    result = compile_expectation("my bill should be lower", mock_mode=True)
    assert result.kind == "clarification"
    assert result.clarification is not None
    assert result.clarification.required is True
    assert "missing_fields" in result.clarification.model_dump()


def test_investigate_mismatch_hero_scenario():
    exp = Expectation(
        claim="I've been running the AC less, so my next bill should be lower.",
        type="numeric_comparison",
        metric="total_cost",
        comparison="less_than",
        status="mismatch",
    )
    eval_res = EvaluationResult(
        result="MISMATCH",
        contradiction=True,
    )
    evidences = [
        Evidence(source="utility_usage", metric="energy_usage", value=-18),
        Evidence(source="tariff", metric="electricity_rate", value=22),
    ]

    res = investigate_mismatch(exp, eval_res, evidences, mock_mode=True)
    assert res.explanation is not None
    assert res.confidence >= 0.9
    assert len(res.key_factors) >= 2
