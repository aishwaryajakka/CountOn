"""Preferences and a fenced outbox; in-app persistence remains reliable delivery."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NotificationPreference(Base):
    __tablename__ = "notification_preferences"
    __table_args__ = (
        CheckConstraint(
            "quiet_start_hour BETWEEN 0 AND 23 AND quiet_end_hour BETWEEN 0 AND 23",
            name="ck_preference_hours",
        ),
    )
    user_id: Mapped[UUID] = mapped_column(
        PGUUID, ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    email_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    encrypted_recipient: Mapped[str | None] = mapped_column(Text)
    mismatch_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    deadline_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    connection_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    quiet_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    quiet_start_hour: Mapped[int] = mapped_column(
        Integer, default=22, server_default="22"
    )
    quiet_end_hour: Mapped[int] = mapped_column(Integer, default=8, server_default="8")
    timezone: Mapped[str] = mapped_column(
        String(64), default="UTC", server_default="UTC"
    )


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["notification_id", "user_id"],
            ["notifications.id", "notifications.user_id"],
            ondelete="CASCADE",
            name="fk_delivery_owner",
        ),
        UniqueConstraint("notification_id", "channel", name="uq_delivery_channel"),
        CheckConstraint(
            "channel = 'email' AND status IN ('pending','running','sent','failed','cancelled')",
            name="ck_delivery_status",
        ),
        Index("ix_delivery_due", "status", "next_run_at"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID, primary_key=True, default=uuid4)
    notification_id: Mapped[UUID] = mapped_column(PGUUID)
    user_id: Mapped[UUID] = mapped_column(PGUUID)
    channel: Mapped[str] = mapped_column(
        String(20), default="email", server_default="email"
    )
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending"
    )
    next_run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    lease_token: Mapped[UUID | None] = mapped_column(PGUUID)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    first_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    encrypted_payload: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(String(50))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
