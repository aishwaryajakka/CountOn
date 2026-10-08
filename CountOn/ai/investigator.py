"""
CountOn Investigator Implementation (Person 2 - Day 5)
"""

import os
import json
from typing import List, Optional, Dict, Any
from mycounton.ai.models.expectation import (
    Expectation,
    EvaluationResult,
    Evidence,
    InvestigationResult,
)
from mycounton.ai.bedrock_client import BedrockClient
from mycounton.ai.prompts import INVESTIGATOR_SYSTEM_PROMPT
from mycounton.ai.exceptions import (
    BedrockClientError,
    InvalidModelResponse,
    InvestigationError,
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


def _mock_investigate_mismatch(
    expectation: Expectation,
    evaluation_result: EvaluationResult,
    evidence: List[Evidence],
) -> InvestigationResult:
    """
    Day 5 Local Mock Investigator for offline testing without Bedrock credentials.
    Supports Scenario A (Hero), Scenario B (Insufficient), Scenario C (Multiple sources), Scenario D (Conflicting).
    """
    if not evidence:
        return InvestigationResult(
            explanation="I found that the result differed from your expectation, but the available evidence isn't sufficient to determine why.",
            key_factors=["Observed outcome contradicted expectation", "No supporting evidence provided"],
            confidence=0.3
        )

    sources = [e.source for e in evidence]
    metrics = {e.metric: e.value for e in evidence if e.metric}
    descriptions = [e.description for e in evidence if e.description]

    # Check for Hero Scenario: usage -18%, rate +22%, bill +14% / bill total cost
    usage_val = metrics.get("energy_usage") or metrics.get("usage_change_percent")
    rate_val = metrics.get("electricity_rate") or metrics.get("rate_change_percent")

    if usage_val is not None and rate_val is not None:
        return InvestigationResult(
            explanation="Your electricity usage decreased by 18%, but the electricity rate increased by 22%. The higher rate outweighed the reduction in usage, so your bill increased.",
            key_factors=[
                "Energy usage decreased by 18%",
                "Electricity rate increased by 22%",
                "Total bill increased"
            ],
            confidence=0.94
        )

    # Scenario D: Conflicting evidence
    is_conflicting = False
    if len(evidence) >= 2:
        vals = [e.value for e in evidence if isinstance(e.value, (int, float, str))]
        if "delivered" in str(vals).lower() and "failed" in str(vals).lower():
            is_conflicting = True

    if is_conflicting:
        return InvestigationResult(
            explanation="The available evidence contains conflicting reports regarding the delivery status, so a conclusive reason cannot be determined.",
            key_factors=["Conflicting evidence sources detected", "Delivery status discrepancy"],
            confidence=0.4
        )

    # Scenario C: Multiple supporting evidence sources (e.g. ring + delivery)
    if "delivery" in sources and "ring" in sources:
        return InvestigationResult(
            explanation="Delivery tracking confirmed the item arrived, and Ring door camera footage recorded parcel drop-off at your front door.",
            key_factors=["Delivery status confirmed by carrier", "Doorbell camera motion event logged"],
            confidence=0.95
        )

    # Scenario B fallback if evidence is minimal or insufficient to show root cause
    if len(evidence) == 1 and ("bill" in sources or "utility_bill" in sources) and not usage_val:
        return InvestigationResult(
            explanation="I found that the result differed from your expectation, but the available evidence isn't sufficient to determine why.",
            key_factors=["Bill total cost noted", "Insufficient detailed usage or rate breakdown"],
            confidence=0.35
        )

    # Generic evidence summary
    factors = [f"Source: {e.source}, value: {e.value}" for e in evidence[:3]]
    return InvestigationResult(
        explanation=f"Evaluation confirmed a contradiction. Evidence from {', '.join(sources)} shows observed values differed from the claimed expectation.",
        key_factors=factors,
        confidence=0.85
    )


def investigate_mismatch(
    expectation: Expectation,
    evaluation_result: EvaluationResult,
    evidence: List[Evidence],
    mock_mode: Optional[bool] = None,
) -> InvestigationResult:
    """
    Public Function: Investigates a confirmed MISMATCH evaluation result and generates an evidence-based explanation.

    MUST be called ONLY after Person 3's deterministic engine has confirmed a MISMATCH.

    Parameters:
        expectation: The target Expectation model.
        evaluation_result: Deterministic evaluation result from Person 3.
        evidence: List of normalized Evidence objects.
        mock_mode: Optional boolean to explicitly force mock vs Bedrock mode.
    """
    # Verify that the verdict is indeed a MISMATCH or contradiction
    if evaluation_result.result != "MISMATCH" and not evaluation_result.contradiction:
        raise InvestigationError(
            f"Investigator called on non-mismatch result: '{evaluation_result.result}'. "
            "Person 2 Investigator must only be invoked for confirmed MISMATCH outcomes."
        )

    if _should_use_mock(mock_mode):
        return _mock_investigate_mismatch(expectation, evaluation_result, evidence)

    # Real Amazon Bedrock Call
    bedrock = BedrockClient()

    # Construct input context for Bedrock prompt
    payload = {
        "expectation": expectation.model_dump(),
        "evaluation_result": evaluation_result.model_dump(),
        "evidence": [e.model_dump() for e in evidence],
    }

    user_message = f"Explain this confirmed mismatch based strictly on the provided data:\n\n{json.dumps(payload, indent=2)}"

    try:
        raw_response = bedrock.invoke(
            system_prompt=INVESTIGATOR_SYSTEM_PROMPT,
            user_message=user_message,
            temperature=0.0,
        )

        result = InvestigationResult.model_validate(raw_response)
        return result
    except (BedrockClientError, InvalidModelResponse) as err:
        raise InvestigationError(f"Mismatch investigation failed: {str(err)}") from err
    except Exception as e:
        raise InvestigationError(f"Unexpected error during mismatch investigation: {str(e)}") from e
