"""Bounded rules-only normalization cache. Never stores messages, tokens or prompts.

The caller supplies verified owner/connection/generation/scope context. A different
authorization generation, source version, operation or input hash cannot hit a
previous entry. No authorization context means no cache. Cache loss is harmless.
"""

import copy
import hashlib
import json
import threading
import time
from collections import OrderedDict

from app.core.observability import record
from app.integrations.normalization import NORMALIZER_VERSION


class ExtractionCache:
    def __init__(
        self,
        capacity=256,
        ttl_seconds=900,
        clock=time.monotonic,
        timer_factory=threading.Timer,
    ):
        if capacity < 1 or ttl_seconds <= 0:
            raise ValueError("Cache capacity and retention must be positive")
        self.capacity, self.ttl, self.clock = capacity, ttl_seconds, clock
        self._entries = OrderedDict()
        self._lock = threading.Lock()
        self._timer = None
        self._timer_factory = timer_factory

    def _expire_locked(self):
        now = self.clock()
        for key, entry in list(self._entries.items()):
            if now - entry[0] >= self.ttl:
                del self._entries[key]

    def _schedule_locked(self):
        if self._entries and self._timer is None:
            delay = max(
                0.001,
                min(entry[0] for entry in self._entries.values())
                + self.ttl
                - self.clock(),
            )
            self._timer = self._timer_factory(delay, self._expire)
            self._timer.daemon = True
            self._timer.start()

    def _expire(self):
        with self._lock:
            self._timer = None
            self._expire_locked()
            self._schedule_locked()

    def close(self):
        with self._lock:
            self._entries.clear()
            if self._timer:
                self._timer.cancel()
                self._timer = None

    def extract(
        self,
        scope,
        external_id,
        operation,
        payload,
        normalize,
        *,
        extractor_version=NORMALIZER_VERSION,
    ):
        if not scope:
            return normalize(payload)
        raw = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        if len(raw) > 262144:
            return normalize(payload)
        key = hashlib.sha256(
            json.dumps(
                [list(scope), external_id, operation, extractor_version]
            ).encode()
            + raw
        ).hexdigest()
        with self._lock:
            self._expire_locked()
            entry = self._entries.get(key)
            if entry and self.clock() - entry[0] < self.ttl:
                self._entries.move_to_end(key)
                record("evidence_extraction_cache", "hit")
                return copy.deepcopy(entry[1])
            if entry:
                del self._entries[key]
        # No model/network work under the cache lock or a critical DB transaction.
        facts = normalize(payload)
        with self._lock:
            self._entries[key] = (self.clock(), copy.deepcopy(facts))
            self._entries.move_to_end(key)
            while len(self._entries) > self.capacity:
                self._entries.popitem(last=False)
            self._schedule_locked()
        record("evidence_extraction_cache", "miss")
        return facts


cache = ExtractionCache()
