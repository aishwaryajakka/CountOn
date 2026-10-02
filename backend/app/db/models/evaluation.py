"""Persisted deterministic results; EvaluationResult is shared across layers."""

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, Float, ForeignKey, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.evaluators.base import EvaluationResult

if TYPE_CHECKING:
    from app.db.models.expectation import Expectation


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (UniqueConstraint("id", "expectation_id", name="uq_evaluation_expectation"),)

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    expectation_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("expectations.id", ondelete="CASCADE"), index=True
    )
    result: Mapped[EvaluationResult] = mapped_column(
        Enum(EvaluationResult, name="evaluation_result"), index=True
    )
    expected: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    observed: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    confidence: Mapped[float] = mapped_column(Float, default=1.0, server_default="1.0")
    reasoning: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expectation: Mapped["Expectation"] = relationship(back_populates="evaluations")
