

"""OAuth endpoints for Google Calendar integration."""

import hmac
import logging
from datetime import datetime, timedelta, timezone
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

    build_gmail_authorization_url,

    exchange_gmail_authorization_code,

)

from app.services.google_oauth_state import (

    consume_oauth_state,

    create_oauth_state,

)

from app.services.oauth_credential_service import save_credentials
from app.services.microsoft_oauth_service import (
    build_authorization_url as build_microsoft_authorization_url,
    exchange_authorization_code as exchange_microsoft_authorization_code,
    fetch_user_profile as fetch_microsoft_user_profile,
)
logger = logging.getLogger(__name__)

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

GMAIL_STATE_COOKIE = "counton_google_gmail_oauth_state"

def _gmail_callback_path() -> str:

    """Return the configured Gmail OAuth callback path."""

    redirect_uri = get_settings().google_gmail_redirect_uri

    return urlparse(redirect_uri or "/").path or "/"

def _clear_gmail_state_cookie(response: Response) -> None:

    """Remove the Gmail OAuth state cookie."""

    response.delete_cookie(

        key=GMAIL_STATE_COOKIE,

        path=_gmail_callback_path(),

        httponly=True,

        secure=True,

        samesite="lax",

    )


@router.get(
    "/google/gmail/start",
    response_model=AuthorizationURLResponse,
)
def google_gmail_oauth_start(
    current_user: CurrentUser,
    response: Response,
    db: Session = Depends(get_db),
) -> AuthorizationURLResponse:
    """Start the read-only Gmail OAuth flow."""
    settings = get_settings()

    if not settings.google_gmail_redirect_uri:
        raise HTTPException(
            status_code=503,
            detail="Gmail OAuth redirect URI is not configured.",
        )

    try:
        state = create_oauth_state(
            db,
            current_user.id,
            provider="google_gmail",
        )
        authorization_url = build_gmail_authorization_url(state)
    except GoogleOAuthError:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Gmail OAuth configuration is incomplete.",
        ) from None
    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not start Gmail OAuth.",
        ) from None

    response.set_cookie(
        key=GMAIL_STATE_COOKIE,
        value=state,
        max_age=STATE_MAX_AGE,
        httponly=True,
        secure=True,
        samesite="lax",
        path=_gmail_callback_path(),
    )

    return AuthorizationURLResponse(
        authorization_url=authorization_url,
    )

@router.get("/google/gmail/callback")

def google_gmail_oauth_callback(

    request: Request,

    db: Session = Depends(get_db),

):

    """Validate Gmail OAuth and store encrypted credentials."""

    state = request.query_params.get("state", "")

    code = request.query_params.get("code", "")

    provider_error = request.query_params.get("error")

    cookie_state = request.cookies.get(GMAIL_STATE_COOKIE)

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

        _clear_gmail_state_cookie(response)

        return response

    try:

        user_id = consume_oauth_state(

            db,

            state,

            provider="google_gmail",

        )

    except Exception:

        db.rollback()

        response = Response(

            content='{"detail":"Could not validate OAuth state."}',

            status_code=500,

            media_type="application/json",

        )

        _clear_gmail_state_cookie(response)

        return response

    if user_id is None:

        response = Response(

            content=(

                '{"detail":"OAuth state is invalid, expired, or already used."}'

            ),

            status_code=400,

            media_type="application/json",

        )

        _clear_gmail_state_cookie(response)

        return response

    if provider_error or not code:

        response = Response(

            content='{"detail":"Gmail authorization was not completed."}',

            status_code=400,

            media_type="application/json",

        )

        _clear_gmail_state_cookie(response)

        return response

    try:

        tokens = exchange_gmail_authorization_code(code)

        scopes = tokens.get("scope", "")

        if not isinstance(scopes, str):

            raise GoogleOAuthError("Invalid Gmail OAuth scopes.")

        granted_scopes = set(scopes.split())

        required_scope = (

            "https://www.googleapis.com/auth/gmail.readonly"

        )

        if required_scope not in granted_scopes:

            raise GoogleOAuthError(

                "Google Gmail read-only permission was not granted."

            )

        identity = fetch_google_userinfo(tokens["access_token"])

        if (

            not isinstance(identity, dict)

            or not isinstance(identity.get("sub"), str)

            or not identity["sub"].strip()

            or not isinstance(identity.get("email"), str)

            or not identity["email"].strip()

        ):

            raise GoogleOAuthError(

                "Google returned an invalid account identity."

            )

        connection = db.scalar(

            select(IntegrationConnection).where(

                IntegrationConnection.user_id == user_id,

                IntegrationConnection.provider == "google",

                IntegrationConnection.connection_type == "email",

                IntegrationConnection.external_account_id == identity["sub"],

            )

        )

        if connection is None:

            connection = IntegrationConnection(

                user_id=user_id,

                provider="google",

                connection_type="email",

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

            content='{"detail":"Could not complete Gmail connection."}',

            status_code=502,

            media_type="application/json",

        )

        _clear_gmail_state_cookie(response)

        return response

    response = Response(

        content='{"message":"Gmail connected successfully."}',

        media_type="application/json",

    )

    _clear_gmail_state_cookie(response)

    return response

