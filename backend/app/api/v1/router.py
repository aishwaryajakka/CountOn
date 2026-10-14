"""Compose version-one route modules."""

from fastapi import APIRouter

from app.api.v1 import (
    agent,
    alexa,
    amazon_auth,
    audit,
    bee_connector,
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
):
    router.include_router(module.router)
