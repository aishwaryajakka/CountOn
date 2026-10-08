"""Bounded metric labels and request context; replace the sink for export."""
from collections import Counter
from contextvars import ContextVar
from threading import Lock
from typing import Protocol

request_id: ContextVar[str | None] = ContextVar('counton_request_id', default=None)


class Metrics(Protocol):
    def increment(self, name: str, label: str = '', amount: float = 1) -> None: ...


class MemoryMetrics:
    def __init__(self):
        self._values = Counter()
        self._lock = Lock()

    def increment(self, name: str, label: str = '', amount: float = 1) -> None:
        with self._lock:
            self._values[(name, label)] += amount

    def snapshot(self):
        with self._lock:
            return dict(self._values)


metrics: Metrics = MemoryMetrics()


def record(name: str, label: str = '', amount: float = 1) -> None:
    """Exporter failures must not fail successful requests or committed writes."""
    try:
        metrics.increment(name,label,amount)
    except Exception as error:
        import logging
        logging.getLogger(__name__).warning('Metric sink unavailable error_type=%s',type(error).__name__)
