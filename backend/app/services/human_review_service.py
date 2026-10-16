"""Service for managing Bedrock Human-in-the-Loop reviews and Verification records."""

from datetime import datetime
from uuid import UUID, uuid4
from typing import Any

from app.schemas.human_review import HumanReviewItem, ReviewStatus, ReviewActionPayload

# In-memory store for human reviews, seeded with standard verification test items
_REVIEW_STORE: dict[UUID, HumanReviewItem] = {}


def seed_default_reviews_if_empty() -> None:
    if _REVIEW_STORE:
        return

    # Seed baseline representative examples for human review
    examples = [
        {
            "input_text": "My electric bill should be under $150",
            "model_output": {
                "claim": "electric bill under $150",
                "type": "numeric_comparison",
                "metric": "electric bill",
                "comparison": "less_than",
                "baseline": 150.0,
                "evidence_sources": ["utility_bill"],
                "status": "monitoring",
            },
            "expected_output": {
                "metric": "electric bill",
                "comparison": "less_than",
                "baseline": 150.0,
            },
            "latency_ms": 1420.5,
        },
        {
            "input_text": "My Amazon package should arrive by Friday 5pm",
            "model_output": {
                "claim": "Amazon package arrive by Friday 5pm",
                "type": "temporal",
                "metric": "delivery_status",
                "deadline": "2026-10-16T17:00:00Z",
                "evidence_sources": ["delivery"],
            },
            "expected_output": {
                "type": "temporal",
                "metric": "delivery_status",
            },
            "latency_ms": 1850.2,
        },
        {
            "input_text": "I expect my grocery refund of $42.50 within 3 days",
            "model_output": {
                "claim": "grocery refund of $42.50 within 3 days",
                "type": "numeric_comparison",
                "metric": "refund_amount",
                "comparison": "equal",
                "baseline": 42.50,
                "evidence_sources": ["billing", "email"],
            },
            "expected_output": {
                "type": "numeric_comparison",
                "baseline": 42.50,
            },
            "latency_ms": 1620.0,
        },
    ]

    for item in examples:
        rev_id = uuid4()
        _REVIEW_STORE[rev_id] = HumanReviewItem(
            id=rev_id,
            input_text=item["input_text"],
            model_output=item["model_output"],
            expected_output=item["expected_output"],
            status=ReviewStatus.PENDING,
            latency_ms=item["latency_ms"],
        )


def list_reviews(status: ReviewStatus | None = None) -> list[HumanReviewItem]:
    seed_default_reviews_if_empty()
    reviews = list(_REVIEW_STORE.values())
    if status:
        reviews = [r for r in reviews if r.status == status]
    return sorted(reviews, key=lambda x: x.created_at, reverse=True)


def get_review(review_id: UUID) -> HumanReviewItem | None:
    seed_default_reviews_if_empty()
    return _REVIEW_STORE.get(review_id)


def record_review_item(
    input_text: str,
    model_output: dict[str, Any],
    expected_output: dict[str, Any] | None = None,
    latency_ms: float | None = None,
) -> HumanReviewItem:
    seed_default_reviews_if_empty()
    rev_id = uuid4()
    item = HumanReviewItem(
        id=rev_id,
        input_text=input_text,
        model_output=model_output,
        expected_output=expected_output,
        status=ReviewStatus.PENDING,
        latency_ms=latency_ms,
    )
    _REVIEW_STORE[rev_id] = item
    return item


def submit_review_decision(
    review_id: UUID,
    payload: ReviewActionPayload,
) -> HumanReviewItem | None:
    seed_default_reviews_if_empty()
    item = _REVIEW_STORE.get(review_id)
    if not item:
        return None

    item.status = payload.status
    item.reviewer_notes = payload.reviewer_notes
    item.reviewer_verdict = payload.reviewer_verdict
    item.reviewed_at = datetime.utcnow()
    _REVIEW_STORE[review_id] = item
    return item
