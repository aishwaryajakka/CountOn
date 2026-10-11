"""Small source allowlist. Permission is not evidence or provider availability."""

import re
from dataclasses import dataclass

from app.schemas.evidence import EvidenceResponse
from app.schemas.expectation import ExpectationResponse
from app.schemas.trust import EvidenceSource, SourceDecision

ALIASES = {"tariff": "utility_tariff"}
SOURCES = {
    "utility": EvidenceSource.UTILITY,
    "utility_bill": EvidenceSource.UTILITY,
    "utility_usage": EvidenceSource.UTILITY,
    "utility_tariff": EvidenceSource.UTILITY,
    "billing": EvidenceSource.BILLING,
    "grocery_bill": EvidenceSource.BILLING,
    "receipt": EvidenceSource.BILLING,
    "delivery": EvidenceSource.DELIVERY,
    "package_tracking": EvidenceSource.DELIVERY,
    "ring": EvidenceSource.RING,
    "calendar": EvidenceSource.CALENDAR,
    "outlook": EvidenceSource.OUTLOOK,
    "bee": EvidenceSource.BEE,
}


def source_key(value: str) -> str | None:
    # Reject arbitrary provider text; retain custom explicitly declared identifiers.
    return (
        ALIASES.get(value, value)
        if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", value)
        else None
    )


@dataclass(frozen=True)
class ExpectationPrivacyScope:
    expectation_type: str
    allowed_sources: frozenset[str]


class EvidenceAccessPolicy:
    def __init__(self, expectation: ExpectationResponse) -> None:
        allowed = frozenset(
            key
            for value in expectation.evidence_sources
            if (key := source_key(value)) is not None
        )
        # Only an empty declaration can use a conservative domain default. This
        # grants permission to existing rows, never implies an integration exists.
        if not expectation.evidence_sources:
            claim = expectation.claim.lower()
            if expectation.metric == "total_cost" and re.search(
                r"\b(electricity|utility|energy)\b", claim
            ):
                allowed = frozenset({"utility_bill", "utility_usage", "utility_tariff"})
            elif expectation.metric == "total_cost" and re.search(
                r"\b(grocery|groceries)\b", claim
            ):
                allowed = frozenset({"grocery_bill", "receipt"})
            elif expectation.type in ("event", "temporal") and re.search(
                r"\b(package|parcel|delivery)\b", claim
            ):
                allowed = frozenset({"delivery", "package_tracking", "ring"})
            elif expectation.type in ("event", "temporal") and re.search(
                r"\b(appointment|meeting)\b", claim
            ):
                allowed = frozenset({"calendar", "outlook", "bee"})
        self.scope = ExpectationPrivacyScope(
            expectation_type=str(expectation.type),
            allowed_sources=allowed,
        )

    def decide(self, evidence: EvidenceResponse) -> SourceDecision:
        key = source_key(evidence.source)
        return SourceDecision(
            evidence_id=evidence.id,
            source=SOURCES.get(key or "", EvidenceSource.OTHER),
            allowed=key is not None and key in self.scope.allowed_sources,
        )
