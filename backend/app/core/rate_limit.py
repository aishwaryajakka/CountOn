"""Atomic in-process fixed-window limiter; bounded, fail-closed at capacity.

A shared implementation must atomically check both budgets across replicas.
Proxy headers are intentionally not trusted for determining the caller.
"""
from math import ceil
from threading import Lock
from time import monotonic
from typing import Protocol


class RateLimiter(Protocol):
    def check(self, key: str, write: bool) -> int: ...  # zero allowed; otherwise Retry-After


class MemoryRateLimiter:
    def __init__(self, settings, clock=monotonic):
        self.settings, self.clock = settings, clock
        self.buckets = {}
        self.lock = Lock()

    def check(self, key, write):
        now = self.clock()
        window = self.settings.rate_limit_window_seconds
        with self.lock:
            # Bound memory under random-IP traffic; never evict live budgets.
            self.buckets = {k:v for k,v in self.buckets.items() if now-v[0] < window}
            if key not in self.buckets:
                if len(self.buckets) >= self.settings.rate_limit_max_keys:
                    return window
                self.buckets[key] = [now, 0, 0]
            bucket = self.buckets[key]
            if bucket[1] >= self.settings.rate_limit_requests or (write and bucket[2] >= self.settings.rate_limit_writes):
                return max(1, ceil(window-(now-bucket[0])))
            bucket[1] += 1
            bucket[2] += int(write)
            return 0
