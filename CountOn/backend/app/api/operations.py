"""Request correlation, safe access logs, metrics and rate limiting."""
import logging
from time import perf_counter
from uuid import UUID, uuid4
from app.core import observability
from app.core.rate_limit import MemoryRateLimiter
from app.api.errors import error_response
from starlette.middleware.cors import CORSMiddleware

logger = logging.getLogger('counton.requests')


class ExplicitCORSMiddleware(CORSMiddleware):
    def preflight_response(self, request_headers):
        response = super().preflight_response(request_headers)
        if response.status_code == 400:
            return error_response(400,'CORS_REJECTED','Origin, method or headers not allowed',{k:v for k,v in response.headers.items() if k.lower() not in ('content-type','content-length')})
        return response


class OperationalMiddleware:
    def __init__(self, app, settings, limiter=None):
        self.app, self.settings = app, settings
        self.limiter = limiter or MemoryRateLimiter(settings)

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope,receive,send)
        supplied=dict(scope.get('headers',[])).get(b'x-request-id',b'').decode('ascii',errors='ignore')
        try: rid=str(UUID(supplied))
        except ValueError: rid=str(uuid4())
        token=observability.request_id.set(rid)
        started=perf_counter()
        status=500
        response_started=False
        async def correlated(message):
            nonlocal status,response_started
            if message['type']=='http.response.start':
                response_started=True
                status=message['status']
                message['headers']=[(k,v) for k,v in message.get('headers',[]) if k.lower()!=b'x-request-id']+[(b'x-request-id',rid.encode())]
            await send(message)
        try:
            wait=0
            if self.settings.rate_limit_enabled and scope['path'].startswith('/api/') and scope['method']!='OPTIONS':
                key=(scope.get('client') or ('unknown',0))[0]
                limiter=getattr(getattr(scope.get('app'),'state',None),'rate_limiter',self.limiter)
                wait=limiter.check(key,scope['method'] not in ('GET','HEAD'))
            if wait:
                response=error_response(429,'RATE_LIMITED','Request rate limit exceeded',{'Retry-After':str(wait)})
                self.add_cors(response,scope)
                await response(scope,receive,correlated)
            else:
                try:
                    await self.app(scope,receive,correlated)
                except Exception as error:
                    logger.error('Request failed request_id=%s error_type=%s',rid,type(error).__name__)
                    if response_started:
                        raise RuntimeError('Response failed after headers') from None
                    response=error_response(500,'INTERNAL_ERROR','Internal server error')
                    self.add_cors(response,scope)
                    await response(scope,receive,correlated)
        finally:
            route=scope.get('route')
            label=getattr(route,'path','unmatched')
            elapsed=perf_counter()-started
            observability.record('requests',label)
            observability.record('request_latency_seconds',label,elapsed)
            if status>=500: observability.record('server_errors',label)
            logger.info('HTTP request',extra={'method':scope['method'],'route':label,'status_code':status,'duration_ms':round(elapsed*1000,1),'user_id':scope.get('state',{}).get('user_id')})
            observability.request_id.reset(token)

    def add_cors(self,response,scope):
        origin=dict(scope.get('headers',[])).get(b'origin',b'').decode('latin1')
        if origin in self.settings.allowed_origins:
            response.headers['Access-Control-Allow-Origin']=origin
            response.headers['Access-Control-Allow-Credentials']='true'
            response.headers['Access-Control-Expose-Headers']='X-Request-ID, Retry-After'
            response.headers['Vary']='Origin'
