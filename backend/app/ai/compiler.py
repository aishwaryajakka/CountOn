"""
Expectation Compiler Implementation with Multi-Turn Memory, Corrections, and Cancellations.
"""

import os
import json
import re
from typing import Optional, List, Dict, Any
from app.ai.models.expectation import (
    Expectation,
    ClarificationRequest,
    CancellationRequest,
    ExpectationCompilationResult,
)
from app.ai.bedrock_client import BedrockClient
from app.ai.prompts import EXPECTATION_COMPILER_SYSTEM_PROMPT
from app.ai.exceptions import (
    BedrockClientError,
    InvalidModelResponse,
    ExpectationCompilationError,
)


def _should_use_mock(explicit_mock: Optional[bool] = None) -> bool:
    """Determine whether to use offline mock mode."""
    if explicit_mock is not None:
        return explicit_mock

    env_mock = os.environ.get("COUNTON_MOCK_AI", "").strip().lower()
    if env_mock in ("1", "true", "yes", "on"):
        return True

    if not os.environ.get("AWS_ACCESS_KEY_ID") and not os.environ.get("AWS_CONTAINER_CREDENTIALS_RELATIVE_URI"):
        return True

    return False


def _mock_compile_expectation(
    user_text: str,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    draft_expectation: Optional[Dict[str, Any]] = None,
    expectation_id: Optional[str] = None,
) -> ExpectationCompilationResult:
    """
    Local Rule-Based Mock Compiler for offline testing with multi-turn memory,
    corrections, and cancellations.
    """
    text = user_text.strip()
    lowered = text.lower()

    # Combine previous history text if available
    history_texts = []
    if conversation_history:
        for turn in conversation_history:
            if isinstance(turn, dict) and turn.get("content"):
                history_texts.append(turn["content"].lower())
    history_combined = " ".join(history_texts)

    # 1. Check for Cancellation Intent
    cancel_keywords = ["cancel", "stop tracking", "don't track", "dont track", "stop monitoring", "delete expectation"]
    if any(kw in lowered for kw in cancel_keywords):
        target = user_text
        for kw in cancel_keywords:
            if kw in lowered:
                target = user_text[lowered.find(kw) + len(kw):].strip(" .:?!") or user_text
                break
        return ExpectationCompilationResult(
            kind="cancellation",
            cancellation=CancellationRequest(
                expectation_id=expectation_id,
                target_claim=target or user_text,
                reason="User requested cancellation"
            )
        )

    # 2. Check for Empty / Whitespace Input
    if not text:
        return ExpectationCompilationResult(
            kind="clarification",
            clarification=ClarificationRequest(
                required=True,
                question="No statement was provided. Please describe what you expect to happen.",
                missing_fields=["claim", "deadline", "metric"],
                draft_expectation=draft_expectation,
            )
        )

    # 3. Check for Correction Intent ("actually", "change", "correction", "instead")
    is_correction_intent = any(w in lowered for w in ["actually", "correction", "change", "instead", "wait, make it", "update"])
    if is_correction_intent or (expectation_id and not history_combined):
        base_exp = draft_expectation or {}
        # Parse what is being corrected
        deadline = base_exp.get("deadline", "next_bill")
        if "tomorrow" in lowered:
            deadline = "tomorrow"
        elif "today" in lowered:
            deadline = "today"
        elif "this week" in lowered or "this_week" in lowered:
            deadline = "this_week"
        elif "next week" in lowered or "next_week" in lowered:
            deadline = "next_week"

        baseline = base_exp.get("baseline")
        # Check for numeric amount (e.g. $100, 120, 150)
        num_match = re.search(r"\$?(\d+(?:\.\d+)?)", user_text)
        if num_match:
            try:
                baseline = float(num_match.group(1))
            except ValueError:
                pass

        metric = base_exp.get("metric", "total_cost")
        if "gas" in lowered:
            metric = "gas_cost"
        elif "electricity" in lowered:
            metric = "total_cost"

        claim = user_text if not base_exp.get("claim") else f"Corrected: {user_text}"
        return ExpectationCompilationResult(
            kind="expectation",
            is_correction=True,
            expectation=Expectation(
                id=expectation_id or base_exp.get("id"),
                claim=claim,
                type=base_exp.get("type", "numeric_comparison"),
                metric=metric,
                comparison=base_exp.get("comparison", "less_than"),
                baseline=baseline,
                deadline=deadline,
                evidence_sources=base_exp.get("evidence_sources", ["utility_bill"]),
                materiality_threshold=base_exp.get("materiality_threshold", 0.05),
                status="monitoring",
            )
        )

    # 4. Multi-Turn Clarification Memory
    # If the user previously had a clarification request (e.g. "my bill should be lower" or draft_expectation)
    has_prior_bill = "bill" in history_combined or (draft_expectation and "bill" in str(draft_expectation).lower())
    has_prior_package = "package" in history_combined or (draft_expectation and "package" in str(draft_expectation).lower())

    if has_prior_bill:
        # Check if user clarified the bill type and deadline
        is_electric = "electric" in lowered or "power" in lowered or "ac" in lowered or "utility" in lowered
        is_gas = "gas" in lowered
        has_deadline = any(d in lowered for d in ["next month", "tomorrow", "this week", "next week", "next bill", "today"])

        if (is_electric or is_gas or "bill" in lowered) and has_deadline:
            deadline_str = "next_month" if "next month" in lowered else (
                "tomorrow" if "tomorrow" in lowered else (
                    "this_week" if "this week" in lowered else (
                        "next_week" if "next week" in lowered else "next_bill"
                    )
                )
            )
            metric_str = "gas_cost" if is_gas else "total_cost"
            return ExpectationCompilationResult(
                kind="expectation",
                expectation=Expectation(
                    id=expectation_id,
                    claim=f"My {'gas' if is_gas else 'electricity'} bill should be lower",
                    type="numeric_comparison",
                    metric=metric_str,
                    comparison="less_than",
                    deadline=deadline_str,
                    evidence_sources=["utility_bill", "utility_usage", "tariff", "weather"],
                    materiality_threshold=0.05,
                    status="monitoring",
                )
            )
        elif is_electric or is_gas:
            # Clarified bill type, but still missing deadline
            return ExpectationCompilationResult(
                kind="clarification",
                clarification=ClarificationRequest(
                    required=True,
                    question=f"When do you expect your {'gas' if is_gas else 'electricity'} bill to be lower (e.g. next month, next bill)?",
                    missing_fields=["deadline"],
                    draft_expectation={
                        "claim": f"My {'gas' if is_gas else 'electricity'} bill should be lower",
                        "type": "numeric_comparison",
                        "metric": "gas_cost" if is_gas else "total_cost",
                        "comparison": "less_than",
                    }
                )
            )

    if has_prior_package:
        if "tomorrow" in lowered or "today" in lowered or "this week" in lowered:
            deadline_val = "today" if "today" in lowered else ("tomorrow" if "tomorrow" in lowered else "this_week")
            return ExpectationCompilationResult(
                kind="expectation",
                expectation=Expectation(
                    id=expectation_id,
                    claim="My package should arrive",
                    type="delivery",
                    comparison="exists",
                    deadline=deadline_val,
                    evidence_sources=["delivery", "ring"],
                    status="monitoring",
                )
            )

    # 5. Single-Turn Ambiguous Statements
    if lowered in ["my bill should be lower.", "my bill should be lower", "bill should be lower"]:
        return ExpectationCompilationResult(
            kind="clarification",
            clarification=ClarificationRequest(
                required=True,
                question="Could you specify which bill (e.g. electricity, gas) and when you expect it to be lower?",
                missing_fields=["deadline", "metric", "baseline"],
                draft_expectation={
                    "claim": user_text,
                    "type": "numeric_comparison",
                    "comparison": "less_than",
                }
            )
        )

    if "soon" in lowered and "package" in lowered:
        return ExpectationCompilationResult(
            kind="clarification",
            clarification=ClarificationRequest(
                required=True,
                question="Could you specify an expected delivery date or timeframe instead of 'soon'?",
                missing_fields=["deadline"],
                draft_expectation={
                    "claim": user_text,
                    "type": "delivery",
                    "comparison": "exists",
                }
            )
        )

    # 6. Specific Complete Statements
    if "ac" in lowered and "bill" in lowered:
        return ExpectationCompilationResult(
            kind="expectation",
            expectation=Expectation(
                id=expectation_id,
                claim=user_text,
                type="numeric_comparison",
                metric="total_cost",
                comparison="less_than",
                deadline="next_bill",
                evidence_sources=["utility_bill", "utility_usage", "tariff", "weather"],
                materiality_threshold=0.05,
                status="monitoring"
            )
        )

    if "package" in lowered and "today" in lowered:
        return ExpectationCompilationResult(
            kind="expectation",
            expectation=Expectation(
                id=expectation_id,
                claim=user_text,
                type="delivery",
                comparison="exists",
                deadline="today",
                evidence_sources=["delivery", "ring"],
                status="monitoring"
            )
        )

    if "sarah" in lowered or ("send" in lowered and "tomorrow" in lowered and "document" in lowered):
        return ExpectationCompilationResult(
            kind="expectation",
            expectation=Expectation(
                id=expectation_id,
                claim=user_text,
                type="conversation_commitment",
                comparison="exists",
                deadline="tomorrow",
                evidence_sources=["bee", "conversation_context"],
                status="monitoring"
            )
        )

    if "refund" in lowered and "this week" in lowered:
        return ExpectationCompilationResult(
            kind="expectation",
            expectation=Expectation(
                id=expectation_id,
                claim=user_text,
                type="delivery",
                metric="refund_amount",
                comparison="exists",
                deadline="this_week",
                evidence_sources=["billing", "external_api"],
                status="monitoring"
            )
        )

    if "landlord" in lowered or "leak" in lowered:
        return ExpectationCompilationResult(
            kind="expectation",
            expectation=Expectation(
                id=expectation_id,
                claim=user_text,
                type="conversation_commitment",
                comparison="exists",
                deadline=None,
                evidence_sources=["conversation_context", "bee"],
                status="monitoring"
            )
        )

    if "outlook" in lowered or "dentist" in lowered:
        cal_deadline = "2026-10-05" if "dentist" in lowered else "upcoming"
        if "tomorrow" in lowered:
            cal_deadline = "tomorrow"
        elif "monday" in lowered:
            cal_deadline = "monday"
        elif "today" in lowered:
            cal_deadline = "today"
        is_cal = "calendar" in lowered or "dentist" in lowered or "meeting" in lowered or "appointment" in lowered
        return ExpectationCompilationResult(
            kind="expectation",
            expectation=Expectation(
                id=expectation_id,
                claim=user_text,
                type="event_occurrence" if is_cal else "conversation_commitment",
                metric="appointment_status" if is_cal else "email_confirmation",
                comparison="exists",
                deadline=cal_deadline,
                evidence_sources=["outlook_calendar"] if is_cal else ["outlook_email"],
                status="monitoring"
            )
        )

    # 7. Fallback General Parsing
    if "lower" in lowered or "less" in lowered:
        comp = "less_than"
    elif "higher" in lowered or "more" in lowered:
        comp = "greater_than"
    else:
        comp = "exists"

    deadline = "upcoming"
    if "tomorrow" in lowered:
        deadline = "tomorrow"
    elif "today" in lowered:
        deadline = "today"
    elif "this week" in lowered:
        deadline = "this_week"
    elif "next week" in lowered:
        deadline = "next_week"

    return ExpectationCompilationResult(
        kind="expectation",
        expectation=Expectation(
            id=expectation_id,
            claim=user_text,
            type="numeric_comparison" if "lower" in lowered or "higher" in lowered else "event_occurrence",
            comparison=comp,
            deadline=deadline,
            evidence_sources=["external_api"],
            status="monitoring"
        )
    )


