"""Shared API dependencies; routes inject sessions through get_db."""

from app.db.session import get_db

__all__ = ["get_db"]
