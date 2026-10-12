"""Provider contract for bounded, permission-scoped normalization; no provider AI."""

from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from app.db.models import Expectation, MonitoringJob
from app.schemas.evidence import EvidenceCreate


class ProviderError(Exception):
    def __init__(self, code: str, *, retryable: bool = True, retry_after: int = 0):
        allowed = {
            "PROVIDER_DISABLED",
            "CREDENTIAL_UNAVAILABLE",
            "PROVIDER_THROTTLED",
            "AUTH_REQUIRED",
            "PERMISSION_DENIED",
            "PROVIDER_UNAVAILABLE",
            "OAUTH_REJECTED",
            "PROVIDER_REJECTED",
            "PROVIDER_RESPONSE_INVALID",
            "OAUTH_STATE_INVALID",
            "INCOMPLETE_SYNC",
            "WORKER_ERROR",
            "SYNC_CURSOR_EXPIRED",
            "SOURCE_NOT_FOUND",
        }
        self.code = code if code in allowed else "PROVIDER_UNAVAILABLE"
        self.retryable = retryable
        self.retry_after = min(max(retry_after, 0), 86400)
        super().__init__(self.code)


class EvidenceProvider(Protocol):
    def fetch(
        self, db: Session, job: MonitoringJob, expectation: Expectation, now: datetime
    ) -> list[EvidenceCreate]: ...
