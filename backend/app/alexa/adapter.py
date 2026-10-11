"""ASK envelopes, bounded transport replay and speech; no second orchestration."""

import asyncio
import hashlib
import json
import re
from copy import deepcopy
from dataclasses import dataclass, field
from time import monotonic
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from app.agent.actions import FailureCode
from app.agent.models import AgentInput, AgentResult
from app.agent.orchestrator import AgentOrchestrator
from app.core.auth import AuthenticatedUser

from .verification import InvalidAlexaRequest

WELCOME = "Welcome to CountOn. What are you counting on?"
HELP = (
    "Ask what you're counting on, tell me about an expectation, or tell me what "
    "you expect. You can ask why something didn't match. Say cancel to stop."
)
UNCERTAIN = (
    "I couldn't finish that safely in time. Please check your CountOn records "
    "before trying to save it again."
)


class _Attributes(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    counton_session: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{43}$")


class AlexaSessionUnavailable(Exception):
    """An expired or rotated opaque reference; safe request to start again."""


@dataclass(frozen=True)
class AlexaEvent:
    kind: str
    request_id: str
    session_key: str
    digest: str
    intent: str | None
    text: str | None
    reference: SecretStr | None = field(repr=False)
    locale: str | None = None

    @classmethod
    def parse(cls, data: dict[str, Any], body: bytes) -> "AlexaEvent":
        try:
            request, session = data["request"], data["session"]
            system = data["context"]["System"]
            kind = request["type"]
            if kind not in ("LaunchRequest", "IntentRequest", "SessionEndedRequest"):
                raise InvalidAlexaRequest()
            keys = [
                system["application"]["applicationId"],
                session["sessionId"],
                system["user"]["userId"],
                request["requestId"],
            ]
            if any(
                not isinstance(key, str) or not 1 <= len(key) <= 512 for key in keys
            ):
                raise InvalidAlexaRequest()
            attrs = _Attributes.model_validate(session.get("attributes", {}))
            intent, text = None, None
            if kind == "IntentRequest":
                intent = request["intent"]["name"]
                if not isinstance(intent, str) or len(intent) > 128:
                    raise InvalidAlexaRequest()
                slots = request["intent"].get("slots", {})
                if not isinstance(slots, dict) or set(slots) - {"text"}:
                    raise InvalidAlexaRequest()
                if "text" in slots:
                    text = slots["text"].get("value")
                    if text is not None:
                        # Slots supply language only, never credentials/identity/plans.
                        text = AgentInput.nonempty_text(text)
                        if len(text) > 1800:
                            raise InvalidAlexaRequest()
            locale = request.get("locale")
            if not isinstance(locale, str) or not re.fullmatch(
                r"[a-z]{2}-[A-Z]{2}", locale
            ):
                locale = None
            return cls(
                kind=kind,
                request_id=keys[3],
                session_key=hashlib.sha256(json.dumps(keys[:3]).encode()).hexdigest(),
                digest=hashlib.sha256(body).hexdigest(),
                intent=intent,
                text=text,
                reference=SecretStr(attrs.counton_session)
                if attrs.counton_session
                else None,
                locale=locale,
            )
        except Exception:  # noqa: BLE001 - Sanitize malformed Alexa envelope fields
            raise InvalidAlexaRequest() from None


def envelope(
    speech: str | None,
    *,
    reference: SecretStr | None = None,
    end: bool = False,
    link: bool = False,
    elicit: bool = False,
) -> dict[str, Any]:
    response: dict[str, Any] = {"shouldEndSession": end}
    if speech is not None:
        response["outputSpeech"] = {"type": "PlainText", "text": speech}
        if not end:
            response["reprompt"] = {
                "outputSpeech": {
                    "type": "PlainText",
                    "text": "What would you like to do?",
                }
            }
    if link:
        response["card"] = {"type": "LinkAccount"}
    if elicit:
        # Free-form replies are elicited into the existing language slot. We do
        # not implement Alexa dialog semantics as a second clarification engine.
        response["directives"] = [
            {
                "type": "Dialog.ElicitSlot",
                "slotToElicit": "text",
                "updatedIntent": {
                    "name": "CaptureExpectationIntent",
                    "confirmationStatus": "NONE",
                    "slots": {"text": {"name": "text", "confirmationStatus": "NONE"}},
                },
            }
        ]
        response["reprompt"]["outputSpeech"]["text"] = speech
    return {
        "version": "1.0",
        "sessionAttributes": {"counton_session": reference.get_secret_value()}
        if reference and not end
        else {},
        "response": response,
    }


def link_account() -> dict[str, Any]:
    return envelope(
        "Please link or relink your CountOn account in the Alexa app first.",
        end=True,
        link=True,
    )


@dataclass
class _Conversation:
    owner: UUID
    expires_at: float
    reference: SecretStr | None = field(default=None, repr=False)
    awaiting_reply: bool = False
    closed: bool = False
    # Only safe response envelopes and request/body hashes; never tokens/history.
    replies: dict[str, tuple[str, dict[str, Any]]] = field(
        default_factory=dict, repr=False
    )
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)


