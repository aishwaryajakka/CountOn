"""
Unit tests for Continuous Monitoring & Automated Event Trigger Service.
"""

from uuid import uuid4
from unittest.mock import MagicMock, patch
import pytest

from app.db.models import Expectation, ExpectationStatus, ExpectationType
from app.db.models.operations import Notification
from app.evaluators.base import EvaluationOutput, EvaluationResult as EvaluatorResult
from app.services.monitoring_service import (
    trigger_account_event,
    run_continuous_monitoring_sweep,
    MonitoringEventResult,
)


def test_monitoring_event_result_to_dict():
    exp_id = uuid4()
    notif_id = uuid4()
    res = MonitoringEventResult(
        expectation_id=exp_id,
        provider="amazon",
        event_type="delivery_delayed",
        evaluation_result="MISMATCH",
        mismatch_detected=True,
        evidence_created=2,
        summary="Package delayed in transit",
        notification_id=notif_id,
    )
    d = res.to_dict()
    assert d["expectation_id"] == str(exp_id)
    assert d["provider"] == "amazon"
    assert d["evaluation_result"] == "MISMATCH"
    assert d["mismatch_detected"] is True
    assert d["evidence_created"] == 2
    assert d["notification_id"] == str(notif_id)


@patch("app.services.monitoring_service.evaluation_service.evaluate_expectation")
@patch("app.services.monitoring_service.evidence_repository.create_evidence")
@patch("app.services.monitoring_service.expectation_service.create_expectation")
def test_trigger_account_event_amazon_delivery(mock_create_exp, mock_create_ev, mock_eval):
    """Verify triggering an Amazon delivery event ingests evidence and runs evaluation."""
    db = MagicMock()
    user_id = uuid4()
    exp_id = uuid4()

    mock_exp = Expectation(
        id=exp_id,
        user_id=user_id,
        claim="My headphones should arrive today",
        type=ExpectationType.event,
        metric="delivery_status",
        status=ExpectationStatus.monitoring,
    )
    # No existing expectation found in query -> creates one
    db.scalars.return_value = []
    mock_create_exp.return_value = mock_exp

    # Evaluation returns MATCH
    mock_evaluation = MagicMock()
    mock_evaluation.result.value = "MATCH"
    mock_eval.return_value = mock_evaluation

    payload = {
        "order": {
            "order_id": "114-1234567-8901234",
            "item_title": "Wireless Headphones",
            "status": "delivered",
            "expected_delivery_date": "2026-10-12",
        },
        "mock_mode": True,
    }

    result = trigger_account_event(
        db=db,
        user_id=user_id,
        provider="amazon",
        event_type="package_delivered",
        payload=payload,
        mock_mode=True,
    )

    assert result.expectation_id == exp_id
    assert result.provider == "amazon"
    assert result.evaluation_result == "MATCH"
    assert result.mismatch_detected is False
    assert result.evidence_created >= 1
    assert mock_create_ev.called
    assert mock_eval.called


@patch("app.services.monitoring_service.investigator_service.investigate_expectation_mismatch")
@patch("app.services.monitoring_service.evaluation_service.evaluate_expectation")
@patch("app.services.monitoring_service.evidence_repository.create_evidence")
def test_trigger_account_event_with_mismatch_and_proactive_investigation(mock_create_ev, mock_eval, mock_investigate):
    """Verify that when a delay/cancellation is triggered, Bedrock Investigator explains why and enriches the notification."""
    db = MagicMock()
    user_id = uuid4()
    exp_id = uuid4()

    existing_exp = Expectation(
        id=exp_id,
        user_id=user_id,
        claim="My package should arrive today",
        type=ExpectationType.event,
        metric="delivery_status",
        status=ExpectationStatus.monitoring,
        evidence_sources=["delivery"],
    )
    # Existing expectation found in query
    db.scalars.return_value = [existing_exp]

    # Evaluation returns MISMATCH
    mock_evaluation = MagicMock()
    mock_evaluation.result.value = "MISMATCH"
    mock_eval.return_value = mock_evaluation

    # Mock notification
    mock_notification = Notification(
        id=uuid4(),
        expectation_id=exp_id,
        user_id=user_id,
        message="Initial message",
        notification_metadata={},
    )
    db.scalar.return_value = mock_notification

    # Mock investigation result
    mock_inv_result = MagicMock()
    mock_inv_result.explanation = "Your package delivery was delayed in transit by the carrier beyond the promised window."
    mock_inv_result.key_factors = ["Carrier transit delay logged"]
    mock_inv_result.confidence = 0.95
    mock_inv_result.model_dump.return_value = {
        "explanation": mock_inv_result.explanation,
        "key_factors": mock_inv_result.key_factors,
        "confidence": 0.95,
    }
    mock_investigate.return_value = mock_inv_result

    payload = {
        "order": {
            "order_id": "114-9999999-0000000",
            "item_title": "Espresso Machine",
            "status": "delayed",
            "delay_reason": "Severe weather",
        },
        "mock_mode": True,
    }

    result = trigger_account_event(
        db=db,
        user_id=user_id,
        provider="amazon",
        event_type="delivery_delayed",
        payload=payload,
        mock_mode=True,
    )

    assert result.mismatch_detected is True
    assert result.evaluation_result == "MISMATCH"
    assert result.investigation is not None
    assert "delayed" in result.investigation.explanation.lower()
    # Notification was enriched
    assert "Mismatch Detected" in mock_notification.message
    assert mock_notification.notification_metadata.get("confidence") == 0.95


@patch("app.services.monitoring_service.evaluation_service.evaluate_expectation")
def test_run_continuous_monitoring_sweep(mock_eval):
    """Verify running continuous monitoring cycle sweeps all active expectations."""
    db = MagicMock()
    user_id = uuid4()

    exp1 = Expectation(id=uuid4(), user_id=user_id, status=ExpectationStatus.monitoring)
    exp2 = Expectation(id=uuid4(), user_id=user_id, status=ExpectationStatus.monitoring)
    db.scalars.return_value = [exp1, exp2]

    eval_match = MagicMock()
    eval_match.result.value = "MATCH"
    eval_mismatch = MagicMock()
    eval_mismatch.result.value = "MISMATCH"
    mock_eval.side_effect = [eval_match, eval_mismatch]

    sweep_res = run_continuous_monitoring_sweep(db, user_id, mock_mode=True)
    assert sweep_res["status"] == "completed"
    assert sweep_res["total_active"] == 2
    assert sweep_res["evaluated"] == 2
    assert sweep_res["matches"] == 1
    assert sweep_res["mismatches"] == 1