# Microsoft Outlook and Calendar OAuth

def _microsoft_callback_path(connection_type: str) -> str:
    settings = get_settings()
    redirect_uri = (
        settings.microsoft_outlook_redirect_uri
        if connection_type == "email"
        else settings.microsoft_calendar_redirect_uri
    )
    if not redirect_uri:
        raise HTTPException(
            status_code=503,
            detail="Microsoft OAuth redirect URI is not configured.",
        )
    return urlparse(redirect_uri).path


def _clear_microsoft_state_cookie(
    response: Response,
    connection_type: str,
) -> None:
    response.delete_cookie(
        key=(
            "counton_microsoft_outlook_state"
            if connection_type == "email"
            else "counton_microsoft_calendar_state"
        ),
        path=_microsoft_callback_path(connection_type),
        httponly=True,
        secure=False,  # localhost development
        samesite="lax",
    )


def _microsoft_redirect_uri(connection_type: str) -> str:
    settings = get_settings()
    logger.info(
    "Microsoft redirect URI check: type=%s, outlook_set=%s, calendar_set=%s",
    connection_type,
    bool(settings.microsoft_outlook_redirect_uri),
    bool(settings.microsoft_calendar_redirect_uri),
    )
    redirect_uri = (
        settings.microsoft_outlook_redirect_uri
        if connection_type == "email"
        else settings.microsoft_calendar_redirect_uri
    )
    if not redirect_uri:
        raise HTTPException(
            status_code=503,
            detail="Microsoft OAuth redirect URI is not configured.",
        )
    return redirect_uri


@router.get("/microsoft/outlook/start")
def microsoft_outlook_oauth_start(
    response: Response,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    from app.services.google_oauth_state import create_oauth_state

    state = create_oauth_state(
        db, user.id, provider="microsoft_outlook"
    )
    try:
        authorization_url = build_microsoft_authorization_url(
            state=state,
            redirect_uri=_microsoft_redirect_uri("email"),
            connection_type="email",
        )
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Microsoft Outlook OAuth is not configured correctly.",
        ) from exc

    response = Response(
        content=f'{{"authorization_url":"{authorization_url}"}}',
        media_type="application/json",
    )
    response.set_cookie(
        key="counton_microsoft_outlook_state",
        value=state,
        max_age=600,
        httponly=True,
        secure=False,
        samesite="lax",
        path=_microsoft_callback_path("email"),
    )
    return response


@router.get("/microsoft/calendar/start")
def microsoft_calendar_oauth_start(
    response: Response,
    user: CurrentUser,
    db: Session = Depends(get_db),
):
    from app.services.google_oauth_state import create_oauth_state

    try:
        logger.info("Microsoft Calendar OAuth: creating state")
        state = create_oauth_state(
            db, user.id, provider="microsoft_calendar"
        )

        logger.info("Microsoft Calendar OAuth: building authorization URL")
        authorization_url = build_microsoft_authorization_url(
            state=state,
            redirect_uri=_microsoft_redirect_uri("calendar"),
            connection_type="calendar",
        )

        logger.info("Microsoft Calendar OAuth: authorization URL built")
    except HTTPException as exc:
        logger.error(
            "Microsoft Calendar OAuth HTTP error: status=%s, detail=%s",
            exc.status_code,
            exc.detail,
        )
        db.rollback()
        raise
    except Exception as exc:
        logger.exception(
            "Microsoft Calendar OAuth start failed at setup: %s",
            type(exc).__name__,
        )
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Microsoft Calendar OAuth setup failed. Check server logs.",
        ) from exc

    response = Response(
        content=f'{{"authorization_url":"{authorization_url}"}}',
        media_type="application/json",
    )
    response.set_cookie(
        key="counton_microsoft_calendar_state",
        value=state,
        max_age=600,
        httponly=True,
        secure=False,
        samesite="lax",
        path=_microsoft_callback_path("calendar"),
    )
    return response


