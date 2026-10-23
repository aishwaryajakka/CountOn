
"""SMTP adapter for CountOn mismatch notification emails."""

import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import Settings
from app.services.supabase_user_service import get_user_email


class SmtpEmailDelivery:
    """Deliver a notification to its CountOn user's verified email."""

    def __init__(self, settings: Settings):
        self.settings = settings

    def deliver(self, notification) -> bool:
        """Send an email; return True only when SMTP accepts delivery."""
        settings = self.settings

        if (
            not settings.smtp_host
            or not settings.smtp_from_email
            or not settings.smtp_username
            or not settings.smtp_password
        ):
            raise RuntimeError("SMTP_NOT_CONFIGURED")

        recipient = get_user_email(notification.user_id)

        message = EmailMessage()
        message["Subject"] = "CountOn: expectation mismatch detected"
        message["From"] = settings.smtp_from_email
        message["To"] = recipient
        message.set_content(
            "CountOn detected a mismatch with one of your expectations.\n\n"
            f"{notification.message}\n\n"
            "Please open CountOn to review the notification."
        )

        context = ssl.create_default_context()

        with smtplib.SMTP(
            settings.smtp_host,
            settings.smtp_port,
            timeout=10,
        ) as smtp:
            smtp.ehlo()

            if settings.smtp_use_tls:
                smtp.starttls(context=context)
                smtp.ehlo()

            smtp.login(
                settings.smtp_username,
                settings.smtp_password.get_secret_value(),
            )

            refused = smtp.send_message(message)

        # send_message returns a mapping of refused recipients.
        if recipient in refused:
            raise RuntimeError("SMTP_RECIPIENT_REJECTED")

        return True
