"""Shared sessions and authenticated identities for protected routes."""

from typing import Annotated

from fastapi import Depends, Request
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
    request.state.user_id=str(user.id)
    ensure_profile(db, user.id)
    return user


CurrentUser = Annotated[AuthenticatedUser, Depends(get_current_user)]

__all__ = ["get_db", "get_current_user", "CurrentUser"]
