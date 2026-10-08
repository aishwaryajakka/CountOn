"""
Expectation Compiler Implementation
"""

import os
from typing import Optional
from app.ai.models.expectation import (
    Expectation,
    ClarificationRequest,
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


def _mock_compile_expectation(user_text: str) -> ExpectationCompilationResult:
    """
    Local Rule-Based Mock Compiler for offline testing.
    """
    text = user_text.strip()
    lowered = text.lower()

    if not text:
        return ExpectationCompilationResult(
            kind="clarification",
            clarification=ClarificationRequest(
                required=True,
                question="No statement was provided. Please describe what you expect to happen.",
                missing_fields=["claim", "deadline", "metric"]
            )
        )

    if lowered in ["my bill should be lower.", "my bill should be lower", "bill should be lower"]:
        return ExpectationCompilationResult(
            kind="clarification",
            clarification=ClarificationRequest(
                required=True,
                question="Could you specify which bill (e.g. electricity, gas) and when you expect it to be lower?",
                missing_fields=["deadline", "metric", "baseline"]
            )
        )

    if "soon" in lowered and "package" in lowered:
        return ExpectationCompilationResult(
            kind="clarification",
            clarification=ClarificationRequest(
                required=True,
                question="Could you specify an expected delivery date or timeframe instead of 'soon'?",
                missing_fields=["deadline"]
            )
        )

    if "ac" in lowered and "bill" in lowered:
        return ExpectationCompilationResult(
            kind="expectation",
            expectation=Expectation(
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
                claim=user_text,
                type="conversation_commitment",
                comparison="exists",
                deadline=None,
                evidence_sources=["conversation_context", "bee"],
                status="monitoring"
            )
        )

    if "lower" in lowered or "less" in lowered:
        comp = "less_than"
    elif "higher" in lowered or "more" in lowered:
        comp = "greater_than"
    else:
        comp = "exists"

    return ExpectationCompilationResult(
        kind="expectation",
        expectation=Expectation(
            claim=user_text,
            type="numeric_comparison" if "lower" in lowered or "higher" in lowered else "event_occurrence",
            comparison=comp,
            deadline="upcoming",
            evidence_sources=["external_api"],
            status="monitoring"
        )
    )


def compile_expectation(
    user_text: str,
    mock_mode: Optional[bool] = None
) -> ExpectationCompilationResult:
    """
    Public Function: Converts casual natural language user statements into a structured Expectation or ClarificationRequest.
    """
    if not user_text or not user_text.strip():
        return ExpectationCompilationResult(
            kind="clarification",
            clarification=ClarificationRequest(
                required=True,
                question="No statement was provided. Please describe what you expect to happen.",
                missing_fields=["claim"]
            )
        )

    if _should_use_mock(mock_mode):
        return _mock_compile_expectation(user_text)

    bedrock = BedrockClient()
    try:
        raw_response = bedrock.invoke(
            system_prompt=EXPECTATION_COMPILER_SYSTEM_PROMPT,
            user_message=user_text,
            temperature=0.0
        )
        
        result = ExpectationCompilationResult.model_validate(raw_response)
        return result
    except (BedrockClientError, InvalidModelResponse) as err:
        raise ExpectationCompilationError(f"Expectation compilation failed: {str(err)}") from err
    except Exception as e:
        raise ExpectationCompilationError(f"Unexpected error during compilation: {str(e)}") from e
