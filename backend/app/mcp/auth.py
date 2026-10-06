"""Resolve MCP request identity with the existing Supabase verifier."""

from mcp.server.mcpserver import Context

from app.core.auth import AuthenticatedUser, get_token_verifier
from app.core.exceptions import AuthenticationError


def authenticated_user_from_header(authorization: str | None) -> AuthenticatedUser:
    """Derive identity using the same Supabase token verifier as the REST API."""
    if not authorization:
        raise AuthenticationError()
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthenticationError()
    return get_token_verifier().verify(parts[1])


def current_user(context: Context) -> AuthenticatedUser:
    """Verify transport credentials for every call; no identity from arguments."""
    headers = context.headers
    return authenticated_user_from_header(headers.get("authorization") if headers else None)