async def _complete_microsoft_oauth(
    *,
    connection_type: str,
    code: str | None,
    state: str | None,
    cookie_state: str | None,
    error: str | None,
    db: Session,
) -> Response:
    from app.services.google_oauth_state import consume_oauth_state

    cookie_name = (
        "counton_microsoft_outlook_state"
        if connection_type == "email"
        else "counton_microsoft_calendar_state"
    )
    provider_state = (
        "microsoft_outlook"
        if connection_type == "email"
        else "microsoft_calendar"
    )

    def failure(status_code: int, message: str) -> Response:
        response = Response(
            content=f'{{"detail":"{message}"}}',
            status_code=status_code,
            media_type="application/json",
        )
        _clear_microsoft_state_cookie(response, connection_type)
        return response

    if error:
        return failure(400, "Microsoft authorization was not completed.")
    if not code or not state or not cookie_state:
        return failure(400, "Missing Microsoft OAuth callback parameters.")
    if not hmac.compare_digest(state, cookie_state):
        return failure(400, "Invalid Microsoft OAuth state.")

    try:
        user_id = consume_oauth_state(
            db, state, provider=provider_state
        )
        if user_id is None:
            return failure(400, "Expired or already-used Microsoft OAuth state.")

        tokens = await exchange_microsoft_authorization_code(
            code=code,
            redirect_uri=_microsoft_redirect_uri(connection_type),
            connection_type=connection_type,
        )
        profile = await fetch_microsoft_user_profile(
            tokens["access_token"]
        )

        account_id = profile.get("id")
        if not account_id:
            raise RuntimeError("Microsoft profile did not include an account ID")

        account_email = (
            profile.get("mail")
            or profile.get("userPrincipalName")
            or profile.get("displayName")
        )
        scopes = tokens.get("scope", "")
        required_scope = (
            "Mail.Read" if connection_type == "email"
            else "Calendars.Read"
        )
        if scopes and required_scope.lower() not in {
            scope.lower() for scope in scopes.split()
        }:
            raise RuntimeError("Required Microsoft permission was not granted")

        connection = db.scalar(
            select(IntegrationConnection).where(
                IntegrationConnection.user_id == user_id,
                IntegrationConnection.provider == "microsoft",
                IntegrationConnection.connection_type == connection_type,
                IntegrationConnection.external_account_id == account_id,
            )
        )

        if connection is None:
            connection = IntegrationConnection(
                user_id=user_id,
                provider="microsoft",
                connection_type=connection_type,
                external_account_id=account_id,
            )
            db.add(connection)

        connection.display_name = account_email
        connection.status = "connected"
        connection.scopes = scopes.split()
        connection.connection_metadata = {
            "email": profile.get("mail"),
            "display_name": profile.get("displayName"),
            "user_principal_name": profile.get("userPrincipalName"),
        }
        db.flush()

        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=int(tokens.get("expires_in", 3600))
        )
        save_credentials(
            db,
            connection_id=connection.id,
            user_id=user_id,
            provider="microsoft",
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token"),
            expires_at=expires_at,
            token_type=tokens.get("token_type") or "Bearer",
            scopes=scopes,
        )
        db.commit()

        response = Response(
            content=(
                '{"message":"Microsoft Outlook connected successfully."}'
                if connection_type == "email"
                else '{"message":"Microsoft Calendar connected successfully."}'
            ),
            media_type="application/json",
        )
        _clear_microsoft_state_cookie(response, connection_type)
        return response

    except Exception:
        db.rollback()
        return failure(502, "Could not complete Microsoft OAuth connection.")


@router.get("/microsoft/outlook/callback")
async def microsoft_outlook_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    return await _complete_microsoft_oauth(
        connection_type="email",
        code=code,
        state=state,
        cookie_state=request.cookies.get("counton_microsoft_outlook_state"),
        error=error,
        db=db,
    )


@router.get("/microsoft/calendar/callback")
async def microsoft_calendar_oauth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    return await _complete_microsoft_oauth(
        connection_type="calendar",
        code=code,
        state=state,
        cookie_state=request.cookies.get("counton_microsoft_calendar_state"),
        error=error,
        db=db,
    )
