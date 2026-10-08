"""Conservative deterministic guards for model interpretation, never evaluation."""

import json
import re
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.db.models.expectation import ComparisonType, ExpectationType
from app.schemas.compiler import (
    ClarificationReason,
    ClarificationRequest,
    CompileContext,
    CompiledExpectation,
)
from app.schemas.expectation import ExpectationCreate

NUMBER = r"[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?"
COMPARISONS = (
    (r"no more than|at most|less than or equal to", ComparisonType.less_than_or_equal),
    (
        r"at least|no less than|greater than or equal to",
        ComparisonType.greater_than_or_equal,
    ),
    (r"under|below|less than|lower than", ComparisonType.less_than),
    (r"over|above|greater than|higher than", ComparisonType.greater_than),
    (r"not equal to", ComparisonType.not_equal),
    (r"equal to|exactly|stays the same as", ComparisonType.equal),
)
WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)


class GroundingError(Exception):
    """Safe semantic failure; never include original utterance/model output."""

    def __init__(self) -> None:
        super().__init__(
            "Compiler output could not be grounded in the user's statement"
        )


def clarification(
    text: str, reason: ClarificationReason, question: str, field: str
) -> ClarificationRequest:
    return ClarificationRequest(
        result="clarification",
        question=question,
        reason_code=reason,
        missing_fields=[field],
        partial_interpretation={"claim": text.strip()},
    )


def comparison_of(text: str) -> ComparisonType | None:
    for pattern, comparison in COMPARISONS:
        if re.fullmatch(pattern, text.strip(), flags=re.IGNORECASE):
            return comparison
    return None


def amount_of(quote: str) -> Decimal | None:
    # A proof span must have exactly one numeric value, with no malformed commas.
    if re.search(r"\d,(?!\d{3}(?:\D|$))", quote):
        return None
    values = re.findall(rf"(?<![\w.]){NUMBER}(?![\w.])", quote)
    if len(values) != 1:
        return None
    return Decimal(values[0].replace(",", ""))


def metric_for(subject: str) -> str:
    value = subject.lower().strip()
    if re.fullmatch(
        r"(?:my |the )?(?:grocery|groceries|electricity|electric|utility) (?:bill|spending|cost)",
        value,
    ):
        return "total_cost"
    if re.fullmatch(r"(?:my |the )?package", value):
        return "package_delivery"
    return re.sub(r"[^a-z0-9]+", "_", re.sub(r"^(my |the )", "", value)).strip("_")


