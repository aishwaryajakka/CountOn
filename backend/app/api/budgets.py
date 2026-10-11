"""Bound HTTP bodies before parsing, including chunked messages; no payload logs."""

import asyncio

from app.api.errors import error_response
from app.core.rate_limit import MemoryRateLimiter


class RequestBudgetMiddleware:
    def __init__(self, app, settings, *, mcp=False):
        self.app, self.settings, self.mcp = app, settings, mcp
        self.limiter = MemoryRateLimiter(settings)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] == "OPTIONS":
            return await self.app(scope, receive, send)
        if self.mcp and scope["path"].rstrip("/") != "/mcp":
            return await self.app(scope, receive, send)
        headers = scope.get("headers", [])

        async def reject(status, code):
            response = error_response(status, code, "Request rejected")
            await response(scope, receive, send)

        if sum(k.lower() == b"authorization" for k, _ in headers) > 1:
            return await reject(400, "INVALID_AUTHORIZATION")
        sizes = [v for k, v in headers if k.lower() == b"content-length"]
        if len(sizes) > 1 or (
            sizes
            and (
                not sizes[0].isdigit()
                or len(sizes[0]) > 10
                or int(sizes[0]) > self.settings.max_request_bytes
            )
        ):
            return await reject(413, "REQUEST_TOO_LARGE")
        if self.mcp and self.settings.rate_limit_enabled:
            peer = (scope.get("client") or ("unknown", 0))[0]
            wait = self.limiter.check(
                peer, scope["method"] in ("POST", "PUT", "PATCH", "DELETE")
            )
            if wait:
                response = error_response(
                    429,
                    "RATE_LIMITED",
                    "Request rate limit exceeded",
                    {"Retry-After": str(wait)},
                )
                return await response(scope, receive, send)
        if scope["method"] not in ("POST", "PUT", "PATCH", "DELETE"):
            return await self.app(scope, receive, send)
        body = bytearray()
        try:
            async with asyncio.timeout(10):
                while True:
                    message = await receive()
                    if message["type"] == "http.disconnect":
                        return
                    if message["type"] != "http.request":
                        continue
                    body.extend(message.get("body", b""))
                    if len(body) > self.settings.max_request_bytes:
                        return await reject(413, "REQUEST_TOO_LARGE")
                    if not message.get("more_body"):
                        break
        except TimeoutError:
            return await reject(408, "REQUEST_TIMEOUT")
        sent = False

        async def replay():
            nonlocal sent
            if sent:
                return await receive()
            sent = True
            return {"type": "http.request", "body": bytes(body), "more_body": False}

        await self.app(scope, replay, send)
