
"""Encrypted OAuth credentials for integration connections."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OAuthCredential(Base):
    __tablename__ = "oauth_credentials"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    connection_id: Mapped[UUID] = mapped_column(
        "integration_id",
        PGUUID(as_uuid=True),
        ForeignKey("integration_connections.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    user_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("profiles.id", ondelete="CASCADE"),
        nullable=False,
    )

    provider: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    encrypted_access_token: Mapped[str] = mapped_column(
        "access_token_encrypted",
        String,
        nullable=False,
    )

    encrypted_refresh_token: Mapped[str | None] = mapped_column(
        "refresh_token_encrypted",
        String,
        nullable=True,
    )

    token_type: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    scopes: Mapped[str] = mapped_column(
        String,
        nullable=False,
        default="",
        server_default="",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