class AlexaConversationStore:
    """Single-worker, bounded Alexa-session binding and request retry protection.

    Core conversation state remains in AgentSessionStore. This transport cache
    rejects missing/foreign/old handles and caches even first-turn captures so
    a genuine signed Alexa request replay cannot create a second compilation.
    """

    def __init__(self, ttl_seconds: int = 900, max_sessions: int = 1024) -> None:
        # Retain retry tombstones past the SDK's +/-150s authenticity window.
        self.ttl_seconds = max(ttl_seconds, 310)
        self.max_sessions = max_sessions
        self.entries: dict[str, _Conversation] = {}

    def entry(self, event: AlexaEvent, user: AuthenticatedUser) -> _Conversation:
        for key, previous in tuple(self.entries.items()):
            if previous.expires_at <= monotonic() and not previous.lock.locked():
                del self.entries[key]
        entry = self.entries.get(event.session_key)
        if entry is None:
            if event.reference or len(self.entries) >= self.max_sessions:
                raise AlexaSessionUnavailable()
            entry = _Conversation(user.id, monotonic() + self.ttl_seconds)
            self.entries[event.session_key] = entry
        if entry.owner != user.id:
            raise InvalidAlexaRequest()
        return entry


class AlexaAdapter:
    def __init__(self, store: AlexaConversationStore, agent: AgentOrchestrator) -> None:
        self.store, self.agent = store, agent

    @staticmethod
    def utterance(event: AlexaEvent, awaiting_reply: bool) -> str | None:
        if event.intent == "ListExpectationsIntent":
            return "What am I counting on?"
        if event.intent == "GetExpectationIntent":
            return f"Tell me about {event.text}" if event.text else None
        if event.intent == "WhyExpectationIntent":
            return f"Why did {event.text} fail?" if event.text else "Why did it fail?"
        if event.intent == "CaptureExpectationIntent" and event.text:
            if awaiting_reply or re.match(
                r"^(?:i'm counting on|i am counting on|i expect|i'm expecting|actually|change|make)\b",
                event.text.replace("’", "'"),
                re.IGNORECASE,
            ):
                return event.text
            return "I'm counting on " + event.text
        return None

    @staticmethod
    def speech(result: AgentResult) -> str:
        if result.code == FailureCode.UNAVAILABLE:
            return "CountOn can't reach its tools right now. Check your records before retrying a save."
        if result.code == FailureCode.STATE_REJECTED:
            return "That conversation has expired. Please start a new session and restate your request."
        if result.expectations and result.expectations.expectations:
            rows = result.expectations.expectations
            claims = [" ".join(row.claim.split())[:160] for row in rows[:3]]
            count = len(rows)
            prefix = (
                "Here are up to three of your expectations: "
                if count >= result.expectations.limit
                else f"You're counting on {count} {'thing' if count == 1 else 'things'}: "
            )
            return prefix + "; ".join(claims) + "."
        if result.candidates:
            choices = "; ".join(
                f"{i + 1}: {' '.join(row.claim.split())[:160]}"
                for i, row in enumerate(result.candidates[:3])
            )
            return (
                "Which expectation do you mean? "
                + choices
                + ". Say first, second, or third, or restate the topic."
            )
        if result.captured:
            return "Got it. I'll track that."
        # Speech comes exclusively from the existing controlled result, including
        # deterministic MATCH/UNKNOWN and grounded MISMATCH/fallback responses.
        return " ".join(result.answer.split())[:1200]

    async def handle(
        self,
        event: AlexaEvent,
        user: AuthenticatedUser,
        *,
        timezone: str = "UTC",
        deadline: float | None = None,
    ) -> dict[str, Any]:
        entry = self.store.entry(event, user)
        async with entry.lock:
            if entry.expires_at <= monotonic():
                raise AlexaSessionUnavailable()
            cached = entry.replies.get(event.request_id)
            if cached:
                if cached[0] != event.digest:
                    raise InvalidAlexaRequest()
                return deepcopy(cached[1])
            if (
                entry.closed
                or len(entry.replies) >= 64
                or event.reference != entry.reference
            ):
                raise AlexaSessionUnavailable()
            # Reserve before calling anything that may write; a failed/cancelled
            # first turn is never retried as a fresh capture.
            entry.replies[event.request_id] = (
                event.digest,
                envelope(UNCERTAIN, end=True),
            )
            try:
                async with asyncio.timeout_at(deadline):
                    if event.kind == "SessionEndedRequest":
                        await self._terminate(entry, user)
                        reply = envelope(None, end=True)
                    elif event.kind == "LaunchRequest":
                        reply = envelope(WELCOME, reference=entry.reference)
                    elif event.intent == "AMAZON.HelpIntent":
                        reply = envelope(HELP, reference=entry.reference)
                    elif event.intent in ("AMAZON.CancelIntent", "AMAZON.StopIntent"):
                        await self._terminate(entry, user)
                        reply = envelope(
                            "Okay. I've closed this conversation.", end=True
                        )
                    else:
                        text = self.utterance(event, entry.awaiting_reply)
                        if text is None:
                            reply = envelope(HELP, reference=entry.reference)
                        else:
                            # Establish the same core store reference before the
                            # cancellable network call so a timed-out first turn
                            # can revoke its context as well as later turns.
                            if entry.reference is None:
                                entry.reference = self.agent.sessions.create(user)
                            turn = await self.agent.handle_session(
                                user,
                                AgentInput(
                                    text=text,
                                    timezone=timezone,
                                    locale=event.locale,
                                    compilation_id=uuid5(
                                        NAMESPACE_URL,
                                        f"counton:alexa:{user.id}:{event.session_key}:{event.request_id}",
                                    ),
                                ),
                                entry.reference,
                            )
                            entry.reference = turn.session_reference
                            entry.awaiting_reply = turn.result.clarification_required
                            if turn.result.code == FailureCode.UNAUTHORIZED:
                                reply = link_account()
                                await self._discard(entry, user)
                            else:
                                terminal = (
                                    turn.result.code == FailureCode.STATE_REJECTED
                                )
                                reply = envelope(
                                    self.speech(turn.result),
                                    reference=entry.reference,
                                    end=terminal,
                                    elicit=entry.awaiting_reply and not terminal,
                                )
                                if terminal:
                                    await self._discard(entry, user)
            except asyncio.CancelledError:
                await self._discard(entry, user)
                raise
            except Exception:  # noqa: BLE001 - Fail closed without retrying an uncertain write
                # No automatic retries: capture may already have reached MCP.
                await self._discard(entry, user)
                reply = envelope(UNCERTAIN, end=True)
            entry.replies[event.request_id] = (event.digest, deepcopy(reply))
            return reply

    async def _discard(self, entry: _Conversation, user: AuthenticatedUser) -> None:
        if entry.reference:
            await self.agent.sessions.discard(user, entry.reference)
        entry.reference, entry.awaiting_reply, entry.closed = None, False, True

    async def _terminate(self, entry: _Conversation, user: AuthenticatedUser) -> None:
        if entry.reference:
            # Consume the existing signed draft via canonical cancellation first.
            turn = await self.agent.handle_session(
                user, AgentInput(text="Never mind"), entry.reference
            )
            entry.reference = turn.session_reference
        await self._discard(entry, user)
