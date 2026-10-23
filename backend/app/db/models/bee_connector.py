"""Local Bee CLI pairing, staged imports, and explicit expectation bindings."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BeeCliPairing(Base):
    __tablename__ = "bee_cli_pairings"
    id: Mapped[UUID] = mapped_column(PGUUID, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PGUUID, ForeignKey("profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    code_digest: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BeeCliCredential(Base):
    __tablename__ = "bee_cli_credentials"
    __table_args__ = (
        ForeignKeyConstraint(
            ["connection_id", "user_id"],
            ["integration_connections.id", "integration_connections.user_id"],
            ondelete="CASCADE",
            name="fk_bee_cli_connection_owner",
        ),
        UniqueConstraint("connection_id", name="uq_bee_cli_connection"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID, primary_key=True, default=uuid4)
    connection_id: Mapped[UUID] = mapped_column(PGUUID, nullable=False)
    user_id: Mapped[UUID] = mapped_column(PGUUID, nullable=False, index=True)
    token_digest: Mapped[str] = mapped_column(String(64), unique=True)
    cli_version: Mapped[str] = mapped_column(String(64))
    checkpoint: Mapped[str | None] = mapped_column(String(512))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BeeImportCandidate(Base):
    __tablename__ = "bee_import_candidates"
    __table_args__ = (
        ForeignKeyConstraint(
            ["connection_id", "user_id"],
            ["integration_connections.id", "integration_connections.user_id"],
            ondelete="CASCADE",
            name="fk_bee_candidate_connection_owner",
        ),
        UniqueConstraint("connection_id", "external_id", name="uq_bee_candidate_external"),
        CheckConstraint("category IN ('fact','todo','conversation','journal')", name="ck_bee_candidate_category"),
        CheckConstraint("status IN ('pending','imported','rejected')", name="ck_bee_candidate_status"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID, primary_key=True, default=uuid4)
    connection_id: Mapped[UUID] = mapped_column(PGUUID, nullable=False)
    user_id: Mapped[UUID] = mapped_column(PGUUID, nullable=False, index=True)
    external_id: Mapped[str] = mapped_column(String(255))
    version: Mapped[str] = mapped_column(String(64))
    category: Mapped[str] = mapped_column(String(20))
    summary: Mapped[str] = mapped_column(String(1000))
    fact: Mapped[dict] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float] = mapped_column(Float, default=0.7, server_default="0.7")
    status: Mapped[str] = mapped_column(String(20), default="pending", server_default="pending")
    imported_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BeeExpectationBinding(Base):
    __tablename__ = "bee_expectation_bindings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["connection_id", "user_id"],
            ["integration_connections.id", "integration_connections.user_id"],
            ondelete="CASCADE",
            name="fk_bee_binding_connection_owner",
        ),
        ForeignKeyConstraint(
            ["expectation_id", "user_id"],
            ["expectations.id", "expectations.user_id"],
            ondelete="CASCADE",
            name="fk_bee_binding_expectation_owner",
        ),
        UniqueConstraint("connection_id", "expectation_id", name="uq_bee_expectation_binding"),
    )
    id: Mapped[UUID] = mapped_column(PGUUID, primary_key=True, default=uuid4)
    connection_id: Mapped[UUID] = mapped_column(PGUUID, nullable=False)
    expectation_id: Mapped[UUID] = mapped_column(PGUUID, nullable=False)
    user_id: Mapped[UUID] = mapped_column(PGUUID, nullable=False, index=True)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
