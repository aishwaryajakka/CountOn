"""Persistence adapters reuse AgentSessionState and Alexa's transport envelope."""

import json
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from time import monotonic

import anyio
from pydantic import SecretStr

from app.agent.actions import FailureCode
from app.agent.adapters import CapabilityError
from app.agent.session import AgentSessionState, AgentSessionStore, _Entry
from app.alexa.adapter import (
    AlexaConversationStore,
    AlexaSessionUnavailable,
    _Conversation,
)
from app.conversations.persistence import Lease, Records, agent_key


def state_payload(state):
    data = state.model_dump(mode="json")
    for field_name in ("clarification_reference", "pending_capture_reference"):
        value = getattr(state, field_name, None)
        if value:
            data[field_name] = value.get_secret_value()
    return data


@dataclass
class DurableEntry(_Entry):
    lease: Lease | None = field(default=None, repr=False)
    removed: bool = False


class PostgresAgentSessionStore(AgentSessionStore):
    def __init__(self, records: Records, *, ttl_seconds=900):
        super().__init__(ttl_seconds=ttl_seconds)
        self.records = records

    def create(self, user):
        from app.agent.orchestrator import principal

        principal(user)
        now = datetime.now(timezone.utc)
        state = AgentSessionState(
            created_at=now, expires_at=now + timedelta(seconds=self.ttl_seconds)
        )
        reference, digest = self._token()
        self.records.create(
            agent_key(user.id, state.session_id),
            "agent",
            user.id,
            state_payload(state),
            self.ttl_seconds,
            digest,
        )
        return reference

    @asynccontextmanager
    async def turn(self, user, reference):
        lease = await anyio.to_thread.run_sync(
            lambda: self.records.claim(
                user.id, digest=self._digest(reference), kind="agent"
            )
        )
        try:
            state = AgentSessionState.model_validate_json(json.dumps(lease.payload))
            if state.expires_at <= datetime.now(timezone.utc):
                raise CapabilityError(FailureCode.STATE_REJECTED)
            entry = DurableEntry(
                user.id, state, lease.reference_digest or "", lease=lease
            )
            async with entry.lock:
                # Consume this handle before any remote action. A process crash
                # after capture but before advance must not replay compilation
                # into a new draft/row. Only a successful turn issues a new handle.
                await anyio.to_thread.run_sync(
                    lambda: self.records.save(lease, lease.payload, None)
                )
                yield entry
        finally:
            await anyio.to_thread.run_sync(lambda: self.records.release(lease))

    def advance(self, entry, state):
        if (
            not isinstance(entry, DurableEntry)
            or not entry.lease
            or not entry.lock.locked()
        ):
            raise CapabilityError(FailureCode.STATE_REJECTED)
        state = AgentSessionState.model_validate(state.model_dump(mode="python"))
        if (
            state.session_id != entry.state.session_id
            or state.expires_at != entry.state.expires_at
            or state.created_at != entry.state.created_at
        ):
            raise CapabilityError(FailureCode.STATE_REJECTED)
        reference, digest = self._token()
        self.records.save(entry.lease, state_payload(state), digest)
        entry.state, entry.digest = state, digest
        return reference

    def remove(self, entry):
        if not isinstance(entry, DurableEntry) or not entry.lease:
            raise CapabilityError(FailureCode.STATE_REJECTED)
        self.records.release(entry.lease, remove=True)

    async def discard(self, user, reference):
        try:
            async with self.turn(user, reference) as entry:
                await anyio.to_thread.run_sync(lambda: self.remove(entry))
        except CapabilityError:
            pass


@dataclass
class DurableAlexaEntry(_Conversation):
    lease: Lease | None = field(default=None, repr=False)


def alexa_payload(entry):
    return {
        "reference": entry.reference.get_secret_value() if entry.reference else None,
        "awaiting_reply": entry.awaiting_reply,
        "closed": entry.closed,
        "replies": entry.replies,
    }


class PostgresAlexaConversationStore(AlexaConversationStore):
    def __init__(self, records: Records, *, ttl_seconds=900):
        super().__init__(ttl_seconds=ttl_seconds)
        self.records = records

    @asynccontextmanager
    async def turn(self, event, user):
        try:
            try:
                lease = await anyio.to_thread.run_sync(
                    lambda: self.records.claim(
                        user.id, key=event.session_key, kind="alexa"
                    )
                )
            except CapabilityError:
                # Create only for first-turn handles; conflicting/foreign/busy keys
                # still fail admission and never replace another owner's record.
                if event.reference:
                    raise
                await anyio.to_thread.run_sync(
                    lambda: self.records.create(
                        event.session_key,
                        "alexa",
                        user.id,
                        {
                            "reference": None,
                            "awaiting_reply": False,
                            "closed": False,
                            "replies": {},
                        },
                        self.ttl_seconds,
                    )
                )
                lease = await anyio.to_thread.run_sync(
                    lambda: self.records.claim(
                        user.id, key=event.session_key, kind="alexa"
                    )
                )
            payload = lease.payload
            if (
                set(payload) != {"reference", "awaiting_reply", "closed", "replies"}
                or not isinstance(payload["replies"], dict)
                or len(payload["replies"]) > 64
            ):
                raise CapabilityError(FailureCode.STATE_REJECTED)
            if (
                type(payload["closed"]) is not bool
                or type(payload["awaiting_reply"]) is not bool
            ):
                raise CapabilityError(FailureCode.STATE_REJECTED)
            reference = (
                SecretStr(payload["reference"]) if payload["reference"] else None
            )
            if reference:
                self._validate_reference(reference)
            entry = DurableAlexaEntry(
                user.id,
                monotonic()
                + max(
                    0, (lease.expires_at - datetime.now(timezone.utc)).total_seconds()
                ),
                reference=reference,
                awaiting_reply=payload["awaiting_reply"],
                closed=payload["closed"],
                replies=payload["replies"],
                lease=lease,
            )
            async with entry.lock:
                try:
                    yield entry
                finally:
                    await self.persist(entry)
        except CapabilityError:
            raise AlexaSessionUnavailable() from None
        finally:
            if "lease" in locals():
                await anyio.to_thread.run_sync(lambda: self.records.release(lease))

    @staticmethod
    def _validate_reference(reference):
        import re

        if not re.fullmatch(r"[A-Za-z0-9_-]{43}", reference.get_secret_value()):
            raise CapabilityError(FailureCode.STATE_REJECTED)

    async def persist(self, entry):
        if not isinstance(entry, DurableAlexaEntry) or not entry.lease:
            raise CapabilityError(FailureCode.STATE_REJECTED)
        await anyio.to_thread.run_sync(
            lambda: self.records.save(entry.lease, alexa_payload(entry))
        )
