"""Future compiler routes delegate to services."""

from fastapi import APIRouter

router = APIRouter(prefix="/compiler", tags=["compiler"])
