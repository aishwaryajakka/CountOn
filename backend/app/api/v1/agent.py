"""Authenticated utterance-only boundary; no client plans, tools or trusted state."""

import re
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from sqlalchemy.orm import Session

from app.agent.adapters import (
    CapabilityAdapter,
    CountOnMcpAdapter,
    StreamableMcpAdapter,
)
from app.agent.models import AgentInput
from app.agent.orchestrator import AgentOrchestrator
from app.agent.session import AgentSessionStore
from app.agent.trust import SENSITIVE
from app.api.dependencies import CurrentUser, bearer
from app.core.config import get_settings
from app.core.exceptions import AuthenticationError
from app.db.models.expectation import Expectation
from app.db.session import get_db
from app.evaluators.base import EvaluationResult
from app.mcp.schemas import ExpectationResult
from app.schemas.compiler import CompileContext
from app.schemas.trust import EvidenceSource
from app.services.agent_audit import record_run

router = APIRouter(prefix="/agent", tags=["agent"])


class ConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    text: str = Field(min_length=1, max_length=2000, repr=False)
    session_reference: SecretStr | None = Field(default=None, repr=False, max_length=43)
    expectation_id: UUID | None = None

    @field_validator("text")
    @classmethod
    def normalized_text(cls, value: str) -> str:
        return AgentInput.nonempty_text(value)


class PublicTrace(BaseModel):
    layer: str
    label: str


class ConversationResponse(BaseModel):
    action: str
    status: str
    answer: str
    code: str | None
    session_reference: str | None = Field(repr=False)
    captured: bool
    clarification_required: bool
    rows: list[ExpectationResult]
    saved_id: UUID | None
    traces: list[PublicTrace]
    provenance: "PublicProvenance"


class PublicProvenance(BaseModel):
    run_id: UUID
    expectation_label: str | None
    evaluator_result: EvaluationResult | None
    sources_used: list[EvidenceSource]
    evidence_count: int
    bedrock_used: bool
    fallback_used: bool
    grounded: bool


def remote_adapter(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> CapabilityAdapter:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError()  # type: ignore[no-untyped-call]
    settings = get_settings()
    if settings.mcp_public_url:
        return StreamableMcpAdapter(settings, SecretStr(credentials.credentials))
    return CountOnMcpAdapter()


@router.post("/converse", response_model=ConversationResponse)
async def converse(
    body: ConversationRequest,
    user: CurrentUser,
    request: Request,
    response: Response,
    adapter: Annotated[CapabilityAdapter, Depends(remote_adapter)],
    db: Annotated[Session, Depends(get_db)],
) -> ConversationResponse:
    store: AgentSessionStore = request.app.state.agent_sessions
    agent = AgentOrchestrator(
        adapter,
        session_store=store,
        require_capture_confirmation=True,
        audit_sink=lambda user, result, duration: record_run(
            db, user, result, duration
        ),
    )
    # Transport input contains no plan, identity, tool, provider or compiler state.
    raw_locale = (
        request.headers.get("Accept-Language", "").split(",")[0].split(";")[0].strip()
    )
    locale = raw_locale if re.fullmatch(r"[a-z]{2}(?:-[A-Z]{2})?", raw_locale) else None
    timezone = getattr(request.state, "profile_timezone", None) or "UTC"
    try:
        CompileContext.valid_timezone(timezone)
    except ValueError:
        timezone = "UTC"
    turn = await agent.handle_session(
        user,
        AgentInput(
            text=body.text,
            timezone=timezone,
            locale=locale,
            expectation_id=body.expectation_id,
        ),
        body.session_reference,
    )
    result = turn.result
    assert result.trust is not None
    trust = result.trust
    traces = []
    for step in result.steps:
        traces.extend(
            [
                PublicTrace(layer="Agent", label=step.action.value),
                PublicTrace(layer="MCP", label=step.tool.value),
            ]
        )
    if result.bedrock_used:
        label = (
            "grounded explanation"
            if result.explanation is not None
            else "compiled"
            if result.captured
            else "clarification"
            if result.clarification_required
            else "interpretation"
        )
        traces.append(PublicTrace(layer="Bedrock", label=label))
    elif result.fallback_used and result.explanation is not None:
        traces.append(PublicTrace(layer="CountOn", label="grounded fallback"))
    rows = list(result.candidates)
    if result.expectations is not None:
        rows = result.expectations.expectations
    elif result.expectation is not None:
        rows = [result.expectation]
    response.headers["Cache-Control"] = "no-store"
    claim = result.expectation.claim if result.expectation else None
    if not claim and (trust.expectation_id or (result.explanation and result.explanation.expectation_id)):
        target_id = trust.expectation_id or (result.explanation and result.explanation.expectation_id)
        found_exp = db.get(Expectation, target_id)
        if found_exp and found_exp.user_id == user.id:
            claim = found_exp.claim
    expectation_label = (
        claim[:120]
        if claim and not SENSITIVE.search(claim)
        else "Selected expectation"
        if trust.expectation_id
        else None
    )
    return ConversationResponse(
        action=result.action.value,
        status=result.status.value,
        answer=result.answer,
        code=result.code.value if result.code else None,
        session_reference=turn.session_reference.get_secret_value()
        if turn.session_reference
        else None,
        captured=result.captured,
        clarification_required=result.clarification_required,
        rows=rows,
        saved_id=result.expectation_id if result.captured else None,
        traces=traces,
        provenance=PublicProvenance(
            run_id=trust.run_id,
            expectation_label=expectation_label,
            evaluator_result=trust.evaluator_result,
            sources_used=list(trust.sources_used),
            evidence_count=len(trust.evidence_ids),
            bedrock_used=trust.bedrock_used,
            fallback_used=trust.fallback_used,
            grounded=trust.grounded,
        ),
    )
