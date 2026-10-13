"""Short DB transactions and fenced, encrypted snapshots; no I/O under row locks."""

import base64
import hashlib
import json
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import delete, func, or_, select, text, update

from app.agent.actions import FailureCode
from app.agent.adapters import CapabilityError
from app.db.models import ConversationRecord
from app.db.session import SessionLocal


@dataclass
class Lease:
    key: str
    owner: UUID
    fence: UUID
    kind: str
    created_at: datetime
    expires_at: datetime
    reference_digest: str | None
    payload: dict = field(repr=False)


class Records:
    def __init__(self, key: str, session_factory=SessionLocal, max_sessions=1024):
        self.key = base64.urlsafe_b64decode(key)
        if len(self.key) != 32:
            raise ValueError("Conversation key must contain 32 bytes")
        self.sessions, self.max_sessions = session_factory, max_sessions

    def encrypt(self, payload: dict, kind: str, owner: UUID, key: str) -> str:
        raw = json.dumps(payload, allow_nan=False).encode()
        if len(raw) > 262144:
            raise CapabilityError(FailureCode.STATE_REJECTED)
        nonce = secrets.token_bytes(12)
        return base64.urlsafe_b64encode(
            nonce
            + AESGCM(self.key).encrypt(nonce, raw, f"{kind}:{owner}:{key}".encode())
        ).decode()

    def decrypt(self, row: ConversationRecord) -> dict:
        try:
            raw = base64.urlsafe_b64decode(row.encrypted_payload)
            value = json.loads(
                AESGCM(self.key).decrypt(
                    raw[:12],
                    raw[12:],
                    f"{row.kind}:{row.user_id}:{row.record_key}".encode(),
                )
            )
            if not isinstance(value, dict):
                raise TypeError()
            return value
        except (ValueError, TypeError, InvalidTag):
            raise CapabilityError(FailureCode.STATE_REJECTED) from None

    def create(self, key, kind, owner, payload, ttl, digest=None):
        with self.sessions() as db:
            # Serialize bounded-capacity admission, not remote tool execution.
            db.execute(text("SELECT pg_advisory_xact_lock(1129270868)"))
            now = db.scalar(select(func.clock_timestamp()))
            db.execute(
                delete(ConversationRecord).where(
                    ConversationRecord.expires_at <= now,
                    or_(
                        ConversationRecord.lease_expires_at.is_(None),
                        ConversationRecord.lease_expires_at <= now,
                    ),
                )
            )
            if (
                db.scalar(select(func.count()).select_from(ConversationRecord))
                >= self.max_sessions
            ):
                raise CapabilityError(FailureCode.UNAVAILABLE)
            if db.get(ConversationRecord, key):
                raise CapabilityError(FailureCode.STATE_REJECTED)
            row = ConversationRecord(
                record_key=key,
                kind=kind,
                user_id=owner,
                reference_digest=digest,
                encrypted_payload=self.encrypt(payload, kind, owner, key),
                created_at=now,
                expires_at=now + timedelta(seconds=ttl),
            )
            db.add(row)
            db.commit()

    def claim(self, owner, *, key=None, digest=None, kind):
        with self.sessions() as db:
            query = select(ConversationRecord).where(
                ConversationRecord.user_id == owner, ConversationRecord.kind == kind
            )
            query = (
                query.where(ConversationRecord.record_key == key)
                if key
                else query.where(ConversationRecord.reference_digest == digest)
            )
            row = db.scalar(query.with_for_update())
            now = db.scalar(select(func.clock_timestamp()))
            if (
                row is None
                or row.expires_at <= now
                or (row.lease_expires_at and row.lease_expires_at > now)
            ):
                raise CapabilityError(FailureCode.STATE_REJECTED)
            payload = self.decrypt(row)
            fence = uuid4()
            row.lease_token = fence
            row.lease_expires_at = now + timedelta(seconds=180)
            lease = Lease(
                row.record_key,
                owner,
                fence,
                kind,
                row.created_at,
                row.expires_at,
                row.reference_digest,
                payload,
            )
            db.commit()
            return lease

    def save(self, lease: Lease, payload, digest=None):
        with self.sessions() as db:
            now = db.scalar(select(func.clock_timestamp()))
            row = db.scalar(
                select(ConversationRecord)
                .where(
                    ConversationRecord.record_key == lease.key,
                    ConversationRecord.user_id == lease.owner,
                    ConversationRecord.lease_token == lease.fence,
                    ConversationRecord.lease_expires_at > now,
                    ConversationRecord.expires_at > now,
                )
                .with_for_update()
            )
            if row is None:
                raise CapabilityError(FailureCode.STATE_REJECTED)
            row.encrypted_payload = self.encrypt(
                payload, lease.kind, lease.owner, lease.key
            )
            row.reference_digest = digest
            db.commit()
            lease.payload = payload
            lease.reference_digest = digest

    def release(self, lease, *, remove=False):
        with self.sessions() as db:
            filters = (
                ConversationRecord.record_key == lease.key,
                ConversationRecord.user_id == lease.owner,
                ConversationRecord.lease_token == lease.fence,
            )
            if remove:
                db.execute(delete(ConversationRecord).where(*filters))
            else:
                db.execute(
                    update(ConversationRecord)
                    .where(*filters)
                    .values(lease_token=None, lease_expires_at=None)
                )
            db.commit()


def agent_key(owner: UUID, session_id: UUID) -> str:
    return hashlib.sha256(f"agent:{owner}:{session_id}".encode()).hexdigest()
