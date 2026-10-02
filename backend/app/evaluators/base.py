"""Framework-independent deterministic evaluator output and shared enum."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.db.models.evidence import Evidence


class EvaluationResult(StrEnum):
    MATCH = "MATCH"
    UNKNOWN = "UNKNOWN"
    MISMATCH = "MISMATCH"


@dataclass(frozen=True)
class EvaluationOutput:
    result: EvaluationResult
    expected: dict[str, Any] = field(default_factory=dict)
    observed: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    reasoning: dict[str, Any] = field(default_factory=dict)


def latest_evidence(evidence: list["Evidence"], metric: str | None) -> "Evidence | None":
    """Latest observation wins; creation time and UUID break equal-time ties.

    For boolean expectations without a metric, consider all evidence.
    """
    relevant = [item for item in evidence if metric is None or item.metric == metric]
    if not relevant:
        return None
    minimum = datetime.min.replace(tzinfo=timezone.utc)
    return max(relevant, key=lambda item: (
        item.observed_at, item.created_at or minimum, str(item.id or "")
    ))
