"""SMTP delivery preserved from main; canonical outbox supplies consent/recipients."""

import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import Settings
from app.services.supabase_user_service import get_user_email


def send_smtp(settings, payload):
    if not all(
        (
            settings.smtp_host,
            settings.smtp_username,
            settings.smtp_password,
            settings.smtp_use_tls,
        )
    ):
        raise RuntimeError("SMTP_NOT_CONFIGURED")
    message = EmailMessage()
    message["Subject"], message["From"] = payload["subject"], payload["from"]
    message["To"] = ", ".join(payload["to"])
    message.set_content(payload["text"])
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        smtp.ehlo()
        smtp.starttls(context=ssl.create_default_context())
        smtp.ehlo()
        smtp.login(settings.smtp_username, settings.smtp_password.get_secret_value())
        refused = smtp.send_message(message)
    if refused:
        raise RuntimeError("SMTP_RECIPIENT_REJECTED")


class SmtpEmailDelivery:
    """Compatibility adapter; verifies email through the existing Supabase authority."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def deliver(self, notification) -> bool:
        if not all(
            (
                self.settings.smtp_host,
                self.settings.smtp_from_email,
                self.settings.smtp_username,
                self.settings.smtp_password,
            )
        ):
            raise RuntimeError("SMTP_NOT_CONFIGURED")
        send_smtp(
            self.settings,
            {
                "from": self.settings.smtp_from_email,
                "to": [get_user_email(notification.user_id)],
                "subject": "CountOn: expectation mismatch detected",
                "text": "CountOn detected a mismatch with one of your expectations.\n\n"
                + notification.message
                + "\n\nPlease open CountOn to review the notification.",
            },
        )
        return True
