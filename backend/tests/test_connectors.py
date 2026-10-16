"""
Unit tests for external service connectors:
- Gmail: Google Gmail API
- Google Calendar: Google Calendar API via Amazon AppFlow connector
- Outlook Mail: Microsoft Graph API (/v1.0/me/messages)
- Outlook Calendar: Microsoft Graph API (/v1.0/me/events)
- Amazon Orders: Inferred via email receipts & carrier tracking (no direct shopping API assumed)
"""

import pytest
from app.connectors.google_connector import (
    GmailAPIConnector,
    GoogleCalendarAppFlowConnector,
)
from app.connectors.microsoft_connector import (
    MicrosoftGraphMailConnector,
    MicrosoftGraphCalendarConnector,
)
from app.connectors.amazon_connector import (
    AmazonOrderInferredConnector,
)


def test_gmail_api_connector():
    """Verify Google Gmail API connector parsing users.messages payload."""
    raw_gmail_msg = {
        "id": "18f123abc456",
        "snippet": "Your electricity bill for October is ready. Total due: $115.00",
        "payload": {
            "headers": [
                {"name": "From", "value": "billing@utilitypower.com"},
                {"name": "Subject", "value": "Monthly Electricity Bill Ready"},
                {"name": "Date", "value": "2026-10-10T12:00:00Z"},
            ],
            "body": {
                "data": "Your electricity bill for October is ready. Total due: $115.00 by Nov 1."
            },
        },
    }

    result = GmailAPIConnector.ingest_gmail_message(raw_gmail_msg, mock_mode=True)
    assert result.success is True
    assert result.expectation is not None
    assert "gmail" in result.expectation.evidence_sources
    assert len(result.extracted_evidence) >= 1
    assert any(e.source == "gmail" for e in result.extracted_evidence)


def test_google_calendar_appflow_connector():
    """Verify Google Calendar API connector with Amazon AppFlow connector format."""
    raw_appflow_event = {
        "summary": "Dentist Teeth Cleaning",
        "start": {"dateTime": "2026-10-18T10:00:00Z"},
        "end": {"dateTime": "2026-10-18T11:00:00Z"},
        "status": "confirmed",
        "location": "Smile Dental Suite 400",
        "organizer": {"email": "clinic@smiledental.com"},
    }

    result = GoogleCalendarAppFlowConnector.ingest_calendar_event(raw_appflow_event, mock_mode=True)
    assert result.success is True
    assert result.expectation is not None
    assert result.expectation.type == "event_occurrence"
    assert result.expectation.deadline == "2026-10-18T10:00:00Z"
    assert "google_calendar" in result.expectation.evidence_sources
    assert any(e.source == "google_calendar" for e in result.extracted_evidence)


def test_microsoft_graph_mail_connector():
    """Verify Microsoft Graph API connector parsing Outlook Mail /v1.0/me/messages."""
    graph_message = {
        "id": "AAMkAGI2AA...",
        "subject": "Doctor Appointment Confirmation",
        "bodyPreview": "Your appointment is confirmed for tomorrow at 3 PM with Dr. Reynolds.",
        "from": {
            "emailAddress": {
                "name": "Health Center",
                "address": "appointments@healthcenter.org",
            }
        },
        "receivedDateTime": "2026-10-11T14:30:00Z",
        "importance": "high",
    }

    result = MicrosoftGraphMailConnector.ingest_graph_message(graph_message, mock_mode=True)
    assert result.success is True
    assert result.expectation is not None
    assert result.expectation.type == "conversation_commitment"
    assert "outlook_email" in result.expectation.evidence_sources
    assert len(result.extracted_evidence) >= 1


def test_microsoft_graph_calendar_connector():
    """Verify Microsoft Graph API connector parsing Outlook Calendar /v1.0/me/events."""
    graph_event = {
        "id": "AAMkAGI2BB...",
        "subject": "Home HVAC Maintenance Inspection",
        "start": {"dateTime": "2026-10-19T09:00:00Z"},
        "end": {"dateTime": "2026-10-19T11:00:00Z"},
        "isCancelled": False,
        "location": {"displayName": "123 Elm Street"},
    }

    result = MicrosoftGraphCalendarConnector.ingest_graph_event(graph_event, mock_mode=True)
    assert result.success is True
    assert result.expectation is not None
    assert result.expectation.type == "event_occurrence"
    assert result.expectation.deadline == "2026-10-19T09:00:00Z"
    assert "outlook_calendar" in result.expectation.evidence_sources


def test_amazon_order_inferred_from_email_receipt():
    """Verify Amazon order inferred via email receipt (without assuming direct shopping API)."""
    sender = "auto-confirm@amazon.com"
    subject = "Shipped: Echo Dot Smart Speaker (5th Gen)"
    body = (
        "Order #114-7654321-1234567 has shipped via Amazon Logistics TBA9876543210. "
        "Estimated arrival: tomorrow by 8 PM."
    )

    result = AmazonOrderInferredConnector.parse_from_email_receipt(
        sender=sender,
        subject=subject,
        body=body,
        mock_mode=True,
    )
    assert result.success is True
    assert result.expectation is not None
    assert result.expectation.type == "delivery"
    assert result.expectation.deadline == "tomorrow"
    assert "delivery" in result.expectation.evidence_sources
    assert len(result.extracted_evidence) >= 2


def test_amazon_order_inferred_with_carrier_delay():
    """Verify Amazon order inferred from carrier tracking delay update."""
    tracking_update = {
        "order_id": "114-8888777-6666555",
        "item_title": "Ergonomic Office Chair",
        "status": "delayed",
        "expected_delivery_date": "2026-10-11",
        "actual_delivery_date": "2026-10-15",
        "carrier": "UPS",
        "delay_reason": "Severe winter weather caused road closure",
    }

    result = AmazonOrderInferredConnector.parse_from_carrier_update(tracking_update, mock_mode=True)
    assert result.success is True
    assert result.is_delayed is True
    assert result.expectation.status == "mismatch"
    assert "delayed" in result.summary.lower()
