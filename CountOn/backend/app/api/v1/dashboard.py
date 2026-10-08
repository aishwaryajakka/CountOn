"""Future dashboard routes delegate to services."""

from fastapi import APIRouter

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
