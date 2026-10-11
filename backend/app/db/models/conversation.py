"""Backend-only encrypted state and expiring fencing leases, never bearer tokens."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConversationRecord(Base):
    __tablename__ = "conversation_records"
    __table_args__ = (
        CheckConstraint("kind IN ('agent','alexa')", name="ck_conversation_kind"),
        Index("ix_conversation_expiry", "expires_at"),
    )
    record_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(10))
    user_id: Mapped[UUID] = mapped_column(
        PGUUID, ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    reference_digest: Mapped[str | None] = mapped_column(String(64), unique=True)
    encrypted_payload: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[UUID | None] = mapped_column(PGUUID)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
