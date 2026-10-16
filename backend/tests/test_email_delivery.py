
"""Tests for the SMTP notification email adapter."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.services.email_delivery import SmtpEmailDelivery


@pytest.fixture
def settings():
    return SimpleNamespace(
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        smtp_from_email="sender@example.com",
        smtp_username="sender@example.com",
        smtp_password=MagicMock(),
        smtp_use_tls=True,
    )


@pytest.fixture
def notification():
    return SimpleNamespace(
        user_id=uuid4(),
        message="Your expectation was contradicted.",
    )


def test_deliver_sends_email_using_tls(settings, notification):
    settings.smtp_password.get_secret_value.return_value = "test-password"

    with (
        patch(
            "app.services.email_delivery.get_user_email",
            return_value="recipient@example.com",
        ),
        patch("app.services.email_delivery.smtplib.SMTP") as smtp_class,
    ):
        smtp = smtp_class.return_value.__enter__.return_value
        smtp.send_message.return_value = {}

        result = SmtpEmailDelivery(settings).deliver(notification)

    assert result is True
    smtp_class.assert_called_once_with(
        "smtp.gmail.com", 587, timeout=10
    )
    smtp.starttls.assert_called_once()
    smtp.login.assert_called_once_with(
        "sender@example.com", "test-password"
    )

    message = smtp.send_message.call_args.args[0]
    assert message["To"] == "recipient@example.com"
    assert "mismatch" in message["Subject"].lower()
    assert "Your expectation was contradicted." in message.get_content()


def test_deliver_fails_when_smtp_is_not_configured(
    settings, notification
):
    settings.smtp_password = None

    with pytest.raises(RuntimeError, match="SMTP_NOT_CONFIGURED"):
        SmtpEmailDelivery(settings).deliver(notification)


def test_deliver_fails_when_recipient_is_rejected(
    settings, notification
):
    settings.smtp_password.get_secret_value.return_value = "test-password"

    with (
        patch(
            "app.services.email_delivery.get_user_email",
            return_value="recipient@example.com",
        ),
        patch("app.services.email_delivery.smtplib.SMTP") as smtp_class,
    ):
        smtp = smtp_class.return_value.__enter__.return_value
        smtp.send_message.return_value = {
            "recipient@example.com": (550, b"Rejected")
        }

        with pytest.raises(
            RuntimeError, match="SMTP_RECIPIENT_REJECTED"
        ):
            SmtpEmailDelivery(settings).deliver(notification)
