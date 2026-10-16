"""
Microsoft Connector: Microsoft Graph API for Outlook Mail & Outlook Calendar.
Connects an AWS backend to Microsoft Graph API endpoints:
- Outlook Mail: https://graph.microsoft.com/v1.0/me/messages
- Outlook Calendar: https://graph.microsoft.com/v1.0/me/events
"""

from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from app.ai.outlook_intelligence import (
    OutlookEmailContext,
    OutlookCalendarContext,
    OutlookContextPayload,
    OutlookExtractionResult,
    extract_from_outlook_context,
    convert_outlook_to_evidence,
)


class MicrosoftGraphMailConnector:
    """
    Connects to and parses messages from the Microsoft Graph API (/v1.0/me/messages).
    Enables AWS backend services to process Outlook mail.
    """

    @staticmethod
    def parse_graph_message(graph_msg: Dict[str, Any]) -> OutlookEmailContext:
        """
        Transforms a standard Microsoft Graph API Message resource into an OutlookEmailContext.
        """
        subject = graph_msg.get("subject", "No Subject")
        body_preview = graph_msg.get("bodyPreview", "")
        body_content = graph_msg.get("body", {}).get("content", body_preview)

        # Parse sender
        sender_email = "unknown@outlook.com"
        sender_info = graph_msg.get("from") or graph_msg.get("sender")
        if isinstance(sender_info, dict) and "emailAddress" in sender_info:
            sender_email = sender_info["emailAddress"].get("address", sender_email)

        received_at = graph_msg.get("receivedDateTime") or datetime.now(timezone.utc).isoformat()
        importance = graph_msg.get("importance", "normal").lower()

        return OutlookEmailContext(
            sender=sender_email,
            subject=subject,
            body=body_content or body_preview or f"Outlook mail from {sender_email}: {subject}",
            received_at=received_at,
            importance=importance,
        )

    @classmethod
    def ingest_graph_message(
        cls,
        graph_msg: Dict[str, Any],
        user_statement: Optional[str] = None,
        mock_mode: Optional[bool] = None,
    ) -> OutlookExtractionResult:
        """
        Parses a Microsoft Graph Outlook mail message and extracts expectations & evidence.
        """
        context = cls.parse_graph_message(graph_msg)
        payload = OutlookContextPayload(
            context_type="email",
            email=context,
            user_statement=user_statement,
            mock_mode=mock_mode,
        )
        return extract_from_outlook_context(payload)


class MicrosoftGraphCalendarConnector:
    """
    Connects to and parses calendar events from the Microsoft Graph API (/v1.0/me/events).
    Enables AWS backend services to process Outlook calendar items.
    """

    @staticmethod
    def parse_graph_event(graph_event: Dict[str, Any]) -> OutlookCalendarContext:
        """
        Transforms a standard Microsoft Graph Event resource into an OutlookCalendarContext.
        """
        subject = graph_event.get("subject", "Scheduled Calendar Event")
        start_dt = graph_event.get("start", {}).get("dateTime") or graph_event.get("start_time") or datetime.now(timezone.utc).isoformat()
        end_dt = graph_event.get("end", {}).get("dateTime") or graph_event.get("end_time") or datetime.now(timezone.utc).isoformat()

        # In Graph API: isCancelled boolean or showAs status
        is_cancelled = graph_event.get("isCancelled", False)
        status = "cancelled" if is_cancelled else "confirmed"

        location_name = graph_event.get("location", {}).get("displayName") if isinstance(graph_event.get("location"), dict) else None
        organizer_name = graph_event.get("organizer", {}).get("emailAddress", {}).get("name") if isinstance(graph_event.get("organizer"), dict) else None

        return OutlookCalendarContext(
            subject=subject,
            start=str(start_dt),
            end=str(end_dt),
            status=status,
            organizer=organizer_name,
            location=location_name,
        )

    @classmethod
    def ingest_graph_event(
        cls,
        graph_event: Dict[str, Any],
        user_statement: Optional[str] = None,
        mock_mode: Optional[bool] = None,
    ) -> OutlookExtractionResult:
        """
        Parses a Microsoft Graph Outlook calendar event and extracts expectations & evidence.
        """
        context = cls.parse_graph_event(graph_event)
        payload = OutlookContextPayload(
            context_type="calendar",
            calendar=context,
            user_statement=user_statement,
            mock_mode=mock_mode,
        )
        return extract_from_outlook_context(payload)
