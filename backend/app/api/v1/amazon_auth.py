"""Amazon UserInfo translation for Supabase custom OAuth2; never issues sessions.

Amazon tokens are accepted only here, never as CountOn credentials. The Auth
server owns client-secret exchange, state, PKCE and linking. No database access.
"""

import json
import math
from typing import Annotated, Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, build_opener
from urllib.request import Request as UpstreamRequest

from fastapi import APIRouter, Header, HTTPException, Response

from app.core.config import get_settings

router = APIRouter(prefix="/auth/amazon", tags=["authentication"])


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: UpstreamRequest, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None  # Never forward a credential through a redirect.


def amazon_json(url: str, token: str | None = None) -> dict[str, Any]:
    # urllib does not log request URLs. Amazon introspection requires a query
    # credential; do not use HTTPX's URL-logging request API for that operation.
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        with build_opener(NoRedirect()).open(UpstreamRequest(url, headers=headers), timeout=5) as reply:
            data = reply.read(8193)
            if len(data) > 8192:
                raise ValueError("Oversized provider response")
            value = json.loads(data)
            if not isinstance(value, dict):
                raise TypeError("Invalid provider response")
            return value
    except HTTPError as error:
        status = 401 if error.code in (400, 401, 403) else 503
        raise HTTPException(status, "Amazon identity could not be verified") from None
    except (URLError, TimeoutError, OSError):
        raise HTTPException(503, "Amazon identity is temporarily unavailable") from None
    except (ValueError, TypeError):
        raise HTTPException(401, "Amazon identity could not be verified") from None


@router.get("/userinfo", summary="Translate Amazon profile for Supabase OAuth2")
def userinfo(response: Response, authorization: Annotated[str | None, Header()] = None) -> dict[str, str]:
    settings = get_settings()
    response.headers["Cache-Control"] = "no-store"
    if not settings.amazon_auth_enabled or not settings.amazon_client_id:
        raise HTTPException(503, "Amazon sign-in is not configured")
    parts = authorization.split() if authorization else []
    if len(parts) != 2 or parts[0].lower() != "bearer" or not 1 <= len(parts[1]) <= 8192:
        raise HTTPException(401, "Amazon identity could not be verified")
    token = parts[1]
    if not token.startswith("Atza|"):
        raise HTTPException(401, "Amazon identity could not be verified")
    info = amazon_json("https://api.amazon.com/auth/O2/tokeninfo?" + urlencode({"access_token": token}))
    expiry = info.get("exp")  # Amazon introspection returns remaining lifetime in seconds.
    subject = info.get("user_id")
    if (info.get("aud") != settings.amazon_client_id or info.get("iss") != "https://www.amazon.com"
            or isinstance(expiry, bool) or not isinstance(expiry, (int, float))
            or not math.isfinite(expiry) or expiry <= 0
            or not isinstance(subject, str) or not 1 <= len(subject) <= 255):
        raise HTTPException(401, "Amazon identity could not be verified")
    profile = amazon_json("https://api.amazon.com/user/profile", token)
    if profile.get("user_id") != subject:
        raise HTTPException(401, "Amazon identity could not be verified")
    # Intentionally omit email even if accidentally granted a broader scope.
    # Same-email automatic linking must never connect unrelated CountOn accounts.
    return {"sub": subject}
