"""Shared sessions and authenticated identities for protected routes."""

import re
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser, get_token_verifier
from app.core.exceptions import AuthenticationError
from app.db.session import get_db
from app.services.profile_service import ensure_profile

bearer = HTTPBearer(auto_error=False, scheme_name="SupabaseAccessToken")


def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    db: Annotated[Session, Depends(get_db)],
) -> AuthenticatedUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError()
    user = get_token_verifier().verify(credentials.credentials)
    if user.oauth_client_id is not None and not (
        request.method == "GET"
        and (
            request.url.path == "/api/v1/expectations"
            or re.fullmatch(r"/api/v1/expectations/[0-9a-fA-F-]{36}", request.url.path)
            is not None
        )
        or request.method == "POST"
        and request.url.path in ("/api/v1/agent/converse", "/api/v1/agent/reset")
    ):
        raise HTTPException(
            status_code=403, detail="OAuth client operation is not permitted"
        )
    request.state.user_id = str(user.id)
    profile = ensure_profile(db, user.id)
    request.state.profile_timezone = profile.timezone
    return user


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]

__all__ = ["CurrentUser", "get_current_user", "get_db"]