def resolve_deadline(
    text: str, context: CompileContext
) -> datetime | ClarificationRequest | None:
    """Sunday week end, end-of-day inclusive deadlines, explicit AM/PM times.

    Unsupported dates/ranges clarify instead of delegating calendar math to AI.
    """
    local = context.current_time.astimezone(ZoneInfo(context.timezone))
    normalized = text.lower()
    if re.search(r"\bafter\s+\d", normalized):
        return clarification(
            text,
            ClarificationReason.AMBIGUOUS_DEADLINE,
            "Do you mean a deadline or a time window? CountOn currently stores one deadline.",
            "deadline",
        )
    clocks = list(
        re.finditer(
            r"\b(?:by|at|before)\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\b", normalized
        )
    )
    if len(clocks) > 1:
        return clarification(
            text,
            ClarificationReason.AMBIGUOUS_DEADLINE,
            "Which single deadline should CountOn monitor?",
            "deadline",
        )
    clock = clocks[0] if clocks else None
    if clock and not clock.group(3):
        return clarification(
            text,
            ClarificationReason.AMBIGUOUS_DEADLINE,
            "Is that time AM or PM?",
            "deadline",
        )
    day = None
    hits = 0
    if "this week" in normalized:
        day = local.date() + timedelta(days=(6 - local.weekday()) % 7)
        hits += 1
    if re.search(r"\btomorrow\b", normalized):
        day = local.date() + timedelta(days=1)
        hits += 1
    if re.search(r"\btoday\b", normalized):
        day = local.date()
        hits += 1
    weekdays = list(
        re.finditer(r"\b(next\s+)?(" + "|".join(WEEKDAYS) + r")\b", normalized)
    )
    for weekday in weekdays:
        if re.search(r"last\s+$", normalized[: weekday.start()]):
            continue
        delta = (WEEKDAYS.index(weekday.group(2)) - local.weekday()) % 7
        # 'next Tuesday' means the next strictly future occurrence.
        if weekday.group(1) and delta == 0:
            delta = 7
        day = local.date() + timedelta(days=delta)
        hits += 1
    if hits > 1:
        return clarification(
            text,
            ClarificationReason.AMBIGUOUS_DEADLINE,
            "Which date should be the deadline?",
            "deadline",
        )
    # Explicit date syntax outside the supported subset is never silently lost.
    if hits == 0 and (
        clock
        or re.search(
            r"\b(?:next|this) (?:month|year|week)|\b\d{4}-\d{2}-\d{2}\b|\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b|\b\d{1,2}/\d{1,2}\b|\bin \d+ (?:days?|weeks?)\b",
            normalized,
        )
    ):
        return clarification(
            text,
            ClarificationReason.AMBIGUOUS_DEADLINE,
            "What exact local date and time should be the deadline?",
            "deadline",
        )
    if day is None:
        return None
    wall_time = time(23, 59, 59, 999000)
    if clock:
        hour, minute = int(clock.group(1)), int(clock.group(2) or 0)
        if not 1 <= hour <= 12 or not 0 <= minute <= 59:
            return clarification(
                text,
                ClarificationReason.AMBIGUOUS_DEADLINE,
                "What valid time should be the deadline?",
                "deadline",
            )
        wall_time = time(hour % 12 + (12 if clock.group(3) == "pm" else 0), minute)
    resolved = datetime.combine(day, wall_time, tzinfo=ZoneInfo(context.timezone))
    # Round-trip detects DST gaps; two distinct UTC folds detect ambiguous times.
    roundtrip = resolved.astimezone(timezone.utc).astimezone(resolved.tzinfo)
    if (
        roundtrip.replace(tzinfo=None) != resolved.replace(tzinfo=None)
        or resolved.replace(fold=0).utcoffset() != resolved.replace(fold=1).utcoffset()
    ):
        return clarification(
            text,
            ClarificationReason.AMBIGUOUS_DEADLINE,
            "That local time is ambiguous or does not exist due to daylight saving time. Which time should I use?",
            "deadline",
        )
    if resolved <= context.current_time:
        return clarification(
            text,
            ClarificationReason.AMBIGUOUS_DEADLINE,
            "That deadline has already passed. Which future date and time do you mean?",
            "deadline",
        )
    return resolved.astimezone(timezone.utc)


