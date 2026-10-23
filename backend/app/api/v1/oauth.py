

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
