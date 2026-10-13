"""Allow only operational evidence metadata; provider content belongs in ``value``.

Evidence is a normalized CountOn fact, not a copy of a provider record.  This
allowlist is intentionally small and shared by every ingestion path so a future
adapter cannot accidentally persist a message body, transcript, attachment,
audio/video URL, credential, or arbitrary provider JSON in ``raw_data``.
"""

from typing import Any

from pydantic import JsonValue

_SCALAR_KEYS = {
    "access",
    "account_fingerprint",
    "absence_verified",
    "binding_id",
    "binding_rule",
    "category",
    "connection_id",
    "coverage_signature",
    "coverage_start_at",
    "coverage_through_at",
    "effective_at",
    "event_id",
    "external_id",
    "oauth_generation",
    "observed_at",
    "parser",
    "permission",
    "provenance",
    "provider",
    "provider_record_ref",
    "received_at",
    "report_basis",
    "sender_authenticated",
    "sender_rule_matched",
    "simulated",
    "source_category",
    "source_event_id",
    "source_timestamp",
    "source_version",
    "verified_at",
}


def _scalar(value: Any) -> JsonValue | None:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:1024]
    return None


def minimize_raw_data(raw_data: dict[str, Any] | None) -> dict[str, JsonValue]:
    """Return safe traceability metadata and discard every unrecognized field."""
    if not isinstance(raw_data, dict):
        return {}
    result: dict[str, JsonValue] = {}
    for key in _SCALAR_KEYS:
        if key not in raw_data:
            continue
        value = _scalar(raw_data[key])
        if value is not None:
            result[key] = value
    correlation = raw_data.get("correlation")
    if isinstance(correlation, dict):
        safe: dict[str, JsonValue] = {}
        if isinstance(correlation.get("cancelled"), bool):
            safe["cancelled"] = correlation["cancelled"]
        if isinstance(correlation.get("start"), str):
            safe["start"] = correlation["start"][:80]
        if safe:
            result["correlation"] = safe
    return result
