
from app.services.outlook_sync_service import _extract_evidence
from app.db.models import ExpectationStatus, ExpectationType

def test_extract_structured_outlook_evidence():
    email = {
        "subject": "CountOn evidence update",
        "body": {
            "contentType": "text",
            "content": (
                'COUNTON_EVIDENCE: {"metric":"response_time",'
                '"value":140,"unit":"ms",'
                '"observed_at":"2026-10-18T08:30:00+00:00"}'
            ),
        },
    }

    result = _extract_evidence(email)

    assert result is not None
    assert result["metric"] == "response_time"
    assert result["value"] == 140
    assert result["unit"] == "ms"


def test_ignore_normal_outlook_email():
    email = {
        "subject": "Meeting reminder",
        "body": {"content": "Let's meet tomorrow at 10 AM."},
    }

    assert _extract_evidence(email) is None


def test_ignore_evidence_without_timezone():
    email = {
        "subject": "CountOn evidence update",
        "body": {
            "content": (
                'COUNTON_EVIDENCE: {"metric":"response_time",'
                '"value":140,"observed_at":"2026-10-18T08:30:00"}'
            ),
        },
    }

    assert _extract_evidence(email) is None



from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.services import outlook_sync_service


def test_sync_creates_evidence_and_evaluates_matching_expectation(monkeypatch):
    user_id = uuid4()
    expectation_id = uuid4()
    connection_id = uuid4()
    email_id = "outlook-message-123"

    expectation = SimpleNamespace(
        id=expectation_id,
        user_id=user_id,
        metric="response_time",
        status="monitoring",
        type="numeric_comparison",
    )

    email = {
        "id": email_id,
        "internetMessageId": "<message-123@example.com>",
        "subject": "CountOn evidence",
        "receivedDateTime": "2026-10-18T08:30:00Z",
        "body": {
            "content": (
                'COUNTON_EVIDENCE: {"metric":"response_time",'
                '"value":140,"unit":"ms",'
                '"observed_at":"2026-10-18T08:30:00+00:00"}'
            )
        },
    }

    monkeypatch.setattr(
        outlook_sync_service,
        "list_outlook_emails",
        lambda *args, **kwargs: {"value": [email]},
    )
    monkeypatch.setattr(
        outlook_sync_service.expectation_service,
        "list_expectations",
        lambda *args, **kwargs: [expectation],
    )

    created = []
    evaluated = []

    def fake_add_evidence(**kwargs):
        created.append(kwargs)
        return SimpleNamespace(id=uuid4())

    def fake_evaluate(**kwargs):
        evaluated.append(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(
        outlook_sync_service.evidence_service,
        "add_evidence",
        fake_add_evidence,
    )
    monkeypatch.setattr(
        outlook_sync_service.evaluation_service,
        "evaluate_expectation",
        fake_evaluate,
    )

    result = outlook_sync_service.sync_outlook_emails(
        db=object(),
        connection_id=connection_id,
        user_id=user_id,
        top=10,
    )

    assert result["emails_fetched"] == 1
    assert result["evidence_processed"] == 1
    assert len(created) == 1
    assert created[0]["expectation_id"] == expectation_id
    assert created[0]["payload"].source == "microsoft_outlook"
    assert created[0]["payload"].value == {"amount": 140}
    assert len(evaluated) == 1
    assert evaluated[0]["expectation_id"] == expectation_id


def test_sync_skips_email_without_matching_expectation(monkeypatch):
    user_id = uuid4()

    email = {
        "id": "ordinary-email-456",
        "subject": "Meeting reminder",
        "body": {"content": "Let's meet tomorrow at 10 AM."},
    }

    monkeypatch.setattr(
        outlook_sync_service,
        "list_outlook_emails",
        lambda *args, **kwargs: {"value": [email]},
    )
    monkeypatch.setattr(
        outlook_sync_service.expectation_service,
        "list_expectations",
        lambda *args, **kwargs: [],
    )

    def unexpected_call(**kwargs):
        raise AssertionError("Evidence should not be created for an ordinary email")

    monkeypatch.setattr(
        outlook_sync_service.evidence_service,
        "add_evidence",
        unexpected_call,
    )

    result = outlook_sync_service.sync_outlook_emails(
        db=object(),
        connection_id=uuid4(),
        user_id=user_id,
        top=10,
    )

    assert result["emails_fetched"] == 1
    assert result["evidence_processed"] == 0
    assert result["emails_skipped"] == 1




from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.services import outlook_sync_service


def test_sync_creates_evidence_and_evaluates_matching_expectation(monkeypatch):
    user_id = uuid4()
    expectation_id = uuid4()
    connection_id = uuid4()
    email_id = "outlook-message-123"

    expectation = SimpleNamespace(
        id=expectation_id,
        user_id=user_id,
        metric="response_time",
        status="monitoring",
        type="numeric_comparison",
    )

    email = {
        "id": email_id,
        "internetMessageId": "<message-123@example.com>",
        "subject": "CountOn evidence",
        "receivedDateTime": "2026-10-18T08:30:00Z",
        "body": {
            "content": (
                'COUNTON_EVIDENCE: {"metric":"response_time",'
                '"value":140,"unit":"ms",'
                '"observed_at":"2026-10-18T08:30:00+00:00"}'
            )
        },
    }

    monkeypatch.setattr(
        outlook_sync_service,
        "list_outlook_emails",
        lambda *args, **kwargs: {"value": [email]},
    )
    monkeypatch.setattr(
        outlook_sync_service.expectation_service,
        "list_expectations",
        lambda *args, **kwargs: [expectation],
    )

    created = []
    evaluated = []

    def fake_add_evidence(**kwargs):
        created.append(kwargs)
        return SimpleNamespace(id=uuid4())

    def fake_evaluate(**kwargs):
        evaluated.append(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(
        outlook_sync_service.evidence_service,
        "add_evidence",
        fake_add_evidence,
    )
    monkeypatch.setattr(
        outlook_sync_service.evaluation_service,
        "evaluate_expectation",
        fake_evaluate,
    )

    result = outlook_sync_service.sync_outlook_emails(
        db=object(),
        connection_id=connection_id,
        user_id=user_id,
        top=10,
    )

    assert result["emails_fetched"] == 1
    assert result["evidence_processed"] == 1
    assert len(created) == 1
    assert created[0]["expectation_id"] == expectation_id
    assert created[0]["payload"].source == "microsoft_outlook"
    assert created[0]["payload"].value == {"amount": 140}
    assert len(evaluated) == 1
    assert evaluated[0]["expectation_id"] == expectation_id


def test_sync_skips_email_without_matching_expectation(monkeypatch):
    user_id = uuid4()

    email = {
        "id": "ordinary-email-456",
        "subject": "Meeting reminder",
        "body": {"content": "Let's meet tomorrow at 10 AM."},
    }

    monkeypatch.setattr(
        outlook_sync_service,
        "list_outlook_emails",
        lambda *args, **kwargs: {"value": [email]},
    )
    monkeypatch.setattr(
        outlook_sync_service.expectation_service,
        "list_expectations",
        lambda *args, **kwargs: [],
    )

    def unexpected_call(**kwargs):
        raise AssertionError("Evidence should not be created for an ordinary email")

    monkeypatch.setattr(
        outlook_sync_service.evidence_service,
        "add_evidence",
        unexpected_call,
    )

    result = outlook_sync_service.sync_outlook_emails(
        db=object(),
        connection_id=uuid4(),
        user_id=user_id,
        top=10,
    )

    assert result["emails_fetched"] == 1
    assert result["evidence_processed"] == 0
    assert result["emails_skipped"] == 1


def test_sync_processes_repeated_outlook_message(monkeypatch):
    user_id = uuid4()
    expectation_id = uuid4()

    expectation = SimpleNamespace(
        id=expectation_id,
        status=ExpectationStatus.monitoring,
        type=ExpectationType.numeric_comparison,
        metric="response_time",
    )

    email = {
        "id": "repeated-message-123",
        "internetMessageId": "<repeated@example.com>",
        "subject": "CountOn evidence",
        "receivedDateTime": "2026-10-18T08:30:00Z",
        "body": {
            "content": (
                'COUNTON_EVIDENCE: {"metric":"response_time",'
                '"value":140,"unit":"ms",'
                '"observed_at":"2026-10-18T08:30:00+00:00"}'
            )
        },
    }

    monkeypatch.setattr(
        outlook_sync_service,
        "list_outlook_emails",
        lambda *args, **kwargs: {"value": [email, email]},
    )
    monkeypatch.setattr(
        outlook_sync_service.expectation_service,
        "list_expectations",
        lambda *args, **kwargs: [expectation],
    )

    evidence_calls = []
    evaluation_calls = []

    def fake_add_evidence(**kwargs):
        evidence_calls.append(kwargs)
        return SimpleNamespace(id=uuid4())

    def fake_evaluate(**kwargs):
        evaluation_calls.append(kwargs)
        return SimpleNamespace()

    monkeypatch.setattr(
        outlook_sync_service.evidence_service,
        "add_evidence",
        fake_add_evidence,
    )
    monkeypatch.setattr(
        outlook_sync_service.evaluation_service,
        "evaluate_expectation",
        fake_evaluate,
    )

    result = outlook_sync_service.sync_outlook_emails(
        db=object(),
        connection_id=uuid4(),
        user_id=user_id,
        top=10,
    )

    assert result["emails_fetched"] == 2
    assert result["evidence_processed"] == 2
    assert len(evidence_calls) == 2
    assert len(evaluation_calls) == 2

    event_ids = [
        call["payload"].external_event_id
        for call in evidence_calls
    ]
    assert event_ids == ["repeated-message-123"] * 2


def test_extract_structured_evidence_with_lowercase_marker():
    email = {
        "body": {
            "content": (
                'counton_evidence: {"metric":"response_time",'
                '"value":140,"unit":"ms",'
                '"observed_at":"2026-10-18T08:30:00+00:00"}'
            )
        }
    }

    result = _extract_evidence(email)

    assert result is not None
    assert result["metric"] == "response_time"
    assert result["value"] == 140


def test_sync_skips_email_without_message_id(monkeypatch):
    user_id = uuid4()
    connection_id = uuid4()

    monkeypatch.setattr(
        outlook_sync_service,
        "list_outlook_emails",
        lambda *args, **kwargs: {
            "value": [
                {
                    "subject": "CountOn evidence",
                    "body": {
                        "content": (
                            'COUNTON_EVIDENCE: {"metric": "revenue", '
                            '"value": 6000, '
                            '"observed_at": "2026-10-18T09:00:00Z"}'
                        )
                    },
                }
            ]
        },
    )

    monkeypatch.setattr(
        outlook_sync_service.expectation_service,
        "list_expectations",
        lambda *args, **kwargs: [],
    )

    def fail_if_called(*args, **kwargs):
        raise AssertionError("Evidence must not be created without a message ID")

    monkeypatch.setattr(
        outlook_sync_service.evidence_service,
        "add_evidence",
        fail_if_called,
    )

    result = outlook_sync_service.sync_outlook_emails(
        db=None,
        connection_id=connection_id,
        user_id=user_id,
    )

    assert result["emails_fetched"] == 1
    assert result["evidence_processed"] == 0
    assert result["emails_skipped"] == 1
    assert result["messages"][0]["reason"] == (
        "Email is missing a valid message ID"
    )
