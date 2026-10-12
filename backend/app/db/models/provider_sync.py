"""Backend-owned sync leases, encrypted projections, bindings and watch secrets."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ProviderSyncState(Base):
    __tablename__ = "provider_sync_states"
    __table_args__ = (
        UniqueConstraint("id", "user_id", name="uq_sync_owner"),
        UniqueConstraint("connection_id", "stream", name="uq_sync_stream"),
        ForeignKeyConstraint(
            ["connection_id", "user_id"],
            ["integration_connections.id", "integration_connections.user_id"],
            ondelete="CASCADE",
            name="fk_sync_connection_owner",
        ),
        CheckConstraint(
            "status IN ('pending','running','paused','error','auth_required')",
            name="ck_sync_status",
        ),
        Index("ix_provider_sync_due", "status", "next_run_at"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID, primary_key=True, default=uuid4)
    connection_id: Mapped[UUID] = mapped_column(PGUUID)
    user_id: Mapped[UUID] = mapped_column(PGUUID)
    stream: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending"
    )
    encrypted_checkpoint: Mapped[str | None] = mapped_column(Text)
    next_run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    coverage_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    coverage_through_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    round_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    wake_requested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_token: Mapped[UUID | None] = mapped_column(PGUUID)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(String(50))
    round_id: Mapped[UUID] = mapped_column(PGUUID, default=uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ProviderSourceEvent(Base):
    __tablename__ = "provider_source_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["sync_id", "user_id"],
            ["provider_sync_states.id", "provider_sync_states.user_id"],
            ondelete="CASCADE",
            name="fk_source_sync_owner",
        ),
        UniqueConstraint("sync_id", "external_id", name="uq_source_event"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID, primary_key=True, default=uuid4)
    sync_id: Mapped[UUID] = mapped_column(PGUUID)
    user_id: Mapped[UUID] = mapped_column(PGUUID)
    external_id: Mapped[str] = mapped_column(String(512))
    version: Mapped[str] = mapped_column(String(64))
    encrypted_facts: Mapped[str] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    seen_round: Mapped[UUID] = mapped_column(PGUUID)


class ExpectationSourceBinding(Base):
    __tablename__ = "expectation_source_bindings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["sync_id", "user_id"],
            ["provider_sync_states.id", "provider_sync_states.user_id"],
            ondelete="CASCADE",
            name="fk_binding_sync_owner",
        ),
        ForeignKeyConstraint(
            ["expectation_id", "user_id"],
            ["expectations.id", "expectations.user_id"],
            ondelete="CASCADE",
            name="fk_binding_expectation_owner",
        ),
        UniqueConstraint("sync_id", "expectation_id", name="uq_expectation_source"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID, primary_key=True, default=uuid4)
    sync_id: Mapped[UUID] = mapped_column(PGUUID)
    expectation_id: Mapped[UUID] = mapped_column(PGUUID)
    user_id: Mapped[UUID] = mapped_column(PGUUID)
    rule: Mapped[dict] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )


class ProviderWatch(Base):
    __tablename__ = "provider_watches"
    __table_args__ = (
        ForeignKeyConstraint(
            ["sync_id", "user_id"],
            ["provider_sync_states.id", "provider_sync_states.user_id"],
            ondelete="CASCADE",
            name="fk_watch_sync_owner",
        ),
        UniqueConstraint("provider", "external_id", name="uq_provider_watch"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID, primary_key=True, default=uuid4)
    sync_id: Mapped[UUID] = mapped_column(PGUUID)
    user_id: Mapped[UUID] = mapped_column(PGUUID)
    provider: Mapped[str] = mapped_column(String(30))
    external_id: Mapped[str] = mapped_column(String(512))
    encrypted_secret: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
