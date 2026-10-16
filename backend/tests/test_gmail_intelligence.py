"""
Unit tests for Gmail and Google Calendar Intelligence.
"""

import pytest
from app.ai.gmail_intelligence import (
    GmailEmailContext,
    GoogleCalendarContext,
    GmailContextPayload,
    extract_from_gmail_context,
    convert_gmail_to_evidence,
)
from app.ai.compiler import compile_expectation
from app.ai.investigator import investigate_mismatch
from app.ai.models.expectation import Expectation, EvaluationResult, Evidence


def test_extract_from_google_calendar_context():
    """Verify extracting expectations and evidence from Google Calendar events."""
    cal_event = GoogleCalendarContext(
        summary="Plumber Repair Visit",
        start="2026-10-15T14:00:00Z",
        end="2026-10-15T15:30:00Z",
        status="confirmed",
        location="123 Main Street",
    )
    payload = GmailContextPayload(
        context_type="calendar",
        calendar=cal_event,
        user_statement="Plumber coming on Thursday afternoon",
        mock_mode=True,
    )

    result = extract_from_gmail_context(payload)
    assert result.success is True
    assert result.expectation is not None
    assert result.expectation.type == "event_occurrence"
    assert result.expectation.comparison == "exists"
    assert result.expectation.deadline == "2026-10-15T14:00:00Z"
    assert "google_calendar" in result.expectation.evidence_sources

    # Check extracted normalized evidence
    assert len(result.extracted_evidence) >= 1
    cal_ev = next((e for e in result.extracted_evidence if e.source == "google_calendar"), None)
    assert cal_ev is not None
    assert cal_ev.metric in ("appointment_date", "appointment_status")


def test_extract_from_gmail_email_context():
    """Verify extracting commitments and evidence from Gmail messages."""
    email = GmailEmailContext(
        sender="noreply@utilitycompany.com",
        subject="Your Monthly Electricity Bill is Ready",
        body="Your statement for the billing cycle ending October 2026 is available. Total amount: $128.40.",
        received_at="2026-10-10T08:00:00Z",
        snippet="Total amount: $128.40 due by October 25.",
    )
    payload = GmailContextPayload(
        context_type="email",
        email=email,
        mock_mode=True,
    )

    result = extract_from_gmail_context(payload)
    assert result.success is True
    assert result.expectation is not None
    assert result.expectation.type == "conversation_commitment"
    assert "gmail" in result.expectation.evidence_sources
    assert len(result.extracted_evidence) >= 1


def test_convert_gmail_to_evidence():
    """Verify converting Gmail and Google Calendar payloads to normalized Evidence objects."""
    cal_event = GoogleCalendarContext(
        summary="Doctor Annual Checkup",
        start="2026-10-20T09:00:00Z",
        end="2026-10-20T10:00:00Z",
        status="confirmed",
    )
    payload = GmailContextPayload(
        context_type="calendar",
        calendar=cal_event,
    )
    evidences = convert_gmail_to_evidence(payload, expectation_id="exp_gmail_1")
    assert len(evidences) == 2
    assert all(e.expectation_id == "exp_gmail_1" for e in evidences)
    assert any(e.metric == "appointment_date" for e in evidences)
    assert any(e.metric == "appointment_status" for e in evidences)


def test_compiler_with_gmail_statements():
    """Verify compiler recognizes Gmail and Google Calendar statements."""
    statement = "Check my Google Calendar for the dentist appointment tomorrow"
    res = compile_expectation(statement, mock_mode=True)
    assert res.kind == "expectation"
    assert res.expectation is not None
    assert "google_calendar" in res.expectation.evidence_sources
    assert res.expectation.type == "event_occurrence"


def test_investigator_with_google_calendar_evidence():
    """Verify Investigator explains mismatches using Google Calendar evidence."""
    exp = Expectation(
        claim="Plumber visit scheduled for Thursday",
        type="event_occurrence",
        comparison="exists",
        status="mismatch",
    )
    eval_res = EvaluationResult(
        result="MISMATCH",
        contradiction=True,
    )
    evidences = [
        Evidence(
            source="google_calendar",
            metric="appointment_status",
            value="cancelled",
        )
    ]
    investigation = investigate_mismatch(exp, eval_res, evidences, mock_mode=True)
    assert investigation.explanation is not None
    assert "Google Calendar" in investigation.explanation
    assert investigation.confidence >= 0.9
