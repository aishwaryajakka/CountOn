"""Grounded patches and deterministic question/assembly, reusing compiler guards."""

import json
import re
from decimal import Decimal

from app.ai.compiler_grounding import (
    COMPARISONS,
    NUMBER,
    GroundingError,
    amount_of,
    comparison_of,
    ground_compiled,
    metric_for,
    resolve_deadline,
)
from app.schemas.clarification import (
    ConversationField,
    FieldPatch,
    PartialInterpretation,
)
from app.schemas.compiler import (
    ClarificationRequest,
    CompileContext,
    CompiledExpectation,
    Grounding,
)
from app.schemas.expectation import ExpectationCreate


def normalized_subject(value: str) -> str:
    return re.sub(r"^(?:my|the)\s+", "", value.strip().lower()).strip(" .!?")


def bill_arrival(text: str, subject: str) -> bool:
    """An explicit evidence-arrival trigger, never an invented calendar deadline."""
    return bool(
        re.search(r"\bbill\b", subject)
        and re.search(
            r"\b(?:when (?:my |the )?next (?:electricity )?bill arrives|next (?:electricity )?bill)\b",
            text,
            re.IGNORECASE,
        )
    )


def subject_type(subject: str) -> str | None:
    if re.search(r"\bbill|spending|cost|temperature|weight|price\b", subject):
        return "numeric_comparison"
    if "package" in subject:
        return "temporal"
    return None


def temporal_phrase(text: str) -> str:
    clock = re.search(
        r"\b(?:by|at|before|after)\s+\d{1,2}(?::\d{2})?\s*(?:AM|PM)?\b",
        text,
        re.IGNORECASE,
    )
    day = re.search(
        r"\b(?:this week|today|tomorrow|(?:next\s+)?(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday))\b",
        text,
        re.IGNORECASE,
    )
    if day:
        return (clock.group().strip() + " " if clock else "") + day.group()
    return text[:200]


def seed_facts(text: str, context: CompileContext) -> PartialInterpretation:
    """Retain only explicit deterministic facts; never trust guessed model partials."""
    facts = PartialInterpretation()
    match = re.search(
        r"\bmy\s+(.+?)\s+(?:should|will|being|staying|to stay|stays|is|arrives?|moves?)\b",
        text,
        re.IGNORECASE,
    )
    if match:
        subject = normalized_subject(match.group(1))
        if subject not in ("bill", "it", "thing"):
            facts.subject = subject
            facts.values["metric"] = metric_for(subject)
        kind = subject_type(subject)
        if kind:
            facts.values["type"] = kind
    for pattern, comparison in COMPARISONS:
        comparison_match = re.search(r"\b(?:" + pattern + r")\b", text, re.IGNORECASE)
        if not comparison_match:
            continue
        facts.values["comparison"] = comparison.value
        facts.values.setdefault("type", "numeric_comparison")
        target = re.match(
            r"\s+(?:[$]|USD\s*)?(" + NUMBER + r")",
            text[comparison_match.end() :],
            re.IGNORECASE,
        )
        if target:
            facts.operand = "target"
            facts.values["target_value"] = float(
                Decimal(target.group(1).replace(",", ""))
            )
        break
    if not facts.values.get("comparison") and re.search(
        r"\blower\b", text, re.IGNORECASE
    ):
        facts.values["comparison"] = "less_than"
    if (
        re.search(
            r"\b(?:last month|last bill|previous bill|baseline)\b", text, re.IGNORECASE
        )
        and facts.operand is None
    ):
        facts.operand = "baseline"
        facts.baseline_reference = (
            "last_month"
            if "last month" in text.lower()
            else "previous_bill"
            if "previous bill" in text.lower() or "last bill" in text.lower()
            else "baseline"
        )
        baseline = re.search(
            r"\b(?:was|baseline(?: is|:))\s+[$]?(" + NUMBER + r")", text, re.IGNORECASE
        )
        if baseline:
            facts.values["baseline"] = float(
                Decimal(baseline.group(1).replace(",", ""))
            )
    if context.locale == "en-US" or re.search(
        r"\b(?:USD|US dollars)\b", text, re.IGNORECASE
    ):
        facts.currency = "USD"
    facts.values["evidence_sources"] = [
        m.group(1)
        for m in re.finditer(
            r"\b(?:using|via|source(?: is|:))\s+([A-Za-z][A-Za-z0-9_]*)", text
        )
        if m.group(1).lower() not in ("usd", "last", "previous", "the", "my")
    ]

    deadline = resolve_deadline(text, context)
    if isinstance(deadline, ClarificationRequest):
        facts.pending_deadline = temporal_phrase(text)
        facts.pending_reference_time = context.current_time
    elif deadline:
        facts.deadline_phrase = temporal_phrase(text)
        facts.deadline_reference_time = context.current_time
        facts.values["deadline"] = deadline.isoformat()
    elif bill_arrival(text, facts.subject or ""):
        facts.deadline_phrase = "when my next bill arrives"
        facts.deadline_reference_time = context.current_time
    return PartialInterpretation.model_validate(facts.model_dump())


