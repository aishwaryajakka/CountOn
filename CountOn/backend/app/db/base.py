"""Shared SQLAlchemy metadata for Alembic-managed models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
