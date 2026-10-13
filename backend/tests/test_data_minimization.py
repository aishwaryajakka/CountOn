"""Provider normalization and provenance must not become a raw-data archive."""

import base64
from types import SimpleNamespace

from app.integrations.normalization import calendar_facts, mail_facts
from app.repositories.audit import evidence_source
from app.services.evidence_minimization import minimize_raw_data


def test_gmail_and_outlook_discard_bodies_and_attachment_metadata():
    private = "private message text Total due: $162.00"
    gmail = {
        "id": "gmail-1",
        "threadId": "thread-1",
        "internalDate": "1791907200000",
        "payload": {
            "headers": [
                {"name": "From", "value": "Bills <billing@example.test>"},
                {"name": "Subject", "value": "Electricity bill"},
            ],
            "body": {"data": base64.urlsafe_b64encode(private.encode()).decode()},
            "parts": [
                {
                    "mimeType": "text/plain",
                    "body": {
                        "data": base64.urlsafe_b64encode(private.encode()).decode()
                    },
                },
                {
                    "filename": "private.pdf",
                    "mimeType": "application/pdf",
                    "body": {"size": 1234},
                }
            ],
        },
    }
    outlook = {
        "id": "outlook-1",
        "conversationId": "thread-2",
        "receivedDateTime": "2026-10-13T12:00:00Z",
        "subject": "Electricity bill",
        "from": {"emailAddress": {"address": "billing@example.test"}},
        "toRecipients": [],
        "hasAttachments": True,
        "body": {"content": private},
    }

    for facts in (mail_facts(gmail, "google"), mail_facts(outlook, "microsoft")):
        assert facts["amount"] == 162
        assert "body" not in facts
        assert "attachments" not in facts
        assert "private message text" not in str(facts)


def test_calendar_projection_discards_description_attendees_and_provider_dump():
    facts = calendar_facts(
        {
            "id": "calendar-1",
            "summary": "Approved visit",
            "description": "private calendar notes",
            "attendees": [{"email": "private@example.test"}],
            "conferenceData": {"entryPoints": [{"uri": "private-meeting-url"}]},
            "status": "confirmed",
            "start": {"dateTime": "2026-10-16T09:00:00-05:00"},
            "end": {"dateTime": "2026-10-16T10:00:00-05:00"},
            "updated": "2026-10-13T12:00:00Z",
        },
        "google",
    )

    assert facts["start"] == "2026-10-16T14:00:00+00:00"
    assert "description" not in facts and "attendees" not in facts
    assert "conferenceData" not in facts and "private" not in str(facts)


def test_evidence_metadata_allowlist_discards_provider_payloads_and_credentials():
    assert minimize_raw_data(
        {
            "provenance": "OFFICIAL_API",
            "source_event_id": "safe-reference",
            "body": "private",
            "transcript": "private",
            "attachment": {"name": "private.pdf"},
            "video": "private-url",
            "token": "private-token",
            "provider_payload": {"anything": "private"},
        }
    ) == {
        "provenance": "OFFICIAL_API",
        "source_event_id": "safe-reference",
    }


def test_amazon_order_email_keeps_true_mail_provider_provenance():
    source = evidence_source(
        SimpleNamespace(
            source="outlook_email",
            external_event_id="safe-reference",
            raw_data={
                "provenance": "OFFICIAL_API",
                "source_category": "amazon_order_email",
                "source_event_id": "safe-reference",
            },
        )
    )

    assert source["source_provider"] == "OUTLOOK"
    assert source["source_type"] == "AMAZON_ORDER_EMAIL"
    assert source["source_provenance"] == "OFFICIAL_API"
    assert source["source_reference"].startswith("sha256:")
