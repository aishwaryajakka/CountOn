"""Encrypted recipients, timezone-aware deferral and idempotent email transport."""

import base64
import json
import secrets
from datetime import timedelta
from zoneinfo import ZoneInfo

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.integrations.provider import ProviderError


def encrypt(settings, data, identity):
    if not settings.integration_token_encryption_key:
        raise ProviderError("CREDENTIAL_UNAVAILABLE", retryable=False)
    nonce = secrets.token_bytes(12)
    key = base64.urlsafe_b64decode(
        settings.integration_token_encryption_key.get_secret_value()
    )
    return base64.urlsafe_b64encode(
        nonce
        + AESGCM(key).encrypt(
            nonce, json.dumps(data).encode(), ("notification:" + str(identity)).encode()
        )
    ).decode()


def decrypt(settings, value, identity):
    try:
        key = base64.urlsafe_b64decode(
            settings.integration_token_encryption_key.get_secret_value()
        )
        raw = base64.urlsafe_b64decode(value)
        return json.loads(
            AESGCM(key).decrypt(
                raw[:12], raw[12:], ("notification:" + str(identity)).encode()
            )
        )
    except Exception:  # noqa: BLE001 -- ciphertext and key never appear in errors
        raise ProviderError("CREDENTIAL_UNAVAILABLE", retryable=False) from None


def ready_at(preference, now):
    """Use actual UTC instants across DST folds/gaps, bounded to one local day."""
    if not preference.quiet_enabled:
        return now

    def quiet(instant):
        hour = instant.astimezone(ZoneInfo(preference.timezone)).hour
        start, end = preference.quiet_start_hour, preference.quiet_end_hour
        return start <= hour < end if start < end else hour >= start or hour < end

    if not quiet(now):
        return now
    for minutes in range(1, 1501):
        candidate = now + timedelta(minutes=minutes)
        if not quiet(candidate):
            return candidate
    return now + timedelta(days=1)


class EmailChannel:
    """Fixed official endpoint. A frozen payload/key is reused for all attempts."""

    def __init__(self, settings, *, transport=None):
        self.settings, self.transport = settings, transport

    def send(self, payload, identity):
        if not self.settings.notification_email_enabled:
            raise ProviderError("PROVIDER_DISABLED", retryable=False)
        try:
            with (
                httpx.Client(
                    transport=self.transport,
                    timeout=httpx.Timeout(10, connect=3),
                    follow_redirects=False,
                    trust_env=False,
                ) as client,
                client.stream(
                    "POST",
                    "https://api.resend.com/emails",
                    headers={
                        "Authorization": "Bearer "
                        + self.settings.notification_email_api_key.get_secret_value(),
                        "Idempotency-Key": "counton/" + str(identity),
                    },
                    json=payload,
                ) as response,
            ):
                body = bytearray()
                for chunk in response.iter_bytes():
                    body.extend(chunk)
                    if len(body) > 65536:
                        raise ProviderError("PROVIDER_RESPONSE_INVALID")
                if response.status_code in (200, 201) and isinstance(
                    json.loads(body).get("id"), str
                ):
                    return
                if (
                    response.status_code == 429
                    or response.status_code >= 500
                    or response.status_code == 409
                ):
                    raise ProviderError("PROVIDER_UNAVAILABLE")
                raise ProviderError("PERMISSION_DENIED", retryable=False)
        except (httpx.HTTPError, ValueError, AttributeError, TypeError):
            raise ProviderError("PROVIDER_UNAVAILABLE") from None
