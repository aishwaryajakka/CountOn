"""Integrity-protected, user-bound continuation state; not an authentication JWT."""

import base64
import hashlib
import hmac
import secrets
from functools import lru_cache
from uuid import UUID

from pydantic import ValidationError

from app.core.config import Settings
from app.schemas.clarification import ClarificationState


class StateError(Exception):
    def __init__(self, code: str = "TOOL_VALIDATION_ERROR") -> None:
        self.code = code
        super().__init__(code)


@lru_cache(maxsize=1)
def development_key() -> bytes:
    # Development only. Restart invalidates in-flight conversations.
    return secrets.token_bytes(32)


def signing_key(settings: Settings) -> bytes:
    configured = settings.counton_clarification_signing_key
    if configured:
        key = configured.get_secret_value().encode()
        if len(key) >= 32:
            return key
        raise StateError("CLARIFICATION_UNAVAILABLE")
    if settings.environment == "production":
        raise StateError("CLARIFICATION_UNAVAILABLE")
    return development_key()


def signature(payload: str, user_id: UUID, key: bytes) -> str:
    # Principal is bound by the signature, not stored in conversation state.
    return hmac.new(
        key,
        ("counton-clarification-v1:" + str(user_id) + ":" + payload).encode(),
        hashlib.sha256,
    ).hexdigest()


def encode_state(state: ClarificationState, user_id: UUID, settings: Settings) -> str:
    payload = (
        base64.urlsafe_b64encode(state.model_dump_json().encode()).decode().rstrip("=")
    )
    token = payload + "." + signature(payload, user_id, signing_key(settings))
    if len(token) > 24000:
        raise StateError("CLARIFICATION_UNAVAILABLE")
    return token


def decode_state(token: str, user_id: UUID, settings: Settings) -> ClarificationState:
    key = signing_key(settings)
    try:
        if len(token) > 24000:
            raise ValueError()
        payload, supplied = token.split(".")
        if not hmac.compare_digest(supplied, signature(payload, user_id, key)):
            raise ValueError()
        raw = base64.b64decode(
            payload + "=" * (-len(payload) % 4), altchars=b"-_", validate=True
        )
        return ClarificationState.model_validate_json(raw)
    except (ValueError, ValidationError):
        raise StateError() from None
