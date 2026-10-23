

"""OAuth endpoints for Google Calendar integration."""

import hmac
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser
from app.core.config import get_settings
from app.db.models.integration import IntegrationConnection
from app.db.session import get_db
from app.services.google_oauth_service import (
    GoogleOAuthError,
    build_authorization_url,
    exchange_authorization_code,
    fetch_google_userinfo,
)
from app.services.google_oauth_state import (
    consume_oauth_state,
    create_oauth_state,
)
from app.services.oauth_credential_service import save_credentials


router = APIRouter(prefix="/oauth", tags=["OAuth"])

STATE_COOKIE = "counton_google_oauth_state"
STATE_MAX_AGE = 600


class AuthorizationURLResponse(BaseModel):
    authorization_url: str


def _callback_path() -> str:
    """Return the configured OAuth callback path."""
    redirect_uri = get_settings().google_redirect_uri
    return urlparse(redirect_uri or "/").path or "/"


def _clear_state_cookie(response: Response) -> None:
    """Remove the OAuth state cookie."""
    response.delete_cookie(
        key=STATE_COOKIE,
        path=_callback_path(),
        httponly=True,
        secure=True,
        samesite="lax",
    )


@router.get(
    "/google/start",
    response_model=AuthorizationURLResponse,
)
def google_oauth_start(
    current_user: CurrentUser,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthorizationURLResponse:
    """Start the Google Calendar OAuth flow."""
    settings = get_settings()

    if not settings.google_redirect_uri:
        raise HTTPException(
            status_code=503,
            detail="Google OAuth redirect URI is not configured.",
        )

    try:
        state = create_oauth_state(db, current_user.id)
        authorization_url = build_authorization_url(state)
    except GoogleOAuthError:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Google OAuth configuration is incomplete.",
        ) from None
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not start Google OAuth.",
        ) from None

    response.set_cookie(
        key=STATE_COOKIE,
        value=state,
        max_age=STATE_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
        path=_callback_path(),
    )

    return AuthorizationURLResponse(
        authorization_url=authorization_url,
    )


@router.get("/google/callback")
def google_oauth_callback(
    request: Request,
    db: Session = Depends(get_db),
):
    """Validate Google's callback and store encrypted credentials."""
    state = request.query_params.get("state", "")
    code = request.query_params.get("code", "")
    provider_error = request.query_params.get("error")
    cookie_state = request.cookies.get(STATE_COOKIE)

    # Verify browser binding before consuming the one-time state.
    if (
        not state
        or not cookie_state
        or not hmac.compare_digest(state, cookie_state)
    ):
        response = Response(
            content='{"detail":"OAuth state validation failed."}',
            status_code=400,
            media_type="application/json",
        )
        _clear_state_cookie(response)
        return response

    # Consume and commit state before making external network requests.
    try:
        user_id = consume_oauth_state(db, state)
    except Exception:
        db.rollback()
        response = Response(
            content='{"detail":"Could not validate OAuth state."}',
            status_code=500,
            media_type="application/json",
        )
        _clear_state_cookie(response)
        return response

    if user_id is None:
        response = Response(
            content='{"detail":"OAuth state is invalid, expired, or already used."}',
            status_code=400,
            media_type="application/json",
        )
        _clear_state_cookie(response)
        return response

    if provider_error or not code:
        response = Response(
            content='{"detail":"Google authorization was not completed."}',
            status_code=400,
            media_type="application/json",
        )
        _clear_state_cookie(response)
        return response

    try:
        tokens = exchange_authorization_code(code)
        identity = fetch_google_userinfo(tokens["access_token"])

        connection = db.scalar(
            select(IntegrationConnection).where(
                IntegrationConnection.user_id == user_id,
                IntegrationConnection.provider == "google",
                IntegrationConnection.connection_type == "calendar",
                IntegrationConnection.external_account_id == identity["sub"],
            )
        )

        scopes = tokens.get("scope", "")
        if not isinstance(scopes, str):
            scopes = ""

        if connection is None:
            connection = IntegrationConnection(
                user_id=user_id,
                provider="google",
                connection_type="calendar",
                external_account_id=identity["sub"],
            )
            db.add(connection)

        connection.display_name = identity["email"]
        connection.status = "connected"
        connection.scopes = scopes.split()
        connection.connection_metadata = {
            "email": identity["email"],
        }

        db.flush()

        save_credentials(
            db,
            connection_id=connection.id,
            user_id=user_id,
            provider="google",
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token"),
            expires_at=tokens["expires_at"],
            token_type=tokens.get("token_type") or "Bearer",
            scopes=scopes,
        )

        db.commit()

    except Exception:
        db.rollback()
        response = Response(
            content='{"detail":"Could not complete Google Calendar connection."}',
            status_code=502,
            media_type="application/json",
        )
        _clear_state_cookie(response)
        return response

    response = Response(
        content='{"message":"Google Calendar connected successfully."}',
        media_type="application/json",
    )
    _clear_state_cookie(response)
    return response
