"""
Unit tests for Amazon Account and Package Delivery Intelligence.
"""

import pytest
from app.ai.amazon_intelligence import (
    AmazonOrderContext,
    AmazonDeliveryPayload,
    extract_from_amazon_context,
    convert_amazon_to_evidence,
)
from app.ai.compiler import compile_expectation
from app.ai.investigator import investigate_mismatch
from app.ai.models.expectation import Expectation, EvaluationResult, Evidence


def test_extract_from_amazon_order_on_time():
    """Verify extracting delivery expectation for normal shipped order."""
    order = AmazonOrderContext(
        order_id="114-9876543-1234567",
        item_title="Wireless Noise Cancelling Headphones",
        status="out_for_delivery",
        expected_delivery_date="2026-10-12",
        carrier="Amazon Logistics",
        tracking_number="TBA1234567890",
    )
    payload = AmazonDeliveryPayload(
        order=order,
        user_statement="My headphones should arrive today",
        mock_mode=True,
    )

    result = extract_from_amazon_context(payload)
    assert result.success is True
    assert result.expectation is not None
    assert result.expectation.type == "delivery"
    assert result.expectation.metric == "delivery_status"
    assert "delivery" in result.expectation.evidence_sources
    assert result.is_delayed is False
    assert result.is_cancelled is False

    # Check evidence
    assert len(result.extracted_evidence) >= 2
    status_ev = next((e for e in result.extracted_evidence if e.metric == "delivery_status"), None)
    assert status_ev is not None
    assert status_ev.value == "out_for_delivery"


def test_extract_from_amazon_order_delayed():
    """Verify detecting and flagging delivery delays from carrier updates."""
    order = AmazonOrderContext(
        order_id="114-1111222-3333444",
        item_title="Espresso Coffee Machine",
        status="delayed",
        expected_delivery_date="2026-10-10",
        actual_delivery_date="2026-10-14",
        carrier="UPS",
        delay_reason="Package delayed due to severe weather conditions along transit route",
    )
    payload = AmazonDeliveryPayload(
        order=order,
        mock_mode=True,
    )

    result = extract_from_amazon_context(payload)
    assert result.success is True
    assert result.is_delayed is True
    assert result.is_cancelled is False
    assert "delayed" in result.summary.lower()
    assert result.expectation.status == "mismatch"


def test_extract_from_amazon_order_cancelled():
    """Verify detecting cancelled Amazon orders and shipments."""
    order = AmazonOrderContext(
        order_id="114-5555666-7777888",
        item_title="Mechanical Keyboard",
        status="cancelled",
        expected_delivery_date="2026-10-11",
        delay_reason="Order cancelled per customer request",
    )
    payload = AmazonDeliveryPayload(
        order=order,
        mock_mode=True,
    )

    result = extract_from_amazon_context(payload)
    assert result.success is True
    assert result.is_cancelled is True
    assert result.is_delayed is False
    assert "cancelled" in result.summary.lower()
    assert result.expectation.status == "mismatch"


def test_investigator_with_delivery_delay_evidence():
    """Verify Investigator explains delivery delays with carrier evidence."""
    exp = Expectation(
        claim="My package should arrive today",
        type="delivery",
        metric="delivery_status",
        comparison="exists",
        status="mismatch",
    )
    eval_res = EvaluationResult(
        result="MISMATCH",
        contradiction=True,
    )
    evidences = [
        Evidence(
            source="delivery",
            metric="delivery_status",
            value="delayed",
        )
    ]
    investigation = investigate_mismatch(exp, eval_res, evidences, mock_mode=True)
    assert investigation.explanation is not None
    assert "delayed in transit" in investigation.explanation.lower()
    assert investigation.confidence >= 0.9
    assert len(investigation.key_factors) >= 1


def test_investigator_with_delivery_cancellation_evidence():
    """Verify Investigator explains shipment cancellations with supporting evidence."""
    exp = Expectation(
        claim="My package should arrive today",
        type="delivery",
        metric="delivery_status",
        comparison="exists",
        status="mismatch",
    )
    eval_res = EvaluationResult(
        result="MISMATCH",
        contradiction=True,
    )
    evidences = [
        Evidence(
            source="delivery",
            metric="delivery_status",
            value="cancelled",
        )
    ]
    investigation = investigate_mismatch(exp, eval_res, evidences, mock_mode=True)
    assert investigation.explanation is not None
    assert "cancelled" in investigation.explanation.lower()
    assert investigation.confidence >= 0.9


def test_compiler_with_amazon_statements():
    """Verify compiler parses casual Amazon package statements."""
    statement = "My Amazon package delivery should arrive today"
    res = compile_expectation(statement, mock_mode=True)
    assert res.kind == "expectation"
    assert res.expectation is not None
    assert "delivery" in res.expectation.evidence_sources
    assert res.expectation.type == "delivery"
