"""Service for generating structured recommendations with confidence and user approval."""

from datetime import datetime
from uuid import UUID, uuid4
from typing import Any
from sqlalchemy.orm import Session

from app.db.models.expectation import ComparisonType, ExpectationType
from app.schemas.expectation import ExpectationCreate
from app.schemas.recommendation import (
    RecommendationBase,
    RecommendationCategory,
    RecommendationResponse,
    RecommendationStatus,
    SourceReference,
    RecommendationApprovalRequest,
)
from app.services import expectation_service

# In-memory recommendation registry for unapproved recommendations
_RECOMMENDATIONS: dict[UUID, RecommendationResponse] = {}


def seed_default_recommendations_if_empty() -> None:
    if _RECOMMENDATIONS:
        return

    rec1_id = uuid4()
    _RECOMMENDATIONS[rec1_id] = RecommendationResponse(
        id=rec1_id,
        title="Pacific Gas & Electric Monthly Budget",
        claim="My electric bill should stay under $145.00 this cycle",
        category=RecommendationCategory.BILLING,
        type=ExpectationType.numeric_comparison,
        metric="electric_bill",
        comparison=ComparisonType.less_than_or_equal,
        baseline=145.0,
        deadline=None,
        evidence_sources=["utility_bill"],
        confidence=0.96,
        source_references=[
            SourceReference(
                provider="utility",
                source_id="pge-statement-9842",
                snippet="Previous 3 statements averaged $138.20. Projected next bill: $144.10",
                timestamp=datetime.utcnow(),
            )
        ],
        rationale="Calculated from your historical utility statement average with a 5% comfort buffer.",
        status=RecommendationStatus.PENDING_APPROVAL,
    )

    rec2_id = uuid4()
    _RECOMMENDATIONS[rec2_id] = RecommendationResponse(
        id=rec2_id,
        title="Amazon Package Arrival Tracking",
        claim="Ergonomic Keyboard package should arrive by Thursday 6pm",
        category=RecommendationCategory.DELIVERY,
        type=ExpectationType.temporal,
        metric="package_delivery",
        comparison=ComparisonType.less_than_or_equal,
        baseline=None,
        deadline=datetime.utcnow(),
        evidence_sources=["delivery", "amazon"],
        confidence=0.92,
        source_references=[
            SourceReference(
                provider="amazon",
                source_id="114-8923412-984112",
                snippet="Shipped via UPS Ground: Estimated delivery Thursday by 6:00 PM.",
                timestamp=datetime.utcnow(),
            )
        ],
        rationale="Extracted shipping confirmation email from Amazon Logistics.",
        status=RecommendationStatus.PENDING_APPROVAL,
    )


def list_recommendations(status: RecommendationStatus | None = None) -> list[RecommendationResponse]:
    seed_default_recommendations_if_empty()
    recs = list(_RECOMMENDATIONS.values())
    if status:
        recs = [r for r in recs if r.status == status]
    return sorted(recs, key=lambda x: x.created_at, reverse=True)


def get_recommendation(rec_id: UUID) -> RecommendationResponse | None:
    seed_default_recommendations_if_empty()
    return _RECOMMENDATIONS.get(rec_id)


def create_recommendation(data: RecommendationBase) -> RecommendationResponse:
    seed_default_recommendations_if_empty()
    rec_id = uuid4()
    rec = RecommendationResponse(
        id=rec_id,
        title=data.title,
        claim=data.claim,
        category=data.category,
        type=data.type,
        metric=data.metric,
        comparison=data.comparison,
        baseline=data.baseline,
        target_value=data.target_value,
        deadline=data.deadline,
        evidence_sources=data.evidence_sources,
        confidence=data.confidence,
        source_references=data.source_references,
        rationale=data.rationale,
        status=RecommendationStatus.PENDING_APPROVAL,
    )
    _RECOMMENDATIONS[rec_id] = rec
    return rec


def process_approval(
    db: Session,
    rec_id: UUID,
    user_id: UUID,
    payload: RecommendationApprovalRequest,
) -> RecommendationResponse | None:
    seed_default_recommendations_if_empty()
    rec = _RECOMMENDATIONS.get(rec_id)
    if not rec:
        return None

    rec.status = payload.action
    rec.reviewed_at = datetime.utcnow()

    # When user APPROVES, convert it to an active Expectation in the database!
    if payload.action == RecommendationStatus.APPROVED:
        exp_create = ExpectationCreate(
            claim=rec.claim,
            type=rec.type,
            metric=rec.metric,
            comparison=rec.comparison,
            baseline=payload.custom_baseline if payload.custom_baseline is not None else rec.baseline,
            target_value=rec.target_value,
            deadline=payload.custom_deadline if payload.custom_deadline is not None else rec.deadline,
            evidence_sources=rec.evidence_sources,
            materiality_threshold=0.05,
        )
        created_exp = expectation_service.create_expectation(db, exp_create, user_id)
        rec.created_expectation_id = created_exp.id

    _RECOMMENDATIONS[rec_id] = rec
    return rec
