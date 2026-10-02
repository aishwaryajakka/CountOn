"""Reusable synchronous client; retry GET/HEAD only, never auth/validation errors."""
import time
import httpx
from app.core.config import get_settings


class ExternalHTTPClient:
    def __init__(self, settings=None, transport=None, sleep=time.sleep):
        self.settings = settings or get_settings()
        self.sleep = sleep
        self.client = httpx.Client(transport=transport, follow_redirects=False,
            timeout=httpx.Timeout(connect=self.settings.http_connect_timeout,
                read=self.settings.http_read_timeout, write=self.settings.http_read_timeout,
                pool=self.settings.http_connect_timeout))

    def request(self, method: str, url: str, **kwargs) -> httpx.Response:
        safe = method.upper() in ('GET', 'HEAD')
        for attempt in range(self.settings.http_max_retries + 1):
            try:
                response = self.client.request(method, url, **kwargs)
            except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout):
                if not safe or attempt == self.settings.http_max_retries:
                    raise
            else:
                if not safe or response.status_code not in (502, 503, 504) or attempt == self.settings.http_max_retries:
                    return response
                response.close()
            self.sleep(self.settings.http_backoff_seconds * (2 ** attempt))
        raise RuntimeError('Retry loop exhausted')

    def close(self):
        self.client.close()

    def __enter__(self): return self
    def __exit__(self, *args): self.close()
