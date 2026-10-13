"""Bounded server-only context; opaque one-turn handles are not auth tokens."""

import asyncio
import hashlib
import re
import secrets
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import AwareDatetime, BaseModel, Field, SecretStr, model_validator

from app.agent.actions import AgentAction, FailureCode
from app.agent.adapters import CapabilityError
from app.agent.models import STRICT, AgentResult, checked_reference
from app.core.auth import AuthenticatedUser


class SessionMarker(StrEnum):
    READY = "READY"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class AgentSessionState(BaseModel):
    """Trusted internal state only. Never accept this object from client JSON."""

    model_config = STRICT
    version: Literal["v1"] = "v1"
    session_id: UUID = Field(default_factory=uuid4)
    selected_expectation_id: UUID | None = None
    clarification_reference: SecretStr | None = Field(default=None, repr=False)
    last_action: AgentAction | None = None
    pending_disambiguation_ids: tuple[UUID, ...] = Field(default=(), max_length=10)
    created_at: AwareDatetime
    expires_at: AwareDatetime
    marker: SessionMarker = SessionMarker.READY

    @model_validator(mode="after")
    def bounded_context(self) -> "AgentSessionState":
        if not timedelta(0) < self.expires_at - self.created_at <= timedelta(hours=1):
            raise ValueError("Invalid bounded session lifetime")
        if len(set(self.pending_disambiguation_ids)) != len(
            self.pending_disambiguation_ids
        ):
            raise ValueError("Selection candidates must be unique")
        if self.pending_disambiguation_ids and self.selected_expectation_id is not None:
            raise ValueError("Ambiguous context cannot have a selected expectation")
        checked_reference(self.clarification_reference)
        if (
            self.marker != SessionMarker.READY
            and self.clarification_reference is not None
        ):
            raise ValueError("Terminal draft cannot retain clarification state")
        return self


class AgentSessionResult(BaseModel):
    model_config = STRICT
    result: AgentResult
    # Private by default. A future authenticated route must explicitly transport
    # only this opaque handle, never the internal state or compiler reference.
    session_reference: SecretStr | None = Field(default=None, repr=False)


@dataclass
class _Entry:
    owner: UUID
    state: AgentSessionState
    digest: str
    lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)


class AgentSessionStore:
    """Single-process store with bounded fixed TTL and atomic handle rotation.

    Identity is trusted auth context, separate from the state. Unknown, expired,
    cross-user, rotated or malformed handles all fail identically. No tombstone or
    transcript history is retained. Existing MCP ledger owns durable write replay.
    """

    def __init__(
        self,
        *,
        ttl_seconds: int = 900,
        max_sessions: int = 1024,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not 60 <= ttl_seconds <= 3600 or not 1 <= max_sessions <= 10000:
            raise ValueError("Invalid bounded session configuration")
        self.ttl_seconds = ttl_seconds
        self.max_sessions = max_sessions
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._entries: dict[str, _Entry] = {}

    def _digest(self, reference: SecretStr) -> str:
        if not isinstance(reference, SecretStr) or not re.fullmatch(
            r"[A-Za-z0-9_-]{43}", reference.get_secret_value()
        ):
            raise CapabilityError(FailureCode.STATE_REJECTED)
        return hashlib.sha256(reference.get_secret_value().encode()).hexdigest()

    def _token(self) -> tuple[SecretStr, str]:
        reference = SecretStr(secrets.token_urlsafe(32))
        return reference, self._digest(reference)

    def _prune(self) -> None:
        now = self._clock()
        for digest, entry in tuple(self._entries.items()):
            if entry.state.expires_at <= now and not entry.lock.locked():
                del self._entries[digest]

    def create(self, user: AuthenticatedUser) -> SecretStr:
        if not isinstance(user, AuthenticatedUser):
            raise CapabilityError(FailureCode.UNAUTHORIZED)
        self._prune()
        if len(self._entries) >= self.max_sessions:
            raise CapabilityError(FailureCode.UNAVAILABLE)
        now = self._clock()
        state = AgentSessionState(
            created_at=now, expires_at=now + timedelta(seconds=self.ttl_seconds)
        )
        reference, digest = self._token()
        self._entries[digest] = _Entry(user.id, state, digest)
        return reference

    @asynccontextmanager
    async def turn(
        self, user: AuthenticatedUser, reference: SecretStr
    ) -> AsyncIterator[_Entry]:
        if not isinstance(user, AuthenticatedUser):
            raise CapabilityError(FailureCode.UNAUTHORIZED)
        digest = self._digest(reference)
        entry = self._entries.get(digest)
        if entry is None or entry.owner != user.id:
            raise CapabilityError(FailureCode.STATE_REJECTED)
        async with entry.lock:
            if (
                self._entries.get(digest) is not entry
                or entry.state.expires_at <= self._clock()
            ):
                self._entries.pop(digest, None)
                raise CapabilityError(FailureCode.STATE_REJECTED)
            # Revalidate trusted snapshots too; version/forbidden fields cannot
            # sneak in via model_construct or a future storage adapter.
            try:
                entry.state = AgentSessionState.model_validate(
                    entry.state.model_dump(mode="python")
                )
            except ValueError:
                self._entries.pop(digest, None)
                raise CapabilityError(FailureCode.STATE_REJECTED) from None
            yield entry

    def advance(self, entry: _Entry, state: AgentSessionState) -> SecretStr:
        # Called only inside the entry lock. No await between revoke and replace.
        if not entry.lock.locked():
            raise CapabilityError(FailureCode.STATE_REJECTED)
        state = AgentSessionState.model_validate(state.model_dump(mode="python"))
        if (
            state.session_id != entry.state.session_id
            or state.created_at != entry.state.created_at
            or state.expires_at != entry.state.expires_at
        ):
            raise CapabilityError(FailureCode.STATE_REJECTED)
        if self._entries.get(entry.digest) is not entry:
            raise CapabilityError(FailureCode.STATE_REJECTED)
        reference, digest = self._token()
        del self._entries[entry.digest]
        entry.digest, entry.state = digest, state
        self._entries[digest] = entry
        return reference

    def remove(self, entry: _Entry) -> None:
        self._entries.pop(entry.digest, None)

    async def discard(self, user: AuthenticatedUser, reference: SecretStr) -> None:
        """Revoke a transport session without starting another conversation."""
        try:
            async with self.turn(user, reference) as entry:
                self.remove(entry)
        except CapabilityError:
            pass  # Already rotated, expired or another owner's handle: no action.
