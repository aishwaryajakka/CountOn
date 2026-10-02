"""Shared normalized evidence from all current and future adapters."""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, String, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.expectation import Expectation


class Evidence(Base):
    __tablename__ = "evidence"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    expectation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("expectations.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(String(100), index=True)
    metric: Mapped[str | None] = mapped_column(String(100))
    value: Mapped[dict[str, Any]] = mapped_column(JSONB)
    unit: Mapped[str | None] = mapped_column(String(50))
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    confidence: Mapped[float] = mapped_column(Float, default=1.0, server_default="1.0")
    raw_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expectation: Mapped["Expectation"] = relationship(back_populates="evidence")
