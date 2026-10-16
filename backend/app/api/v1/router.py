"""Compose version-one route modules."""

from fastapi import APIRouter

from app.api.v1 import (
    compiler,
    dashboard,
    evaluations,
    evidence,
    expectations,
    integrations,
    monitoring,
    notifications,
    quality,
)

# Optional / Feature modules
try:
    from app.api.v1 import agent
except ImportError:
    agent = None

try:
    from app.api.v1 import alexa
except ImportError:
    alexa = None

try:
    from app.api.v1 import notification_preferences
except ImportError:
    notification_preferences = None

try:
    from app.api.v1 import provider_oauth
except ImportError:
    provider_oauth = None

try:
    from app.api.v1 import provider_sync
except ImportError:
    provider_sync = None

router = APIRouter()
modules = [
    expectations,
    evidence,
    evaluations,
    notifications,
    integrations,
    monitoring,
    compiler,
    dashboard,
    quality,
]
for mod in [agent, alexa, notification_preferences, provider_oauth, provider_sync]:
    if mod is not None and hasattr(mod, "router"):
        modules.append(mod)

for module in modules:
    router.include_router(module.router)
