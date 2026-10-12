"""Expectation Compiler and Mismatch Investigator API endpoints."""

from typing import Annotated
from fastapi import APIRouter, Depends, status as http_status
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_db
from app.schemas.compiler import (
    CompileRequest,
    CompileResponse,
    InvestigationRequest,
    InvestigationResponse,
)
from app.services import compiler_service, investigator_service

router = APIRouter(prefix="/compiler", tags=["compiler"])
Database = Annotated[Session, Depends(get_db)]


@router.post(
    "/compile",
    response_model=CompileResponse,
    status_code=http_status.HTTP_200_OK,
    summary="Compile natural language statement into structured expectation metadata",
)
def compile_statement(payload: CompileRequest) -> CompileResponse:
    result = compiler_service.compile_statement(payload.text, mock_mode=payload.mock_mode)
    return CompileResponse(
        kind=result.kind,
        expectation=result.expectation,
        clarification=result.clarification,
    )


@router.post(
    "/investigate",
    response_model=InvestigationResponse,
    status_code=http_status.HTTP_200_OK,
    summary="Investigate confirmed expectation mismatch using AI root-cause analysis",
)
def investigate_mismatch(
    payload: InvestigationRequest,
    db: Database,
    user: CurrentUser,
) -> InvestigationResponse:
    result = investigator_service.investigate_expectation_mismatch(
        db=db,
        expectation_id=payload.expectation_id,
        user_id=user.id,
        mock_mode=payload.mock_mode,
    )
    return InvestigationResponse(
        explanation=result.explanation,
        key_factors=result.key_factors,
        confidence=result.confidence,
    )
