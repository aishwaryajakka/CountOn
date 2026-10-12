"""Unit tests for AI Compiler & Investigator Integration in CountOn-main backend."""

from datetime import datetime, timezone
import pytest
from app.ai.compiler import compile_expectation
from app.ai.investigator import investigate_mismatch
from app.ai.models.expectation import Expectation, EvaluationResult, Evidence
from app.ai.time_parser import parse_relative_deadline


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


def test_compile_expectation_multiturn_memory():
    """Verify that compiler remembers prior clarification context across turns."""
    # Turn 1: User gives vague statement
    turn_1 = compile_expectation("My bill should be lower.", mock_mode=True)
    assert turn_1.kind == "clarification"

    # Turn 2: User answers follow-up with history
    history = [
        {"role": "user", "content": "My bill should be lower."},
        {"role": "assistant", "content": turn_1.clarification.question},
    ]
    turn_2 = compile_expectation(
        "electricity bill next month",
        mock_mode=True,
        conversation_history=history,
        draft_expectation=turn_1.clarification.draft_expectation,
    )
    assert turn_2.kind == "expectation"
    assert turn_2.expectation is not None
    assert turn_2.expectation.type == "numeric_comparison"
    assert turn_2.expectation.deadline == "next_month"
    assert "utility_bill" in turn_2.expectation.evidence_sources


def test_compile_expectation_correction_intent():
    """Verify that compiler recognizes when a user corrects an expectation or changes their mind."""
    draft = {
        "claim": "My electricity bill will be lower",
        "type": "numeric_comparison",
        "metric": "total_cost",
        "baseline": 150.0,
        "deadline": "next_month",
    }
    result = compile_expectation(
        "Actually, change the deadline to tomorrow and baseline to $100",
        mock_mode=True,
        draft_expectation=draft,
    )
    assert result.kind == "expectation"
    assert result.is_correction is True
    assert result.expectation.deadline == "tomorrow"
    assert result.expectation.baseline == 100.0


def test_compile_expectation_cancellation_intent():
    """Verify that compiler extracts natural language cancellation requests."""
    result = compile_expectation("Cancel my expectation about the electric bill", mock_mode=True)
    assert result.kind == "cancellation"
    assert result.cancellation is not None
    assert "electric bill" in result.cancellation.target_claim.lower()
    assert result.cancellation.reason is not None


def test_time_parser_relative_deadlines():
    """Verify that relative time expressions parse into timezone-aware UTC datetimes."""
    ref_time = datetime(2026, 10, 9, 12, 0, 0, tzinfo=timezone.utc)

    # Tomorrow
    tomorrow = parse_relative_deadline("tomorrow", reference_time=ref_time)
    assert tomorrow is not None
    assert tomorrow.tzinfo is not None
    assert tomorrow.day == 10
    assert tomorrow.hour == 23

    # Today
    today = parse_relative_deadline("today", reference_time=ref_time)
    assert today is not None
    assert today.day == 9
    assert today.hour == 23

    # This week
    this_week = parse_relative_deadline("this_week", reference_time=ref_time)
    assert this_week is not None
    assert this_week.tzinfo is not None

    # Next month
    next_month = parse_relative_deadline("next_month", reference_time=ref_time)
    assert next_month is not None
    assert next_month.month == 11

    # Standard ISO string
    iso_dt = parse_relative_deadline("2026-11-15T10:00:00Z")
    assert iso_dt is not None
    assert iso_dt.year == 2026
    assert iso_dt.month == 11
    assert iso_dt.day == 15


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
