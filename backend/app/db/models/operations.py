"""Durable contracts for monitoring, notifications and redacted audit history."""
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint, Index, Integer, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, synonym
from app.db.base import Base


class MonitoringJob(Base):
    __tablename__='monitoring_jobs'
    __table_args__=(
        ForeignKeyConstraint(['expectation_id','user_id'],['expectations.id','expectations.user_id'],ondelete='CASCADE',name='fk_job_owned_expectation'),
        CheckConstraint("status IN ('pending','running','paused','completed','failed','cancelled')",name='ck_job_status'),
        CheckConstraint('attempt_count >= 0',name='ck_job_attempts'),
        Index('uq_job_active_expectation','expectation_id',unique=True,postgresql_where=text("status IN ('pending','running','paused')")),
        Index('ix_job_due','status','next_run_at'),
    )
    id: Mapped[UUID]=mapped_column(PGUUID,primary_key=True,default=uuid4)
    expectation_id: Mapped[UUID]=mapped_column(PGUUID)
    user_id: Mapped[UUID]=mapped_column(PGUUID,index=True)
    status: Mapped[str]=mapped_column(String(20),server_default='pending',default='pending')
    next_run_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    last_run_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    attempt_count: Mapped[int]=mapped_column(Integer,server_default='0',default=0)
    last_error: Mapped[str|None]=mapped_column(String(100))  # safe error code, never exception text
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now())


class Notification(Base):
    __tablename__='notifications'
    __table_args__=(CheckConstraint("status IN ('pending','read','sent','failed','dismissed')",name='ck_notification_status'),
        UniqueConstraint('evaluation_id',name='uq_notification_evaluation'),
        ForeignKeyConstraint(['expectation_id','user_id'],['expectations.id','expectations.user_id'],ondelete='CASCADE',name='fk_notification_owner'),
        Index('ix_notification_owner_created','user_id','created_at'),
        ForeignKeyConstraint(['evaluation_id','expectation_id'],['evaluations.id','evaluations.expectation_id'],ondelete='CASCADE',name='fk_notification_evaluation'),)
    id: Mapped[UUID]=mapped_column(PGUUID,primary_key=True,default=uuid4)
    expectation_id: Mapped[UUID]=mapped_column(PGUUID,ForeignKey('expectations.id',ondelete='CASCADE'),index=True)
    user_id: Mapped[UUID]=mapped_column(PGUUID,ForeignKey('profiles.id',ondelete='CASCADE'))
    type: Mapped[str]=mapped_column(String(50),default='expectation_mismatch',server_default='expectation_mismatch')
    channel: Mapped[str]=mapped_column(String(20),default='in_app',server_default='in_app')
    message: Mapped[str]=mapped_column(String(500),default='An expectation was contradicted by the latest evidence.',server_default='An expectation was contradicted by the latest evidence.')
    notification_metadata: Mapped[dict]=mapped_column('metadata',JSONB,default=dict,server_default=text("'{}'::jsonb"))
    sent_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    evaluation_id: Mapped[UUID]=mapped_column(PGUUID)
    status: Mapped[str]=mapped_column(String(20),server_default='pending',default='pending')
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'processing', 'delivered', 'failed')",
            name="ck_notification_delivery_status",
        ),
        CheckConstraint(
            "attempt_count >= 0",
            name="ck_notification_delivery_attempt_count",
        ),
        CheckConstraint(
            "max_attempts > 0",
            name="ck_notification_delivery_max_attempts",
        ),
        UniqueConstraint(
            "notification_id",
            "channel",
            name="uq_notification_delivery_channel",
        ),
        Index(
            "ix_notification_deliveries_due",
            "status",
            "next_attempt_at",
        ),
        Index(
            "ix_notification_deliveries_notification",
            "notification_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    notification_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("notifications.id", ondelete="CASCADE"),
        nullable=False,
    )
    channel: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending"
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default="0"
    )
    max_attempts: Mapped[int] = mapped_column(
        Integer, default=5, server_default="5"
    )
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_attempt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    processing_started_at: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True),
    nullable=True,
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    # Store safe error codes only, never raw provider exception messages.
    last_error: Mapped[str | None] = mapped_column(String(100))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

class AuditEvent(Base):
    __tablename__='audit_events'
    __table_args__=(Index('ix_audit_owner_created','user_id','created_at'),)
    id: Mapped[UUID]=mapped_column(PGUUID,primary_key=True,default=uuid4)
    user_id: Mapped[UUID]=mapped_column(PGUUID,ForeignKey('profiles.id',ondelete='CASCADE'),index=True)
    expectation_id: Mapped[UUID|None]=mapped_column(PGUUID,ForeignKey('expectations.id',ondelete='SET NULL'),index=True)
    entity_type: Mapped[str]=mapped_column(String(50),default='expectation',server_default='expectation')
    audit_metadata: Mapped[dict]=mapped_column('metadata',JSONB,default=dict,server_default=text("'{}'::jsonb"))
    entity_id = synonym('resource_id')
    resource_id: Mapped[UUID]=mapped_column(PGUUID)
    action: Mapped[str]=mapped_column(String(50))
    request_id: Mapped[str|None]=mapped_column(String(36))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