"""OAuth connection endpoints for external providers."""
from sqlalchemy.orm import Session
from typing import Annotated
from authlib.integrations.starlette_client import OAuth
from fastapi import APIRouter, Depends, HTTPException, Query, Request, logger
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from app.api.dependencies import CurrentUser, get_db
from app.services.oauth_state_service import (
    consume_state,
    create_state,
)
from app.services.oauth_credential_service import save_google_connection
from app.core.config import get_settings

router = APIRouter(prefix="/oauth", tags=["oauth"])

oauth = OAuth()


def get_google_oauth():
    """Return the configured Google OAuth client."""
    settings = get_settings()

    if not all(
        [
            settings.google_client_id,
            settings.google_client_secret,
            settings.google_redirect_uri,
        ]
    ):
        raise HTTPException(
            status_code=503,
            detail="Google OAuth is not configured.",
        )

    oauth.register(
        name="google",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret.get_secret_value(),
        server_metadata_url=(
            "https://accounts.google.com/.well-known/openid-configuration"
        ),
        client_kwargs={
            "scope": "openid email profile https://www.googleapis.com/auth/gmail.readonly",
            "access_type": "offline",
            "prompt": "consent",
        },
    )

    return oauth.create_client("google")





@router.get("/google/login")
async def google_login(
    request: Request,
    user: CurrentUser,
    db: Annotated[Session, Depends(get_db)],
):
    """Start the Google OAuth authorization flow."""
    google = get_google_oauth()
    settings = get_settings()

    state = create_state(
        db=db,
        user_id=user.id,
        provider="google",
    )

    redirect_response = await google.authorize_redirect(
        request,
        settings.google_redirect_uri,
        state=state,
    )

    authorization_url = redirect_response.headers.get("location")
    if not authorization_url:
        raise HTTPException(
            status_code=500,
            detail="Google authorization URL could not be created.",
        )

    response = JSONResponse(
        content={"authorization_url": authorization_url}
    )

    for cookie in redirect_response.headers.getlist("set-cookie"):
        response.headers.append("set-cookie", cookie)

    return response




@router.get("/google/callback")
async def google_callback(
    request: Request,
    code: str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
    db: Annotated[Session, Depends(get_db)] = None,
):
    """Validate Google's response and save the connected account."""
    if error:
        raise HTTPException(
            status_code=400,
            detail="Google authorization was not completed.",
        )

    if not code or not state:
        raise HTTPException(
            status_code=400,
            detail="Missing OAuth callback parameters.",
        )

    user_id = consume_state(
        db=db,
        raw_state=state,
        provider="google",
    )

    if user_id is None:
        raise HTTPException(
            status_code=400,
            detail="Invalid, expired, or already-used OAuth state.",
        )

    google = get_google_oauth()

    try:
        token = await google.authorize_access_token(request)
        user_info = token.get("userinfo")

        if not user_info:
            user_info = await google.userinfo(token=token)

        if not user_info or not user_info.get("sub"):
            raise HTTPException(
                status_code=400,
                detail="Google account identity could not be verified.",
            )

        connection = save_google_connection(
            db=db,
            user_id=user_id,
            user_info=dict(user_info),
            token=dict(token),
        )

    except HTTPException:
        raise
    except Exception as exc:
        print(f"Google OAuth callback failed: {type(exc).__name__}: {exc}", flush=True)
        raise HTTPException(
            status_code=400,
            detail=f"Google connection could not be completed: {type(exc).__name__}",
        ) from exc


    settings = get_settings()

    return RedirectResponse(
        url=f"{settings.frontend_url.rstrip('/')}/integrations?google_connected=true",
        status_code=303,
    )
