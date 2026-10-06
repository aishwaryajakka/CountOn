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
