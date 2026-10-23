"""Authenticated demo-only Ring and Bee evidence ingestion."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_db
from app.core.exceptions import InvalidExpectationError
from app.integrations.bee.adapter import bee_event_to_evidence
from app.integrations.ring.adapter import ring_event_to_evidence
from app.schemas.evaluation import EvaluationResponse
from app.schemas.evidence import EvidenceResponse
from app.services import evaluation_service, evidence_service
from app.services.expectation_service import get_expectation

router = APIRouter(prefix="/simulators", tags=["simulators"])
Database = Annotated[Session, Depends(get_db)]


class RingEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    simulated: Literal[True]
    event_id: str = Field(pattern=r"^ring_sim_[A-Za-z0-9-]{8,100}$")
    kind: Literal["package_detected", "package_not_detected", "doorbell_ding", "motion_detected"]
    device: str = Field(min_length=1, max_length=100)
    timestamp: AwareDatetime
    confidence: float = Field(ge=0, le=1)
    metric: str | None = Field(default=None, min_length=1, max_length=100)


class BeeEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    simulated: Literal[True]
    id: str = Field(pattern=r"^bee_sim_[A-Za-z0-9-]{8,100}$")
    type: Literal["conversation", "note", "commitment"]
    speaker: str = Field(min_length=1, max_length=100)
    summary: str = Field(min_length=1, max_length=1000)
    start_time: AwareDatetime
    confidence: float = Field(default=0.85, ge=0, le=1)
    metric: str | None = Field(default=None, min_length=1, max_length=100)
    confirmed: bool | None = None


class SimulationResult(BaseModel):
    evidence: EvidenceResponse
    evaluation: EvaluationResponse


def ingest(db, user_id, expectation_id, raw, kind):
    expectation = get_expectation(db, expectation_id, user_id)
    required = f"{kind}_simulator"
    if required not in expectation.evidence_sources:
        raise InvalidExpectationError(f"Confirm {kind.title()} simulator as an evidence source before submitting demo evidence")
    evidence = (ring_event_to_evidence if kind == "ring" else bee_event_to_evidence)(raw)
    if evidence is None or evidence.source != required:
        raise InvalidExpectationError("Simulator event is invalid")
    saved = evidence_service.add_evidence(db, expectation_id, evidence, user_id)
    evaluation = evaluation_service.evaluate_expectation(db, expectation_id, user_id, idempotency_key=f"simulation:{saved.external_event_id}")
    return {"evidence": saved, "evaluation": evaluation}


@router.post("/ring/expectations/{expectation_id}/events", response_model=SimulationResult)
def ring(expectation_id: UUID, payload: RingEvent, db: Database, user: CurrentUser):
    return ingest(db, user.id, expectation_id, payload.model_dump(mode="json"), "ring")


@router.post("/bee/expectations/{expectation_id}/events", response_model=SimulationResult)
def bee(expectation_id: UUID, payload: BeeEvent, db: Database, user: CurrentUser):
    return ingest(db, user.id, expectation_id, payload.model_dump(mode="json"), "bee")
