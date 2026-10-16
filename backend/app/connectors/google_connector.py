"""
Google Connector: Google Gmail API & Google Calendar API.
Integrates with Google Gmail API (compatible with AWS ingestion services)
and Google Calendar API (compatible with Amazon AppFlow connector).
"""

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from app.ai.gmail_intelligence import (
    GmailEmailContext,
    GoogleCalendarContext,
    GmailContextPayload,
    GmailExtractionResult,
    extract_from_gmail_context,
    convert_gmail_to_evidence,
)


class GmailAPIConnector:
    """
    Connects to and parses messages from the Google Gmail API (users.messages).
    Compatible with AWS ingestion patterns (e.g. Amazon Quick / EventBridge / Webhooks).
    """

    @staticmethod
    def parse_gmail_api_message(raw_message: Dict[str, Any]) -> GmailEmailContext:
        """
        Transforms a standard Google Gmail API message JSON object (from users.messages.get)
        into a normalized GmailEmailContext.
        """
        msg_id = raw_message.get("id", "unknown")
        snippet = raw_message.get("snippet", "")
        payload = raw_message.get("payload", {})
        headers_list = payload.get("headers", [])

        # Extract standard email headers
        headers: Dict[str, str] = {}
        for h in headers_list:
            name = h.get("name", "").lower()
            headers[name] = h.get("value", "")

        sender = headers.get("from", "unknown@gmail.com")
        subject = headers.get("subject", "No Subject")
        date_str = headers.get("date", datetime.now(timezone.utc).isoformat())

        # Extract body text from parts or body
        body = snippet
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("mimeType") == "text/plain" and "data" in part.get("body", {}):
                    # Data could be base64url or plain string in test mocks
                    body = part["body"].get("data", snippet)
                    break
        elif "body" in payload and "data" in payload["body"]:
            body = payload["body"].get("data", snippet)

        return GmailEmailContext(
            sender=sender,
            subject=subject,
            body=body or snippet or f"Email from {sender}: {subject}",
            received_at=date_str,
            snippet=snippet,
        )

    @classmethod
    def ingest_gmail_message(
        cls,
        raw_message: Dict[str, Any],
        user_statement: Optional[str] = None,
        mock_mode: Optional[bool] = None,
    ) -> GmailExtractionResult:
        """
        Parses a Google Gmail API message and returns an extracted expectation & evidence.
        """
        context = cls.parse_gmail_api_message(raw_message)
        payload = GmailContextPayload(
            context_type="email",
            email=context,
            user_statement=user_statement,
            mock_mode=mock_mode,
        )
        return extract_from_gmail_context(payload)


class GoogleCalendarAppFlowConnector:
    """
    Connects to and parses Google Calendar API events.
    Supports standard Google Calendar API (/calendars/primary/events)
    and Amazon AppFlow Google Calendar connector records.
    """

    @staticmethod
    def parse_google_calendar_event(raw_event: Dict[str, Any]) -> GoogleCalendarContext:
        """
        Transforms a standard Google Calendar API event or Amazon AppFlow record
        into a normalized GoogleCalendarContext.
        """
        summary = raw_event.get("summary") or raw_event.get("title") or "Scheduled Calendar Event"
        start_obj = raw_event.get("start", {})
        end_obj = raw_event.get("end", {})

        start_time = (
            start_obj.get("dateTime")
            or start_obj.get("date")
            or raw_event.get("start_time")
            or datetime.now(timezone.utc).isoformat()
        )
        end_time = (
            end_obj.get("dateTime")
            or end_obj.get("date")
            or raw_event.get("end_time")
            or datetime.now(timezone.utc).isoformat()
        )

        status = raw_event.get("status", "confirmed").lower()
        location = raw_event.get("location")
        organizer = raw_event.get("organizer", {}).get("email") if isinstance(raw_event.get("organizer"), dict) else str(raw_event.get("organizer", ""))

        return GoogleCalendarContext(
            summary=summary,
            start=str(start_time),
            end=str(end_time),
            status=status,
            organizer=organizer or None,
            location=location or None,
        )

    @classmethod
    def ingest_calendar_event(
        cls,
        raw_event: Dict[str, Any],
        user_statement: Optional[str] = None,
        mock_mode: Optional[bool] = None,
    ) -> GmailExtractionResult:
        """
        Parses a Google Calendar event / AppFlow record and returns an extracted expectation & evidence.
        """
        context = cls.parse_google_calendar_event(raw_event)
        payload = GmailContextPayload(
            context_type="calendar",
            calendar=context,
            user_statement=user_statement,
            mock_mode=mock_mode,
        )
        return extract_from_gmail_context(payload)
