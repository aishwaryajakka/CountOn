"""
Outlook Intelligence and Context Integration for CountOn.
Extracts testable expectations and normalized evidence from Microsoft Outlook emails and calendar events.
"""

import os
import json
from typing import Optional, List, Literal, Any
from pydantic import BaseModel, Field

from app.ai.models.expectation import Expectation, Evidence
from app.ai.bedrock_client import BedrockClient
from app.ai.prompts import OUTLOOK_INTELLIGENCE_SYSTEM_PROMPT
from app.ai.exceptions import (
    BedrockClientError,
    InvalidModelResponse,
    CountOnAIError,
)


class OutlookEmailContext(BaseModel):
    """Represents an email message retrieved from Microsoft Outlook / Graph API."""
    sender: str = Field(..., description="Email sender address or display name")
    subject: str = Field(..., description="Subject line of the email")
    body: str = Field(..., description="Plaintext or sanitized body of the email")
    received_at: Optional[str] = Field(default=None, description="ISO timestamp when email was received")
    importance: Optional[str] = Field(default="normal", description="Importance level (high, normal, low)")


class OutlookCalendarContext(BaseModel):
    """Represents a calendar event retrieved from Microsoft Outlook Calendar."""
    subject: str = Field(..., description="Title or subject of the calendar event")
    start: str = Field(..., description="Event start ISO datetime or date string")
    end: str = Field(..., description="Event end ISO datetime or date string")
    status: Optional[str] = Field(default="confirmed", description="Status (confirmed, tentative, cancelled)")
    organizer: Optional[str] = Field(default=None, description="Organizer display name or email")
    location: Optional[str] = Field(default=None, description="Event location or online meeting link")


class OutlookContextPayload(BaseModel):
    """Input payload containing Outlook email or calendar data."""
    context_type: Literal["email", "calendar"]
    email: Optional[OutlookEmailContext] = None
    calendar: Optional[OutlookCalendarContext] = None
    user_statement: Optional[str] = Field(default=None, description="Optional accompanying user voice or chat statement")
    mock_mode: Optional[bool] = None


class OutlookExtractionResult(BaseModel):
    """Result of extracting expectations and evidence from Outlook context."""
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


def convert_outlook_to_evidence(
    payload: OutlookContextPayload,
    expectation_id: Optional[str] = None,
) -> List[Evidence]:
    """
    Normalizes raw Outlook calendar or email payload into CountOn Evidence objects.
    """
    evidences: List[Evidence] = []

    if payload.context_type == "calendar" and payload.calendar:
        cal = payload.calendar
        evidences.append(
            Evidence(
                expectation_id=expectation_id,
                source="outlook_calendar",
                metric="appointment_date",
                value={"date": cal.start, "end": cal.end, "status": cal.status},
                description=f"Outlook calendar event '{cal.subject}' scheduled at {cal.start} ({cal.status})",
                confidence=1.0,
            )
        )
        if cal.status:
            evidences.append(
                Evidence(
                    expectation_id=expectation_id,
                    source="outlook_calendar",
                    metric="appointment_status",
                    value=cal.status,
                    description=f"Outlook calendar event status is {cal.status}",
                    confidence=1.0,
                )
            )

    elif payload.context_type == "email" and payload.email:
        em = payload.email
        evidences.append(
            Evidence(
                expectation_id=expectation_id,
                source="outlook_email",
                metric="email_subject",
                value=em.subject,
                description=f"Outlook email from {em.sender}: '{em.subject}'",
                confidence=1.0,
            )
        )
        evidences.append(
            Evidence(
                expectation_id=expectation_id,
                source="outlook_email",
                metric="email_confirmation",
                value={"sender": em.sender, "body_snippet": em.body[:150]},
                description=f"Outlook email confirmation from {em.sender}",
                confidence=0.95,
            )
        )

    return evidences


def _mock_extract_outlook(payload: OutlookContextPayload) -> OutlookExtractionResult:
    """
    Rule-based mock extractor for Outlook context.
    """
    evidences = convert_outlook_to_evidence(payload)

    if payload.context_type == "calendar" and payload.calendar:
        cal = payload.calendar
        claim = payload.user_statement or f"Outlook calendar event '{cal.subject}' should take place as scheduled"
        exp = Expectation(
            claim=claim,
            type="event_occurrence",
            comparison="exists",
            metric="appointment_status",
            deadline=cal.start,
            evidence_sources=["outlook_calendar"],
            status="monitoring",
        )
        return OutlookExtractionResult(
            success=True,
            expectation=exp,
            extracted_evidence=evidences,
            summary=f"Extracted calendar event '{cal.subject}' scheduled for {cal.start} from Outlook Calendar.",
            confidence=0.96,
        )

    elif payload.context_type == "email" and payload.email:
        em = payload.email
        claim = payload.user_statement or f"Commitment from {em.sender}: {em.subject}"
        deadline = "upcoming"
        body_lower = em.body.lower()
        if "tomorrow" in body_lower:
            deadline = "tomorrow"
        elif "friday" in body_lower:
            deadline = "this_week"
        elif "next week" in body_lower:
            deadline = "next_week"

        exp = Expectation(
            claim=claim,
            type="conversation_commitment",
            comparison="exists",
            metric="email_confirmation",
            deadline=deadline,
            evidence_sources=["outlook_email", "outlook_calendar"],
            status="monitoring",
        )
        return OutlookExtractionResult(
            success=True,
            expectation=exp,
            extracted_evidence=evidences,
            summary=f"Extracted conversation commitment from Outlook email '{em.subject}' sent by {em.sender}.",
            confidence=0.94,
        )

    return OutlookExtractionResult(
        success=False,
        summary="No email or calendar data provided in Outlook context payload.",
        confidence=0.0,
    )


def extract_from_outlook_context(
    payload: OutlookContextPayload,
) -> OutlookExtractionResult:
    """
    Main entry point: Analyzes Microsoft Outlook email/calendar context and extracts
    structured expectations and normalized evidence.
    """
    if _should_use_mock(payload.mock_mode):
        return _mock_extract_outlook(payload)

    bedrock = BedrockClient()
    user_message = f"Extract expectation and evidence from this Outlook context:\n\n{payload.model_dump_json(indent=2)}"

    try:
        raw_response = bedrock.invoke(
            system_prompt=OUTLOOK_INTELLIGENCE_SYSTEM_PROMPT,
            user_message=user_message,
            temperature=0.0,
        )
        result = OutlookExtractionResult.model_validate(raw_response)
        # Always attach normalized evidence if model didn't construct it
        if not result.extracted_evidence:
            result.extracted_evidence = convert_outlook_to_evidence(payload)
        return result
    except Exception as e:
        # Fall back gracefully to rule-based parser on Bedrock error
        mock_result = _mock_extract_outlook(payload)
        mock_result.summary += f" (Fallback mode: {str(e)})"
        return mock_result
