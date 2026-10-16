"""
Amazon Account & Delivery Intelligence for CountOn.
Tracks package deliveries, detects carrier delays, cancellations, and missed delivery windows.
"""

import os
import json
from typing import Optional, List, Literal, Any
from pydantic import BaseModel, Field

from app.ai.models.expectation import Expectation, Evidence
from app.ai.bedrock_client import BedrockClient
from app.ai.prompts import AMAZON_DELIVERY_INTELLIGENCE_SYSTEM_PROMPT


class AmazonOrderContext(BaseModel):
    """Represents an Amazon order or delivery item."""
    order_id: str = Field(..., description="Amazon order identifier e.g. 114-1234567-8901234")
    item_title: str = Field(..., description="Description or title of the purchased item")
    status: Literal["ordered", "shipped", "out_for_delivery", "delivered", "delayed", "cancelled", "returned"] = Field(
        default="shipped",
        description="Current shipment lifecycle status",
    )
    expected_delivery_date: Optional[str] = Field(default=None, description="Original estimated delivery date or ISO string")
    actual_delivery_date: Optional[str] = Field(default=None, description="Actual delivered date or updated revised date")
    carrier: Optional[str] = Field(default="Amazon Logistics", description="Carrier name e.g. Amazon Logistics, UPS, FedEx")
    tracking_number: Optional[str] = Field(default=None, description="Shipment tracking identifier")
    delay_reason: Optional[str] = Field(default=None, description="Carrier reason if delayed or rescheduled")


class AmazonDeliveryPayload(BaseModel):
    """Input payload containing Amazon order status and shipment context."""
    order: AmazonOrderContext
    user_statement: Optional[str] = Field(default=None, description="Optional user statement like 'My package should arrive today'")
    mock_mode: Optional[bool] = None


class AmazonExtractionResult(BaseModel):
    """Result of analyzing Amazon delivery context."""
    success: bool = True
    expectation: Optional[Expectation] = None
    extracted_evidence: List[Evidence] = Field(default_factory=list)
    summary: str = Field(..., description="Human-readable explanation of delivery status")
    is_delayed: bool = Field(default=False, description="True if shipment is delayed beyond original expected date")
    is_cancelled: bool = Field(default=False, description="True if order or shipment was cancelled")
    is_delivered: bool = Field(default=False, description="True if successfully delivered")
    confidence: float = Field(default=0.95, ge=0.0, le=1.0)


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


def convert_amazon_to_evidence(
    payload: AmazonDeliveryPayload,
    expectation_id: Optional[str] = None,
) -> List[Evidence]:
    """
    Normalizes Amazon order and shipment tracking into CountOn Evidence objects.
    """
    evidences: List[Evidence] = []
    ord_ctx = payload.order

    # Delivery status evidence
    evidences.append(
        Evidence(
            expectation_id=expectation_id,
            source="delivery",
            metric="delivery_status",
            value=ord_ctx.status,
            description=f"Amazon order {ord_ctx.order_id} ({ord_ctx.item_title}) status: {ord_ctx.status}",
            confidence=1.0,
        )
    )

    # Carrier & tracking details
    evidences.append(
        Evidence(
            expectation_id=expectation_id,
            source="delivery",
            metric="package_tracking",
            value={
                "order_id": ord_ctx.order_id,
                "carrier": ord_ctx.carrier,
                "expected": ord_ctx.expected_delivery_date,
                "actual": ord_ctx.actual_delivery_date,
                "delay_reason": ord_ctx.delay_reason,
            },
            description=f"Tracking details for {ord_ctx.item_title} via {ord_ctx.carrier}",
            confidence=1.0,
        )
    )

    return evidences


def _mock_extract_amazon(payload: AmazonDeliveryPayload) -> AmazonExtractionResult:
    """
    Rule-based mock analyzer for Amazon orders and delivery anomalies.
    """
    ord_ctx = payload.order
    evidences = convert_amazon_to_evidence(payload)

    is_delayed = ord_ctx.status == "delayed"
    is_cancelled = ord_ctx.status == "cancelled"
    is_delivered = ord_ctx.status == "delivered"

    claim = payload.user_statement or f"My package for '{ord_ctx.item_title}' should arrive as promised"
    deadline = ord_ctx.expected_delivery_date or "today"

    exp = Expectation(
        claim=claim,
        type="delivery",
        metric="delivery_status",
        comparison="exists",
        deadline=deadline,
        evidence_sources=["delivery", "ring"],
        status="monitoring" if not (is_delivered or is_cancelled or is_delayed) else (
            "fulfilled" if is_delivered else "mismatch"
        ),
    )

    if is_delayed:
        summary = f"Amazon order {ord_ctx.order_id} ({ord_ctx.item_title}) is delayed by {ord_ctx.carrier}. Reason: {ord_ctx.delay_reason or 'Severe weather / transit delay'}."
    elif is_cancelled:
        summary = f"Amazon order {ord_ctx.order_id} ({ord_ctx.item_title}) has been cancelled."
    elif is_delivered:
        summary = f"Amazon order {ord_ctx.order_id} ({ord_ctx.item_title}) has been successfully delivered."
    else:
        summary = f"Amazon order {ord_ctx.order_id} ({ord_ctx.item_title}) is currently {ord_ctx.status} with expected delivery {deadline}."

    return AmazonExtractionResult(
        success=True,
        expectation=exp,
        extracted_evidence=evidences,
        summary=summary,
        is_delayed=is_delayed,
        is_cancelled=is_cancelled,
        is_delivered=is_delivered,
        confidence=0.96,
    )


def extract_from_amazon_context(
    payload: AmazonDeliveryPayload,
) -> AmazonExtractionResult:
    """
    Main entry point: Analyzes Amazon order status, shipment updates, and detects delivery mismatches.
    """
    if _should_use_mock(payload.mock_mode):
        return _mock_extract_amazon(payload)

    bedrock = BedrockClient()
    user_message = f"Extract delivery expectation and evidence from this Amazon order context:\n\n{payload.model_dump_json(indent=2)}"

    try:
        raw_response = bedrock.invoke(
            system_prompt=AMAZON_DELIVERY_INTELLIGENCE_SYSTEM_PROMPT,
            user_message=user_message,
            temperature=0.0,
        )
        result = AmazonExtractionResult.model_validate(raw_response)
        if not result.extracted_evidence:
            result.extracted_evidence = convert_amazon_to_evidence(payload)
        return result
    except Exception as e:
        mock_result = _mock_extract_amazon(payload)
        mock_result.summary += f" (Fallback mode: {str(e)})"
        return mock_result
