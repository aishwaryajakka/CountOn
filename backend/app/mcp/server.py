"""Standalone ASGI bootstrap; the existing FastAPI application is unchanged."""

from contextlib import asynccontextmanager

from starlette.responses import JSONResponse
from starlette.concurrency import run_in_threadpool
from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import ValidationError

from app.core.logging import configure_logging
from app.mcp.http import RequestContextMiddleware, BearerAuthMiddleware
from app.core.config import get_settings
from mcp.server.transport_security import TransportSecuritySettings
from starlette.middleware.cors import CORSMiddleware
from urllib.parse import urlsplit
from app.db.session import SessionLocal
from app.mcp.auth import current_user
from app.mcp.tools import register_tools, SessionFactory, UserResolver
from app.services.readiness import database_ready


class CountOnMCPServer(MCPServer):
    async def call_tool(self, name, arguments, context=None):
        # The SDK's validation error text includes rejected input values. Keep
        # those out of responses and SDK logs, including unknown argument names.
        if set(arguments) != {"request"}:
            raise ToolError("INVALID_ARGUMENTS: Supply only the structured request argument.")
        try:
            return await super().call_tool(name, arguments, context)
        except ToolError as error:
            if isinstance(error.__cause__, ValidationError):
                raise ToolError("INVALID_ARGUMENTS: Check required fields, field types, and pagination bounds.") from None
            raise


def create_server(
    *, session_factory: SessionFactory = SessionLocal,
    user_resolver: UserResolver = current_user,
) -> MCPServer:
    server = CountOnMCPServer("CountOn", instructions="Manage structured expectations for the authenticated CountOn user.")
    register_tools(server, session_factory, user_resolver)

    @server.custom_route("/health", methods=["GET"])
    async def health(request):
        return JSONResponse({"status": "ok", "service": "counton-mcp"})

    @server.custom_route("/ready", methods=["GET"])
    async def ready(request):
        def check():
            try:
                with session_factory() as db:
                    return database_ready(db)
            except Exception:
                return False
        if not await run_in_threadpool(check):
            return JSONResponse({"status": "not_ready", "service": "counton-mcp"}, status_code=503)
        return JSONResponse({"status": "ready", "service": "counton-mcp"})

    return server


def create_app(server=None, *, settings=None):
    settings = settings or get_settings()
    if settings.environment == "production" and not settings.mcp_public_url:
        raise ValueError("MCP_PUBLIC_URL is required to start production MCP")
    server = server or create_server()
    security = None
    if settings.mcp_public_url or settings.mcp_allowed_origins:
        hosts = ([urlsplit(settings.mcp_public_url).netloc] if settings.mcp_public_url
                 else ["127.0.0.1:*", "localhost:*", "[::1]:*"])
        security = TransportSecuritySettings(allowed_hosts=hosts,
            allowed_origins=settings.mcp_allowed_origins)
    app = server.streamable_http_app(stateless_http=True, json_response=True,
        transport_security=security)
    app.debug = False
    sdk_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        configure_logging()
        async with sdk_lifespan(app):
            yield

    app.router.lifespan_context = lifespan
    app.add_middleware(BearerAuthMiddleware)
    if settings.mcp_allowed_origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.mcp_allowed_origins,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["Authorization", "Content-Type", "Last-Event-ID", "Mcp-Method",
                "Mcp-Name", "Mcp-Protocol-Version", "Mcp-Session-Id"],
            expose_headers=["X-Request-ID", "Mcp-Session-Id"])
    app.add_middleware(RequestContextMiddleware)
    return app


mcp = create_server()
app = create_app(mcp)
