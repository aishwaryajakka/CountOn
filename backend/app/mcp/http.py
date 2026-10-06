"""Small ASGI request context wrapper; never records headers or bodies."""
from uuid import uuid4

from app.core.observability import request_id


class RequestContextMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        identity = str(uuid4())
        reset = request_id.set(identity)

        async def send_with_id(message):
            if message['type'] == 'http.response.start':
                message = dict(message, headers=[*message.get('headers', []),
                    (b'x-request-id', identity.encode('ascii'))])
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            request_id.reset(reset)


class BearerAuthMiddleware:
    """Protect every MCP HTTP request; health/readiness remain public.

    Alexa's current MCP flow expects 401 without WWW-Authenticate. This is
    only the bearer boundary, not OAuth discovery or an account-linking server.
    """
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['path'].rstrip('/') != '/mcp':
            return await self.app(scope, receive, send)
        import logging
        from time import perf_counter
        from starlette.requests import Request
        from starlette.responses import JSONResponse
        from starlette.concurrency import run_in_threadpool
        from app.core.exceptions import AuthenticationError
        from app.mcp import auth
        started = perf_counter()
        outcome = 'unauthorized'
        user = None
        try:
            user = await run_in_threadpool(auth.authenticated_user_from_header,
                Request(scope).headers.get('authorization'))
            scope.setdefault('state', {})['counton_user'] = user
            outcome = 'authenticated'
        except AuthenticationError:
            response = JSONResponse({'error': {'code': 'UNAUTHORIZED',
                'message': 'Authentication required or token invalid'}}, status_code=401)
            return await response(scope, receive, send)
        except Exception:
            outcome = 'unavailable'
            response = JSONResponse({'error': {'code': 'AUTH_UNAVAILABLE',
                'message': 'Authentication is unavailable'}}, status_code=503)
            return await response(scope, receive, send)
        finally:
            logging.getLogger(__name__).info('MCP authentication', extra={
                'user_id': str(user.id) if user else None, 'result_status': outcome,
                'duration_ms': round((perf_counter() - started) * 1000, 2)})
        await self.app(scope, receive, send)
