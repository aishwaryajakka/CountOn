"""Alexa HTTPS fulfillment: signed ASK body -> existing auth -> same orchestrator."""

import asyncio

import anyio
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import SecretStr

from app.agent.adapters import StreamableMcpAdapter
from app.agent.orchestrator import AgentOrchestrator
from app.alexa.adapter import (
    HELP,
    UNCERTAIN,
    AlexaAdapter,
    AlexaConversationStore,
    AlexaEvent,
    AlexaSessionUnavailable,
    envelope,
    link_account,
)
from app.alexa.verification import InvalidAlexaRequest, get_alexa_verifier
from app.core.auth import AuthenticatedUser, get_token_verifier
from app.core.config import get_settings
from app.core.exceptions import AuthenticationError
from app.db.session import SessionLocal
from app.schemas.compiler import CompileContext
from app.services.agent_audit import persist_run
from app.services.profile_service import ensure_profile

router = APIRouter(prefix="/alexa", tags=["alexa"])


def authenticated_context(token: str) -> tuple[AuthenticatedUser, str]:
    # Identical JWT verifier/profile semantics to the normal protected API.
    user = get_token_verifier().verify(token)
    configured_client = get_settings().alexa_oauth_client_id
    if configured_client and user.oauth_client_id != configured_client:
        raise AuthenticationError()  # type: ignore[no-untyped-call]
    with SessionLocal() as db:
        profile = ensure_profile(db, user.id)
        timezone = profile.timezone or "UTC"
    try:
        CompileContext.valid_timezone(timezone)
    except ValueError:
        timezone = "UTC"
    return user, timezone


@router.post("")
async def fulfillment(request: Request) -> JSONResponse:
    settings = get_settings()
    headers = {"Cache-Control": "no-store"}
    if not settings.alexa_skill_id:
        return JSONResponse(
            {"error": "Alexa endpoint is not configured"},
            status_code=503,
            headers=headers,
        )
    deadline = asyncio.get_running_loop().time() + 7
    authenticated = False
    try:
        async with asyncio.timeout_at(deadline):
            raw = bytearray()
            async for chunk in request.stream():
                raw.extend(chunk)
                if len(raw) > 32768:
                    raise InvalidAlexaRequest()
            verifier = get_alexa_verifier()
            data = await anyio.to_thread.run_sync(
                verifier.verify,
                dict(request.headers),
                bytes(raw),
                settings.alexa_skill_id,
                abandon_on_cancel=True,
            )
            event = AlexaEvent.parse(data, bytes(raw))
            token = data["context"]["System"]["user"].get("accessToken")
            if not isinstance(token, str) or not 1 <= len(token) <= 16000:
                if event.kind == "SessionEndedRequest":
                    reply = envelope(None, end=True)
                elif event.intent in ("AMAZON.CancelIntent", "AMAZON.StopIntent"):
                    reply = envelope("Okay. Goodbye.", end=True)
                elif event.intent == "AMAZON.HelpIntent":
                    reply = envelope(HELP, end=True)
                else:
                    reply = link_account()
                return JSONResponse(reply, headers=headers)
            try:
                user, timezone = await anyio.to_thread.run_sync(
                    authenticated_context,
                    token,
                    abandon_on_cancel=True,
                )
            except AuthenticationError:
                return JSONResponse(
                    envelope(None, end=True)
                    if event.kind == "SessionEndedRequest"
                    else link_account(),
                    headers=headers,
                )
            authenticated = True
            request.state.user_id = str(user.id)
            agent = AgentOrchestrator(
                StreamableMcpAdapter(settings, SecretStr(token)),
                settings=settings,
                session_store=request.app.state.agent_sessions,
                audit_sink=persist_run,
                require_capture_confirmation=settings.alexa_require_confirmation,
            )
            store: AlexaConversationStore = request.app.state.alexa_sessions
            reply = await AlexaAdapter(store, agent).handle(
                event,
                user,
                timezone=timezone,
                deadline=deadline,
            )
            return JSONResponse(reply, headers=headers)
    except InvalidAlexaRequest:
        return JSONResponse(
            {"error": "Invalid Alexa request"}, status_code=400, headers=headers
        )
    except AlexaSessionUnavailable:
        return JSONResponse(
            envelope(
                "That conversation is no longer available. Please start a new session and restate your request.",
                end=True,
            ),
            headers=headers,
        )
    except TimeoutError:
        # No retry. A write may already be in progress; the transport replay cache
        # and existing durable compilation ledger guard requests that reached it.
        return JSONResponse(
            envelope(
                UNCERTAIN
                if authenticated
                else "CountOn is taking too long to verify this request. Please try again later.",
                end=True,
            ),
            headers=headers,
        )
    except Exception:  # noqa: BLE001 - Transport boundary must mask credentials and SDK errors
        # Never expose/log the original ASK payload, slots, JWT or SDK exception.
        return JSONResponse(
            envelope(
                "CountOn is temporarily unavailable. Check your records before retrying a save.",
                end=True,
            ),
            headers=headers,
        )
