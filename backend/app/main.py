"""CountOn HTTP application entry point."""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy.orm import Session

from app.api.errors import ErrorEnvelope, error_response, register_exception_handlers
from app.api.operations import ExplicitCORSMiddleware, OperationalMiddleware
from app.api.v1.router import router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import get_db
from app.services.readiness import database_ready


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    from app.core.rate_limit import MemoryRateLimiter

    app.state.rate_limiter = MemoryRateLimiter(get_settings())
    from app.agent.session import AgentSessionStore

    app.state.agent_sessions = AgentSessionStore(
        ttl_seconds=get_settings().clarification_ttl_seconds
    )
    from app.alexa.adapter import AlexaConversationStore

    app.state.alexa_sessions = AlexaConversationStore(
        ttl_seconds=get_settings().clarification_ttl_seconds
    )
    yield


app = FastAPI(
    title="CountOn API",
    version="0.1.0",
    lifespan=lifespan,
    responses={
        status: {"model": ErrorEnvelope}
        for status in (400, 401, 404, 405, 409, 422, 429, 500, 503)
    },
)
settings = get_settings()
app.add_middleware(
    ExplicitCORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Request-ID"],
    expose_headers=["X-Request-ID", "Retry-After"],
)
app.add_middleware(OperationalMiddleware, settings=settings)
register_exception_handlers(app)
app.include_router(router, prefix="/api/v1")


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok", "service": "counton-api"}


@app.get("/ready", tags=["health"])
def ready(db: Session = Depends(get_db)):  # noqa: B008 - FastAPI dependency declaration
    if not database_ready(db):
        return error_response(503, "NOT_READY", "Service dependencies are not ready")
    return {"status": "ready", "service": "counton-api"}