def ground_compiled(
    text: str, context: CompileContext, compiled: CompiledExpectation
) -> CompiledExpectation | ClarificationRequest:
    e, proof = compiled.expectation, compiled.grounding
    for quote in [
        proof.subject_quote,
        proof.target_quote,
        proof.baseline_quote,
        proof.comparison_quote,
        *proof.source_quotes,
    ]:
        if quote is not None and (not quote.strip() or quote not in text):
            raise GroundingError()
    subject = proof.subject_quote.lower().strip()
    if subject in ("bill", "my bill", "the bill", "it", "this", "that"):
        return clarification(
            text,
            ClarificationReason.MISSING_SUBJECT,
            "Which bill or subject do you want CountOn to monitor?",
            "subject",
        )
    if e.metric != metric_for(proof.subject_quote):
        raise GroundingError()
    default_threshold = ExpectationCreate.model_fields["materiality_threshold"].default
    if e.materiality_threshold != default_threshold:
        raise GroundingError()
    # Sources must be explicitly named by the user, not inferred from subject.
    if e.evidence_sources != proof.source_quotes:
        raise GroundingError()
    for source in e.evidence_sources:
        if not re.search(
            r"(?:using|from|source(?: is|:)?|via)\s+" + re.escape(source) + r"(?:\b|$)",
            text,
            re.IGNORECASE,
        ):
            raise GroundingError()
    if e.type == ExpectationType.numeric_comparison:
        if (
            not proof.comparison_quote
            or comparison_of(proof.comparison_quote) != e.comparison
        ):
            raise GroundingError()
        if e.target_value is not None:
            if (
                not proof.target_quote
                or amount_of(proof.target_quote) != Decimal(str(e.target_value))
                or proof.baseline_quote
            ):
                raise GroundingError()
            # A target must be linked to the comparison, not an unrelated number.
            linked = re.search(
                re.escape(proof.comparison_quote) + r"\s+(?:[$€£]|USD\s*)?" + NUMBER,
                text,
                re.IGNORECASE,
            )
            if not linked or amount_of(linked.group()) != Decimal(str(e.target_value)):
                raise GroundingError()
        if e.baseline is not None:
            if proof.comparison_quote and re.search(
                re.escape(proof.comparison_quote) + rf"\s+(?:[$€£]|USD\s*)?{NUMBER}",
                text,
                re.IGNORECASE,
            ):
                raise GroundingError()  # A direct numeric limit is a target, not history.
            if (
                not proof.baseline_quote
                or amount_of(proof.baseline_quote) != Decimal(str(e.baseline))
                or proof.target_quote
            ):
                return clarification(
                    text,
                    ClarificationReason.MISSING_BASELINE,
                    "What baseline amount should I compare against?",
                    "baseline",
                )
            if not re.search(
                r"\b(?:last|previous|baseline|was)\b",
                proof.baseline_quote,
                re.IGNORECASE,
            ):
                raise GroundingError()
        if e.baseline is not None and not re.search(
            r"\b(?:last|previous|baseline)\b", text, re.IGNORECASE
        ):
            raise GroundingError()
        if e.metric == "total_cost":
            if re.search(
                r"[€£]|\b(?:EUR|GBP|CAD|AUD|euros?|pounds?)\b", text, re.IGNORECASE
            ):
                return clarification(
                    text,
                    ClarificationReason.AMBIGUOUS_CURRENCY,
                    "CountOn's current bill evidence convention uses USD. Which USD amount should I monitor?",
                    "currency",
                )
            if context.locale != "en-US" and not re.search(
                r"\b(?:USD|US dollars)\b", text, re.IGNORECASE
            ):
                return clarification(
                    text,
                    ClarificationReason.AMBIGUOUS_CURRENCY,
                    "Which currency do you mean? Current bill monitoring uses USD.",
                    "currency",
                )
    elif (
        re.search(r"\b(?:no|not|never)\b", text, re.IGNORECASE)
        or re.search(
            rf"\b(?:under|over|at most|at least|below|above|less than|lower than|greater than)\s+[$€£]?{NUMBER}",
            text,
            re.IGNORECASE,
        )
        or proof.target_quote
        or proof.baseline_quote
        or proof.comparison_quote
    ):
        raise GroundingError()
    deadline = resolve_deadline(text, context)
    if isinstance(deadline, ClarificationRequest):
        return deadline
    if e.deadline is not None and e.deadline != deadline:
        raise GroundingError()
    if e.type in (ExpectationType.temporal, ExpectationType.event) and deadline is None:
        return clarification(
            text,
            ClarificationReason.AMBIGUOUS_DEADLINE,
            "By what date and time do you expect this to happen?",
            "deadline",
        )
    # Preserve the user's claim exactly; deterministic defaults/calendar math win.
    payload = e.model_dump(mode="json")
    payload.update(
        claim=text.strip(),
        deadline=deadline.isoformat() if deadline else None,
        materiality_threshold=default_threshold,
    )
    compiled.expectation = ExpectationCreate.model_validate_json(
        json.dumps(payload), strict=True
    )
    return compiled