def next_question(
    facts: PartialInterpretation, *, require_timing: bool = False
) -> tuple[ConversationField, str] | None:
    if not facts.subject:
        return "subject", "Which bill or subject do you mean?"
    if not facts.values.get("type"):
        return "subject", "What do you expect to happen to that subject?"
    if facts.values["type"] == "numeric_comparison":
        if not facts.values.get("comparison"):
            return "comparison", "Should it be lower, higher, or equal to an amount?"
        if not facts.operand:
            return (
                "operand",
                "What should I compare it against?",
            )
        if (
            facts.values.get(
                "baseline" if facts.operand == "baseline" else "target_value"
            )
            is None
        ):
            if facts.operand == "baseline":
                question = (
                    "What was last month's bill amount?"
                    if facts.baseline_reference == "last_month"
                    else "What was the previous bill amount?"
                    if facts.baseline_reference == "previous_bill"
                    else "What amount should I compare it with?"
                )
                return "baseline", question
            return "target_value", "What amount should I compare it with?"
        if facts.values.get("metric") == "total_cost" and not facts.currency:
            return (
                "currency",
                "Which currency do you mean? Current bill monitoring uses USD.",
            )
    if facts.pending_deadline or (
        facts.values["type"] in ("temporal", "event")
        and not facts.values.get("deadline")
    ):
        return "deadline", "What date and time do you mean? Please include AM or PM."
    if (
        require_timing
        and not facts.values.get("deadline")
        and not bill_arrival(facts.deadline_phrase or "", facts.subject or "")
    ):
        return "deadline", "When should I check it?"
    return None


def verify_patch(
    patch: FieldPatch,
    answer: str,
    facts: PartialInterpretation,
    context: CompileContext,
) -> None:
    if patch.quote not in answer or not patch.quote.strip():
        raise GroundingError()
    if patch.field == "subject":
        if (
            not isinstance(patch.value, str)
            or normalized_subject(patch.quote) != normalized_subject(patch.value)
            or not re.fullmatch(r"[a-z0-9 -]{1,200}", normalized_subject(patch.value))
        ):
            raise GroundingError()
    elif patch.field in ("target_value", "baseline"):
        if (
            isinstance(patch.value, bool)
            or not isinstance(patch.value, (int, float))
            or amount_of(patch.quote) != Decimal(str(patch.value))
        ):
            raise GroundingError()
        before = answer[: answer.find(patch.quote)]
        if re.search(r"\bnot\s*[$]?\s*$", before, re.IGNORECASE):
            raise GroundingError()
    elif patch.field == "comparison":
        comparison = comparison_of(patch.quote) or (
            comparison_of("lower than") if patch.quote.lower() == "lower" else None
        )
        if comparison is None or patch.value != comparison.value:
            raise GroundingError()
    elif patch.field == "operand":
        if patch.value == "baseline" and not re.search(
            r"last month|last bill|previous|baseline", patch.quote, re.IGNORECASE
        ):
            raise GroundingError()
        if patch.value == "target" and not re.search(
            r"under|over|at most|at least|specific|limit|target|exactly|no more than",
            patch.quote,
            re.IGNORECASE,
        ):
            raise GroundingError()
        if patch.value not in ("target", "baseline"):
            raise GroundingError()
    elif patch.field == "currency":
        if patch.value != "USD" or not re.fullmatch(
            r"USD|US dollars", patch.quote, re.IGNORECASE
        ):
            raise GroundingError()
    elif patch.field == "deadline" and (
        not isinstance(patch.value, str) or patch.value.strip() != patch.quote.strip()
    ):
        raise GroundingError()


