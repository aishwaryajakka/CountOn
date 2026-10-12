"""
Unit tests for Outlook Intelligence and Context Integration.
"""

import pytest
from app.ai.outlook_intelligence import (
    OutlookEmailContext,
    OutlookCalendarContext,
    OutlookContextPayload,
    extract_from_outlook_context,
    convert_outlook_to_evidence,
)
from app.ai.compiler import compile_expectation
from app.ai.investigator import investigate_mismatch
from app.ai.models.expectation import Expectation, EvaluationResult, Evidence


def test_extract_from_outlook_calendar_context():
    """Verify extracting expectations and normalized evidence from Outlook calendar events."""
    cal_event = OutlookCalendarContext(
        subject="Dentist Appointment",
        start="2026-10-12T10:00:00Z",
        end="2026-10-12T11:00:00Z",
        status="confirmed",
        location="Dental Clinic Room 3",
    )
    payload = OutlookContextPayload(
        context_type="calendar",
        calendar=cal_event,
        user_statement="Dentist appointment on Monday",
        mock_mode=True,
    )

    result = extract_from_outlook_context(payload)
    assert result.success is True
    assert result.expectation is not None
    assert result.expectation.type == "event_occurrence"
    assert result.expectation.comparison == "exists"
    assert result.expectation.deadline == "2026-10-12T10:00:00Z"
    assert "outlook_calendar" in result.expectation.evidence_sources

    # Check extracted normalized evidence
    assert len(result.extracted_evidence) >= 1
    cal_evidence = next((e for e in result.extracted_evidence if e.source == "outlook_calendar"), None)
    assert cal_evidence is not None
    assert cal_evidence.metric in ("appointment_date", "appointment_status")


def test_extract_from_outlook_email_context():
    """Verify extracting commitments and evidence from Outlook emails."""
    email = OutlookEmailContext(
        sender="dr_smith@dentalclinic.com",
        subject="Appointment Confirmation",
        body="Your dental cleaning is scheduled for tomorrow at 2 PM. Please arrive 10 minutes early.",
        received_at="2026-10-09T09:00:00Z",
    )
    payload = OutlookContextPayload(
        context_type="email",
        email=email,
        mock_mode=True,
    )

    result = extract_from_outlook_context(payload)
    assert result.success is True
    assert result.expectation is not None
    assert result.expectation.type == "conversation_commitment"
    assert result.expectation.deadline == "tomorrow"
    assert "outlook_email" in result.expectation.evidence_sources
    assert len(result.extracted_evidence) >= 1


def test_convert_outlook_to_evidence():
    """Verify normalizing raw Outlook events into CountOn Evidence model."""
    cal_event = OutlookCalendarContext(
        subject="Team Sprint Planning",
        start="2026-10-14T09:00:00Z",
        end="2026-10-14T10:00:00Z",
        status="confirmed",
    )
    payload = OutlookContextPayload(
        context_type="calendar",
        calendar=cal_event,
    )
    evidences = convert_outlook_to_evidence(payload, expectation_id="exp_123")
    assert len(evidences) == 2
    assert all(e.expectation_id == "exp_123" for e in evidences)
    assert any(e.metric == "appointment_date" for e in evidences)
    assert any(e.metric == "appointment_status" for e in evidences)


def test_compiler_with_outlook_statements():
    """Verify compiler recognizes Outlook statements from casual user queries."""
    statement = "My dentist appointment is on my Outlook calendar for Monday."
    res = compile_expectation(statement, mock_mode=True)
    assert res.kind == "expectation"
    assert res.expectation is not None
    assert "outlook_calendar" in res.expectation.evidence_sources
    assert res.expectation.type == "event_occurrence"


def test_investigator_with_outlook_calendar_evidence():
    """Verify Investigator explains mismatches using Outlook calendar evidence."""
    exp = Expectation(
        claim="Dentist appointment on Monday",
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
            source="outlook_calendar",
            metric="appointment_status",
            value="cancelled",
        )
    ]
    investigation = investigate_mismatch(exp, eval_res, evidences, mock_mode=True)
    assert investigation.explanation is not None
    assert "Outlook Calendar" in investigation.explanation
    assert investigation.confidence >= 0.9