def compile_expectation(
    user_text: str,
    mock_mode: Optional[bool] = None,
    conversation_history: Optional[List[Dict[str, str]]] = None,
    draft_expectation: Optional[Dict[str, Any]] = None,
    expectation_id: Optional[str] = None,
) -> ExpectationCompilationResult:
    """
    Public Function: Converts casual natural language user statements into a structured
    Expectation, ClarificationRequest, or CancellationRequest.
    Supports multi-turn conversation memory, corrections, and cancellations.
    """
    if not user_text or not user_text.strip():
        return ExpectationCompilationResult(
            kind="clarification",
            clarification=ClarificationRequest(
                required=True,
                question="No statement was provided. Please describe what you expect to happen.",
                missing_fields=["claim"],
                draft_expectation=draft_expectation,
            )
        )

    if _should_use_mock(mock_mode):
        return _mock_compile_expectation(
            user_text=user_text,
            conversation_history=conversation_history,
            draft_expectation=draft_expectation,
            expectation_id=expectation_id,
        )

    bedrock = BedrockClient()
    try:
        # Build contextual message payload for Amazon Bedrock Converse API
        prompt_parts = []
        if conversation_history:
            prompt_parts.append(f"Conversation history:\n{json.dumps(conversation_history, indent=2)}")
        if draft_expectation:
            prompt_parts.append(f"Draft expectation so far:\n{json.dumps(draft_expectation, indent=2)}")
        if expectation_id:
            prompt_parts.append(f"Target Expectation ID: {expectation_id}")
        prompt_parts.append(f"Current user statement: {user_text}")

        user_message = "\n\n".join(prompt_parts)

        raw_response = bedrock.invoke(
            system_prompt=EXPECTATION_COMPILER_SYSTEM_PROMPT,
            user_message=user_message,
            temperature=0.0
        )

        result = ExpectationCompilationResult.model_validate(raw_response)
        return result
    except (BedrockClientError, InvalidModelResponse) as err:
        raise ExpectationCompilationError(f"Expectation compilation failed: {str(err)}") from err
    except Exception as e:
        raise ExpectationCompilationError(f"Unexpected error during compilation: {str(e)}") from e
