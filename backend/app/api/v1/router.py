"""Compose version-one route modules."""

from fastapi import APIRouter

from app.api.v1 import (
    compiler,
    dashboard,
    evaluations,
    evidence,
    expectations,
    notifications,
    integrations,
    oauth,
    calendar,
)

router = APIRouter()
for module in (
    expectations,
    evidence,
    evaluations,
    notifications,
    integrations,
    oauth,
    calendar,
    compiler,
    dashboard,
):
    router.include_router(module.router)