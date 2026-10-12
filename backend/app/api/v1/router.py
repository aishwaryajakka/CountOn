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
    notification_preferences,
    notifications,
    provider_oauth,
    provider_sync,
)

router = APIRouter()
for module in (
    agent,
    alexa,
    expectations,
    evidence,
    evaluations,
    notifications,
    notification_preferences,
    provider_oauth,
    provider_sync,
    integrations,
    monitoring,
    compiler,
    dashboard,
):
    router.include_router(module.router)
