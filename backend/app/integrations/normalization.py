"""Conservative provider facts. External prose is data, never instructions.

No message body is retained. Ambiguous amounts/dates are deliberately omitted.
Sender fields are provider-reported identities, not proof of sender authenticity.
"""

import base64
import hashlib
import json
import re
from datetime import date, datetime, timezone
from email.utils import getaddresses, parseaddr
from html import unescape
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.integrations.provider import ProviderError

NORMALIZER_VERSION = "normalization_v3"


def version(facts: dict) -> str:
    return hashlib.sha256(
        json.dumps(facts, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def timestamp(value: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timezone required")
    return parsed.astimezone(timezone.utc).isoformat()


def calendar_time(value: dict) -> str | None:
    if "date" in value:
        return date.fromisoformat(value["date"]).isoformat()
    raw = value.get("dateTime")
    if not isinstance(raw, str):
        return None
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        zone = ZoneInfo(value.get("timeZone", "UTC"))
        a, b = parsed.replace(tzinfo=zone, fold=0), parsed.replace(tzinfo=zone, fold=1)
        # Ambiguous or non-existent wall clocks must not become invented instants.
        if (
            a.utcoffset() != b.utcoffset()
            or a.astimezone(timezone.utc).astimezone(zone).replace(tzinfo=None)
            != parsed
        ):
            return None
        parsed = a
    return parsed.astimezone(timezone.utc).isoformat()


def gmail_text(payload: dict, depth: int = 0) -> str:
    if depth > 8:
        return ""
    if payload.get("filename"):
        return ""  # no attachment download
    raw = payload.get("body", {}).get("data", "")
    try:
        text = (
            base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)).decode(
                "utf-8", errors="replace"
            )[:32000]
            if isinstance(raw, str) and len(raw) <= 45000
            else ""
        )
    except (ValueError, UnicodeError):
        text = ""
    parts = payload.get("parts", [])
    plain = [p for p in parts if p.get("mimeType") == "text/plain"]
    if parts:
        text = "\n".join(gmail_text(p, depth + 1) for p in (plain or parts)[:30])[
            :32000
        ]
    return unescape(re.sub(r"<[^>]{0,1000}>", " ", text))


def mail_facts(message: dict, provider: str) -> dict:
    if provider == "google":
        headers = {
            str(h.get("name", "")).lower(): str(h.get("value", ""))
            for h in message.get("payload", {}).get("headers", [])[:100]
        }
        sender = parseaddr(headers.get("from", ""))[1].lower()
        subject = headers.get("subject", "")[:300]
        body = gmail_text(message.get("payload", {}))
        observed = datetime.fromtimestamp(
            int(message["internalDate"]) / 1000, timezone.utc
        ).isoformat()
        thread = message.get("threadId", "")
        recipients = [
            address.casefold()
            for _, address in getaddresses([headers.get("to", "")])
            if address
        ][:30]
    else:
        sender = str(
            message.get("from", {}).get("emailAddress", {}).get("address", "")
        ).lower()
        subject = str(message.get("subject", ""))[:300]
        body = unescape(
            re.sub(
                r"<[^>]{0,1000}>",
                " ",
                str(message.get("body", {}).get("content", ""))[:32000],
            )
        )
        observed = timestamp(message["receivedDateTime"])
        thread = message.get("conversationId", "")
        recipients = [
            str(r.get("emailAddress", {}).get("address", "")).casefold()
            for r in message.get("toRecipients", [])[:30]
        ]
    text = subject + "\n" + body
    if "@" not in sender or not isinstance(thread, str) or not thread:
        raise ProviderError("PROVIDER_RESPONSE_INVALID", retryable=False)
    facts = {
        "kind": "email",
        "sender": sender[:254],
        "subject": subject,
        "thread_id": str(thread)[:512],
        "source_timestamp": observed,
        "sender_authenticated": False,
        "report_basis": "email_reported",
    }
    if recipients:
        facts["recipients"] = recipients
    # Only explicitly labeled identifiers/timestamps; prose/title similarity is
    # never sufficient to associate an email with a calendar occurrence.
    uids = set(
        re.findall(r"(?im)^\s*(?:iCalUID|Calendar UID)\s*:\s*([^\s]{1,255})\s*$", text)
    )
    if len(uids) == 1:
        facts["calendar_uid"] = uids.pop()
    for key, label in (
        ("event_start", "Event start"),
        ("original_start", "Original start"),
    ):
        labeled_times = set(
            re.findall(rf"(?im)^\s*{label}\s*:\s*([^\s]{{1,80}})\s*$", text)
        )
        if len(labeled_times) == 1:
            try:
                facts[key] = timestamp(labeled_times.pop())
            except ValueError:
                pass
    if provider == "google" and message.get("historyId"):
        facts["provider_revision"] = str(message["historyId"])[:100]
    elif provider == "microsoft" and message.get("lastModifiedDateTime"):
        facts["provider_revision"] = timestamp(message["lastModifiedDateTime"])
    # A single explicitly labeled total only. Arbitrary dollar figures aren't bills.
    amounts = re.findall(
        r"(?i)\b(?:total(?:\s+amount)?(?:\s+due)?|amount\s+due|invoice\s+total)\s*[:=]\s*(?:USD\s*)?\$\s*(\d{1,8}(?:\.\d{2})?)\b",
        text,
    )
    if len(set(amounts)) == 1 and not re.search(
        r"\b(?:CAD|AUD|NZD|EUR|GBP|JPY)\b", text
    ):
        facts["amount"] = float(amounts[0])
        facts["currency"] = "USD"
    status_words = r"(?:cancelled|canceled|cancellation|confirmed|confirmation|delivered|shipped|rescheduled|delay(?:ed)?)"
    uncertain_status = bool(
        re.search(
            rf"(?i)\b(?:not|never|no|isn.t|wasn.t|hasn.t|won.t|might|may|could|will|would|should|if|unless)\b[^.!?\n]{{0,60}}\b{status_words}\b",
            text,
        )
        or re.search(
            rf"(?i)\b{status_words}\b[^.!?\n]{{0,25}}\b(?:policy|fees?|terms|request|option)\b",
            text,
        )
    )
    states = []
    for label, pattern in (
        ("cancelled", r"\b(?:cancelled|canceled|cancellation)\b"),
        ("rescheduled", r"\b(?:rescheduled|rescheduling)\b"),
        ("confirmed", r"\b(?:confirmed|confirmation)\b"),
        ("delayed", r"\b(?:delayed|delay)\b"),
    ):
        if re.search(pattern, text, re.IGNORECASE):
            states.append(label)
    if len(states) == 1 and not uncertain_status:
        facts["commitment_status"] = states[0]
    dates = re.findall(
        r"(?i)\b(?:deadline|due\s+date)\s*:\s*(\d{4}-\d{2}-\d{2})\b", text
    )
    if len(set(dates)) == 1:
        try:
            facts["deadline"] = date.fromisoformat(dates[0]).isoformat()
        except ValueError:
            pass
    orders = set(re.findall(r"\b\d{3}-\d{7}-\d{7}\b", text))
    if len(orders) == 1:
        facts["order_id"] = orders.pop()
        facts["merchant_reference"] = sender
        # A status is a report, not independently verified fulfillment.
        statuses = [
            status
            for status, pattern in (
                (
                    "delivered",
                    r"\b(?:was delivered|has been delivered|delivered today)\b",
                ),
                ("shipped", r"\b(?:has shipped|was shipped|shipping confirmation)\b"),
                ("delayed", r"\b(?:delivery delayed|delivery delay)\b"),
                ("ordered", r"\border confirmation\b"),
            )
            if re.search(pattern, text, re.IGNORECASE)
        ]
        if len(statuses) == 1 and not uncertain_status:
            facts["shipping_status"] = statuses[0]
            delivered = re.findall(
                r"(?i)\bdelivered at\s*:\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d{1,6})?)?(?:Z|[+-]\d{2}:\d{2}))\b",
                text,
            )
            if len(set(delivered)) == 1 and statuses[0] == "delivered":
                try:
                    facts["delivery_timestamp"] = timestamp(delivered[0])
                except ValueError:
                    pass
        for key, label in (
            ("expected_delivery_date", "expected delivery"),
            ("revised_delivery_date", "revised delivery"),
        ):
            values = re.findall(
                rf"(?i)\b{label}\s*:\s*(\d{{4}}-\d{{2}}-\d{{2}})\b", text
            )
            if len(set(values)) == 1:
                try:
                    facts[key] = date.fromisoformat(values[0]).isoformat()
                except ValueError:
                    pass
        tracks = re.findall(
            r"(?i)\btracking (?:number|id)\s*:\s*([A-Z0-9-]{8,50})\b", text
        )
        if len(set(tracks)) == 1:
            facts["tracking_id"] = tracks[0]
    return facts


def calendar_facts(event: dict, provider: str) -> dict:
    if event.get("@removed") or event.get("unavailable"):
        return {"kind": "calendar", "unavailable": True}
    try:
        facts = {
            "kind": "calendar",
            "title": str(
                event.get("summary" if provider == "google" else "subject", "")
            )[:300],
            "start": calendar_time(event.get("start", {})),
            "end": calendar_time(event.get("end", {})),
            "all_day": bool(event.get("isAllDay") or "date" in event.get("start", {})),
            "cancelled": event.get("status") == "cancelled"
            if provider == "google"
            else event.get("isCancelled") is True,
            "recurring_id": str(
                event.get("recurringEventId") or event.get("seriesMasterId") or ""
            )[:512],
            "original_start": (
                calendar_time(event.get("originalStartTime", {}))
                if provider == "google"
                else timestamp(event["originalStart"])
                if event.get("originalStart")
                else None
            ),
            "source_timestamp": timestamp(
                event["updated" if provider == "google" else "lastModifiedDateTime"]
            )
            if event.get("updated" if provider == "google" else "lastModifiedDateTime")
            else None,
        }
        uid = event.get("iCalUID" if provider == "google" else "iCalUId")
        if isinstance(uid, str) and 0 < len(uid) <= 255:
            facts["calendar_uid"] = uid
        if facts["start"] is None and not facts["cancelled"]:
            facts["unavailable"] = True
        return facts
    except (ValueError, TypeError, ZoneInfoNotFoundError):
        raise ProviderError("PROVIDER_RESPONSE_INVALID", retryable=False) from None
