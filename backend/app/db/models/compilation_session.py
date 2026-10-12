"""Durable replay ledger containing the canonical clarification state only."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import JSON, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class CompilationSession(Base):
    __tablename__ = "compilation_sessions"
    id: Mapped[UUID] = mapped_column(PGUUID, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID, index=True)
    state: Mapped[dict] = mapped_column(JSONB().with_variant(JSON(), "sqlite"))
    token_digest: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    expectation_id: Mapped[UUID | None] = mapped_column(PGUUID, nullable=True)
