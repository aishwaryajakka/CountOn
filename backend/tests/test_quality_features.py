"""Tests for Quality API: Human Review, Latency & Cost Benchmark, and Recommendations."""

from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.human_review import ReviewStatus
from app.schemas.recommendation import (
    RecommendationBase,
    RecommendationCategory,
    RecommendationStatus,
    SourceReference,
)
from app.db.models.expectation import ComparisonType, ExpectationType

client = TestClient(app)


def test_list_human_reviews():
    response = client.get("/api/v1/quality/reviews")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 3
    assert any("electric bill" in item["input_text"] for item in data)


def test_submit_human_review_decision():
    # First get all reviews
    response = client.get("/api/v1/quality/reviews")
    assert response.status_code == 200
    reviews = response.json()
    first_id = reviews[0]["id"]

    # Submit human decision
    payload = {
        "status": "verified",
        "reviewer_notes": "Grounding and metric match verified manually.",
        "reviewer_verdict": "accurate_numeric_extraction",
    }
    decide_resp = client.post(f"/api/v1/quality/reviews/{first_id}/decide", json=payload)
    assert decide_resp.status_code == 200
    updated = decide_resp.json()
    assert updated["status"] == "verified"
    assert updated["reviewer_notes"] == payload["reviewer_notes"]


def test_run_benchmark():
    response = client.post("/api/v1/quality/benchmark?mock_mode=true")
    assert response.status_code == 200
    data = response.json()
    assert data["total_requests"] == 5
    assert data["successful_requests"] == 5
    assert "latency" in data
    assert "cost" in data
    assert data["latency"]["avg_ms"] >= 0
    assert data["cost"]["total_usd"] >= 0
    assert len(data["samples"]) == 5


def test_list_and_create_recommendations():
    # List initial seeded recommendations
    response = client.get("/api/v1/quality/recommendations")
    assert response.status_code == 200
    recs = response.json()
    assert len(recs) >= 2
    assert any(r["confidence"] >= 0.9 for r in recs)

    # Propose new recommendation
    new_rec = {
        "title": "Water Utility Cap",
        "claim": "Water bill should be under $85.00",
        "category": "billing",
        "type": "numeric_comparison",
        "metric": "water_bill",
        "comparison": "less_than",
        "baseline": 85.0,
        "deadline": None,
        "evidence_sources": ["utility_bill"],
        "confidence": 0.94,
        "source_references": [
            {
                "provider": "utility",
                "source_id": "water-918",
                "snippet": "Normal usage is 600 gallons.",
            }
        ],
        "rationale": "Extracted from city municipal water statement.",
    }
    create_resp = client.post("/api/v1/quality/recommendations", json=new_rec)
    assert create_resp.status_code == 201
    created = create_resp.json()
    assert created["title"] == "Water Utility Cap"
    assert created["status"] == "pending_approval"
    assert created["confidence"] == 0.94
