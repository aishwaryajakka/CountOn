"""
Gmail & Google Calendar Intelligence & Context Integration for CountOn.
Extracts testable expectations and normalized evidence from Google emails and calendar events.
"""

import os
import json
from typing import Optional, List, Literal, Any
from pydantic import BaseModel, Field

from app.ai.models.expectation import Expectation, Evidence
from app.ai.bedrock_client import BedrockClient
from app.ai.prompts import GMAIL_INTELLIGENCE_SYSTEM_PROMPT


class GmailEmailContext(BaseModel):
    """Represents an email message retrieved from Google Gmail API."""
    sender: str = Field(..., description="Email sender address or display name")
    subject: str = Field(..., description="Subject line of the email")
    body: str = Field(..., description="Plaintext or sanitized body of the email")
    received_at: Optional[str] = Field(default=None, description="ISO timestamp when email was received")
    snippet: Optional[str] = Field(default=None, description="Brief snippet or preview of the message")


class GoogleCalendarContext(BaseModel):
    """Represents a calendar event retrieved from Google Calendar API."""
    summary: str = Field(..., description="Title or summary of the event")
    start: str = Field(..., description="Event start ISO datetime or date string")
    end: str = Field(..., description="Event end ISO datetime or date string")
    status: Optional[str] = Field(default="confirmed", description="Status (confirmed, tentative, cancelled)")
    organizer: Optional[str] = Field(default=None, description="Organizer display name or email")
    location: Optional[str] = Field(default=None, description="Location of event or meeting URL")


class GmailContextPayload(BaseModel):
    """Input payload containing Gmail email or Google Calendar data."""
    context_type: Literal["email", "calendar"]
    email: Optional[GmailEmailContext] = None
    calendar: Optional[GoogleCalendarContext] = None
    user_statement: Optional[str] = Field(default=None, description="Optional accompanying user voice or text statement")
    mock_mode: Optional[bool] = None


class GmailExtractionResult(BaseModel):
    """Result of extracting expectations and evidence from Gmail/Google context."""
    success: bool = True
    expectation: Optional[Expectation] = None
    extracted_evidence: List[Evidence] = Field(default_factory=list)
    summary: str = Field(..., description="Concise explanation of extracted commitments or events")
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)


def _should_use_mock(explicit_mock: Optional[bool] = None) -> bool:
    """Determine whether to use offline mock mode."""
    if explicit_mock is not None:
        return explicit_mock

    env_mock = os.environ.get("COUNTON_MOCK_AI", "").strip().lower()
    if env_mock in ("1", "true", "yes", "on"):
        return True

    if not os.environ.get("AWS_ACCESS_KEY_ID") and not os.environ.get("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"):
        return True

    return False


def convert_gmail_to_evidence(
    payload: GmailContextPayload,
    expectation_id: Optional[str] = None,
) -> List[Evidence]:
    """
    Normalizes raw Gmail email or Google Calendar payload into CountOn Evidence objects.
    """
    evidences: List[Evidence] = []

    if payload.context_type == "calendar" and payload.calendar:
        cal = payload.calendar
        evidences.append(
            Evidence(
                expectation_id=expectation_id,
                source="google_calendar",
                metric="appointment_date",
                value={"date": cal.start, "end": cal.end, "status": cal.status},
                description=f"Google Calendar event '{cal.summary}' scheduled at {cal.start} ({cal.status})",
                confidence=1.0,
            )
        )
        if cal.status:
            evidences.append(
                Evidence(
                    expectation_id=expectation_id,
                    source="google_calendar",
                    metric="appointment_status",
                    value=cal.status,
                    description=f"Google Calendar event status: {cal.status}",
                    confidence=1.0,
                )
            )

    elif payload.context_type == "email" and payload.email:
        em = payload.email
        evidences.append(
            Evidence(
                expectation_id=expectation_id,
                source="gmail",
                metric="email_subject",
                value=em.subject,
                description=f"Gmail message from {em.sender}: '{em.subject}'",
                confidence=1.0,
            )
        )
        evidences.append(
            Evidence(
                expectation_id=expectation_id,
                source="gmail",
                metric="email_confirmation",
                value={"sender": em.sender, "snippet": em.snippet or em.body[:150]},
                description=f"Gmail confirmation from {em.sender}",
                confidence=0.95,
            )
        )

    return evidences


def _mock_extract_gmail(payload: GmailContextPayload) -> GmailExtractionResult:
    """
    Rule-based mock extractor for Gmail and Google Calendar context.
    """
    evidences = convert_gmail_to_evidence(payload)

    if payload.context_type == "calendar" and payload.calendar:
        cal = payload.calendar
        claim = payload.user_statement or f"Google Calendar event '{cal.summary}' should take place as scheduled"
        exp = Expectation(
            claim=claim,
            type="event_occurrence",
            comparison="exists",
            metric="appointment_status",
            deadline=cal.start,
            evidence_sources=["google_calendar"],
            status="monitoring",
        )
        return GmailExtractionResult(
            success=True,
            expectation=exp,
            extracted_evidence=evidences,
            summary=f"Extracted calendar event '{cal.summary}' scheduled for {cal.start} from Google Calendar.",
            confidence=0.96,
        )

    elif payload.context_type == "email" and payload.email:
        em = payload.email
        claim = payload.user_statement or f"Commitment from {em.sender}: {em.subject}"
        deadline = "upcoming"
        body_lower = em.body.lower()
        if "tomorrow" in body_lower:
            deadline = "tomorrow"
        elif "today" in body_lower:
            deadline = "today"
        elif "this week" in body_lower:
            deadline = "this_week"

        exp = Expectation(
            claim=claim,
            type="conversation_commitment",
            comparison="exists",
            metric="email_confirmation",
            deadline=deadline,
            evidence_sources=["gmail", "google_calendar"],
            status="monitoring",
        )
        return GmailExtractionResult(
            success=True,
            expectation=exp,
            extracted_evidence=evidences,
            summary=f"Extracted conversation commitment from Gmail message '{em.subject}' sent by {em.sender}.",
            confidence=0.95,
        )

    return GmailExtractionResult(
        success=False,
        summary="No email or calendar data provided in Gmail context payload.",
        confidence=0.0,
    )


def extract_from_gmail_context(
    payload: GmailContextPayload,
) -> GmailExtractionResult:
    """
    Main entry point: Analyzes Gmail email or Google Calendar context and extracts
    structured expectations and normalized evidence.
    """
    if _should_use_mock(payload.mock_mode):
        return _mock_extract_gmail(payload)

    bedrock = BedrockClient()
    user_message = f"Extract expectation and evidence from this Google context:\n\n{payload.model_dump_json(indent=2)}"

    try:
        raw_response = bedrock.invoke(
            system_prompt=GMAIL_INTELLIGENCE_SYSTEM_PROMPT,
            user_message=user_message,
            temperature=0.0,
        )
        result = GmailExtractionResult.model_validate(raw_response)
        if not result.extracted_evidence:
            result.extracted_evidence = convert_gmail_to_evidence(payload)
        return result
    except Exception as e:
        mock_result = _mock_extract_gmail(payload)
        mock_result.summary += f" (Fallback mode: {str(e)})"
        return mock_result
