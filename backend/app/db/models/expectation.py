"""Expectation persistence and domain classification enums."""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, Float, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.evidence import Evidence
    from app.db.models.evaluation import Evaluation


class ExpectationStatus(StrEnum):
    monitoring = "monitoring"
    fulfilled = "fulfilled"
    contradicted = "contradicted"
    unknown = "unknown"
    resolved = "resolved"
    cancelled = "cancelled"


class ExpectationType(StrEnum):
    numeric_comparison = "numeric_comparison"
    boolean = "boolean"
    temporal = "temporal"
    event = "event"


class ComparisonType(StrEnum):
    less_than = "less_than"
    less_than_or_equal = "less_than_or_equal"
    greater_than = "greater_than"
    greater_than_or_equal = "greater_than_or_equal"
    equal = "equal"
    not_equal = "not_equal"


class Expectation(Base):
    __tablename__ = "expectations"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID | None] = mapped_column(PGUUID(as_uuid=True), index=True)
    claim: Mapped[str] = mapped_column(Text)
    type: Mapped[ExpectationType] = mapped_column(Enum(ExpectationType, name="expectation_type"))
    metric: Mapped[str | None] = mapped_column(String(100))
    comparison: Mapped[ComparisonType | None] = mapped_column(Enum(ComparisonType, name="comparison_type"))
    baseline: Mapped[Decimal | None] = mapped_column(Numeric)
    target_value: Mapped[Decimal | None] = mapped_column(Numeric)
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    evidence_sources: Mapped[list[str]] = mapped_column(
        ARRAY(String), default=list, server_default=text("ARRAY[]::varchar[]")
    )
    materiality_threshold: Mapped[float] = mapped_column(Float, default=0.05, server_default="0.05")
    status: Mapped[ExpectationStatus] = mapped_column(
        Enum(ExpectationStatus, name="expectation_status"),
        default=ExpectationStatus.monitoring, server_default="monitoring", index=True,
    )
    compiler_metadata: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    evidence: Mapped[list["Evidence"]] = relationship(
        back_populates="expectation", passive_deletes="all"
    )
    evaluations: Mapped[list["Evaluation"]] = relationship(
        back_populates="expectation", passive_deletes="all"
    )
