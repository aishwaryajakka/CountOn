"""API endpoints for Human Review, Benchmark Latency & Cost, and Recommendations."""

from typing import Annotated
from uuid import UUID
from fastapi import APIRouter, Depends, Query, HTTPException, status as http_status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_db
from app.schemas.human_review import HumanReviewItem, ReviewStatus, ReviewActionPayload
from app.schemas.recommendation import (
    RecommendationBase,
    RecommendationResponse,
    RecommendationStatus,
    RecommendationApprovalRequest,
)
from app.services import human_review_service, recommendation_service
from app.ai.benchmark_suite import run_compiler_benchmark, BenchmarkReport

router = APIRouter(prefix="/quality", tags=["quality"])
Database = Annotated[Session, Depends(get_db)]


# ============================================================================
# 1. Human Review & Bedrock Verification Endpoints
# ============================================================================

@router.get("/reviews", response_model=list[HumanReviewItem], summary="List Bedrock model outputs for human review")
def list_human_reviews(
    status: ReviewStatus | None = Query(default=None),
) -> list[HumanReviewItem]:
    return human_review_service.list_reviews(status=status)


@router.get("/reviews/{review_id}", response_model=HumanReviewItem, summary="Get details of a specific human review item")
def get_human_review(review_id: UUID) -> HumanReviewItem:
    item = human_review_service.get_review(review_id)
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found")
    return item


@router.post("/reviews/{review_id}/decide", response_model=HumanReviewItem, summary="Submit human verdict on Bedrock output")
def submit_review_decision(
    review_id: UUID,
    payload: ReviewActionPayload,
) -> HumanReviewItem:
    updated = human_review_service.submit_review_decision(review_id, payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Review item not found")
    return updated


# ============================================================================
# 2. Latency & Cost Benchmarking Suite
# ============================================================================

@router.post("/benchmark", summary="Run latency and cost benchmark across representative requests")
def benchmark_requests(
    mock_mode: bool = Query(default=False, description="Use real Bedrock or mock AI"),
) -> dict:
    representative_queries = [
        "My electric bill should be under $150",
        "My rent should not exceed $2000",
        "My Amazon package should arrive by Thursday 6pm",
        "Subscription for Netflix should remain $15.49 monthly",
        "Refund from Target should be credited by Monday",
    ]
    report: BenchmarkReport = run_compiler_benchmark(
        queries=representative_queries,
        mock_mode=mock_mode,
    )
    return report.to_dict()


# ============================================================================
# 3. Structured Recommendations & User Approval Workflow
# ============================================================================

@router.get("/recommendations", response_model=list[RecommendationResponse], summary="List candidate recommendations")
def list_recommendations(
    status: RecommendationStatus | None = Query(default=None),
) -> list[RecommendationResponse]:
    return recommendation_service.list_recommendations(status=status)


@router.post("/recommendations", response_model=RecommendationResponse, status_code=http_status.HTTP_201_CREATED, summary="Propose a new recommendation")
def create_recommendation(data: RecommendationBase) -> RecommendationResponse:
    return recommendation_service.create_recommendation(data)


@router.post("/recommendations/{rec_id}/approval", response_model=RecommendationResponse, summary="Approve or reject a recommendation into an active expectation")
def decide_recommendation(
    rec_id: UUID,
    payload: RecommendationApprovalRequest,
    db: Database,
    user: CurrentUser,
) -> RecommendationResponse:
    result = recommendation_service.process_approval(
        db=db,
        rec_id=rec_id,
        user_id=user.id,
        payload=payload,
    )
    if not result:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    return result
