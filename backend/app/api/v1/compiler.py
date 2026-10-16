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
    OutlookContextPayload,
    OutlookExtractionResult,
    GmailContextPayload,
    GmailExtractionResult,
    AmazonDeliveryPayload,
    AmazonExtractionResult,
)
from app.ai.outlook_intelligence import extract_from_outlook_context
from app.ai.gmail_intelligence import extract_from_gmail_context
from app.ai.amazon_intelligence import extract_from_amazon_context
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
    result = compiler_service.compile_statement(
        text=payload.text,
        mock_mode=payload.mock_mode,
        conversation_history=payload.conversation_history,
        draft_expectation=payload.draft_expectation,
        expectation_id=payload.expectation_id,
    )
    return CompileResponse(
        kind=result.kind,
        expectation=result.expectation,
        clarification=result.clarification,
        cancellation=result.cancellation,
        is_correction=result.is_correction,
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


@router.post(
    "/outlook-context",
    response_model=OutlookExtractionResult,
    status_code=http_status.HTTP_200_OK,
    summary="Extract expectations and normalized evidence from Outlook email or calendar context",
)
def extract_outlook(payload: OutlookContextPayload) -> OutlookExtractionResult:
    return extract_from_outlook_context(payload)


@router.post(
    "/gmail-context",
    response_model=GmailExtractionResult,
    status_code=http_status.HTTP_200_OK,
    summary="Extract expectations and normalized evidence from Gmail email or Google Calendar context",
)
def extract_gmail(payload: GmailContextPayload) -> GmailExtractionResult:
    return extract_from_gmail_context(payload)


@router.post(
    "/amazon-context",
    response_model=AmazonExtractionResult,
    status_code=http_status.HTTP_200_OK,
    summary="Analyze Amazon order and package tracking context for deliveries, delays, and cancellations",
)
def extract_amazon(payload: AmazonDeliveryPayload) -> AmazonExtractionResult:
    return extract_from_amazon_context(payload)


