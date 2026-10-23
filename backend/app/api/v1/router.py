"""Compose version-one route modules."""

from fastapi import APIRouter

from app.api.v1 import (
    agent,
    alexa,
    amazon_auth,
    audit,
    bee_connector,
    calendar,
    compiler,
    dashboard,
    evaluations,
    evidence,
    expectations,
    integrations,
    manual_events,
    monitoring,
    notification_preferences,
    notifications,
    oauth,
    provider_oauth,
    provider_sync,
    simulators,
)

router = APIRouter()
for module in (
    agent,
    alexa,
    amazon_auth,
    audit,
    bee_connector,
    expectations,
    evidence,
    evaluations,
    notifications,
    notification_preferences,
    provider_oauth,
    provider_sync,
    simulators,
    integrations,
    monitoring,
    compiler,
    dashboard,
    calendar,
    oauth,
    manual_events,
):
    router.include_router(module.router)
