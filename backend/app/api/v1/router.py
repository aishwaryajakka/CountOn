"""Compose version-one route modules."""

from fastapi import APIRouter

from app.api.v1 import (
    agent,
    alexa,
    compiler,
    dashboard,
    evaluations,
    evidence,
    expectations,
    integrations,
    monitoring,
    notifications,
    provider_oauth,
)

router = APIRouter()
for module in (
    agent,
    alexa,
    expectations,
    evidence,
    evaluations,
    notifications,
    provider_oauth,
    integrations,
    monitoring,
    compiler,
    dashboard,
):
    router.include_router(module.router)