def merge_patches(
    facts: PartialInterpretation, patches: list[FieldPatch], context: CompileContext
) -> PartialInterpretation:
    merged = facts.model_copy(deep=True)
    for patch in patches:
        if patch.field == "subject":
            merged.subject = normalized_subject(str(patch.value))
            if merged.subject in ("bill", "it", "thing"):
                merged.subject = None
                merged.values.pop("metric", None)
            else:
                merged.values["metric"] = metric_for(merged.subject)
                kind = subject_type(merged.subject)
                if kind:
                    merged.values["type"] = kind
        elif patch.field == "operand":
            merged.operand = "baseline" if patch.value == "baseline" else "target"
            merged.baseline_reference = (
                (
                    "last_month"
                    if "last month" in patch.quote.lower()
                    else "previous_bill"
                    if "previous" in patch.quote.lower()
                    or "last bill" in patch.quote.lower()
                    else "baseline"
                )
                if patch.value == "baseline"
                else None
            )
            merged.values.pop(
                "target_value" if patch.value == "baseline" else "baseline", None
            )
        elif patch.field == "currency":
            merged.currency = "USD"
        elif patch.field == "deadline":
            phrase = str(patch.value)
            reference = context.current_time
            if merged.pending_deadline and re.fullmatch(
                r"\d{1,2}(?::\d{2})?\s*(?:AM|PM)", phrase, re.IGNORECASE
            ):
                phrase = re.sub(
                    r"\b(?:by|at|before)\s+\d{1,2}(?::\d{2})?\b",
                    "by " + phrase,
                    merged.pending_deadline,
                    flags=re.IGNORECASE,
                )
                reference = facts.pending_reference_time or context.current_time
            deadline_context = CompileContext(
                current_time=reference, timezone=context.timezone, locale=context.locale
            )
            resolved = resolve_deadline(phrase, deadline_context)
            if bill_arrival(phrase, merged.subject or ""):
                merged.pending_deadline = None
                merged.pending_reference_time = None
                merged.deadline_phrase = "when my next bill arrives"
                merged.deadline_reference_time = reference
                merged.values.pop("deadline", None)
            elif isinstance(resolved, ClarificationRequest) or resolved is None:
                merged.pending_deadline = phrase[:200]
                merged.pending_reference_time = reference
            else:
                merged.pending_deadline = None
                merged.pending_reference_time = None
                merged.deadline_phrase = phrase
                merged.deadline_reference_time = reference
                merged.values["deadline"] = resolved.isoformat()
        else:
            merged.values[patch.field] = patch.value
    return PartialInterpretation.model_validate(merged.model_dump())


def assemble(
    facts: PartialInterpretation, context: CompileContext
) -> CompiledExpectation:
    """Assemble established facts, then reuse existing domain/grounding validation."""
    subject = facts.subject
    if subject is None or next_question(facts):
        raise GroundingError()
    kind = facts.values["type"]
    proof = Grounding(subject_quote=subject)
    if kind == "numeric_comparison":
        comparison = facts.values["comparison"]
        words = next(
            pattern.split("|")[0]
            for pattern, enum in COMPARISONS
            if enum.value == comparison
        )
        proof.comparison_quote = words
        number = facts.values[
            "baseline" if facts.operand == "baseline" else "target_value"
        ]
        amount = "$" + str(number) + " USD" if facts.currency else str(number)
        if facts.operand == "baseline":
            words = {"less_than": "lower than", "greater_than": "higher than"}.get(
                str(comparison), words
            )
            proof.comparison_quote = words
            reference_label, label = {
                "last_month": ("last month's amount", "last month was"),
                "previous_bill": ("the previous bill", "previous bill was"),
                "baseline": ("the reference amount", "baseline was"),
            }[facts.baseline_reference or "baseline"]
            text = f"My {subject} should be {words} {reference_label}; {label} {amount}"
            proof.baseline_quote = f"{label} {amount}"
        else:
            text = f"My {subject} should stay {words} {amount}"
            proof.target_quote = amount
    else:
        text = f"My {subject} should arrive"
    if facts.deadline_phrase:
        # Seed phrases can include the original claim; extract only supported date/time
        # words so previous subjects/limits never reappear in the final claim.
        phrase = facts.deadline_phrase
        clock = re.search(
            r"\b(?:by|at|before)\s+\d{1,2}(?::\d{2})?\s*(?:AM|PM)\b",
            phrase,
            re.IGNORECASE,
        )
        day = re.search(
            r"\b(?:this week|today|tomorrow|(?:next\s+)?(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday))\b",
            phrase,
            re.IGNORECASE,
        )
        if bill_arrival(phrase, subject):
            text += " when my next bill arrives"
        elif not day:
            raise GroundingError()
        else:
            text += " " + (clock.group() + " " if clock else "") + day.group()
    sources = facts.values.get("evidence_sources", [])
    if not isinstance(sources, list) or not all(
        isinstance(source, str) for source in sources
    ):
        raise GroundingError()
    for source in sources:
        if not isinstance(source, str):
            raise GroundingError()
        text += f" using {source}"
        proof.source_quotes.append(source)
    payload = dict(facts.values)
    payload["claim"] = text + "."
    e = ExpectationCreate.model_validate_json(json.dumps(payload), strict=True)
    candidate = CompiledExpectation(result="compiled", expectation=e, grounding=proof)
    reference = facts.deadline_reference_time or context.current_time
    validated = ground_compiled(
        text + ".",
        CompileContext(
            current_time=reference, timezone=context.timezone, locale=context.locale
        ),
        candidate,
    )
    if not isinstance(validated, CompiledExpectation):
        raise GroundingError()
    return validated
