"""Authenticated user controls and credential-scoped local Bee CLI bridge."""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, Response
from sqlalchemy.orm import Session

from app.api.dependencies import CurrentUser, get_db
from app.schemas.bee_connector import (
    BeeCliStatus,
    CandidateBatch,
    CandidateResponse,
    DisconnectBeeRequest,
    ImportRequest,
    ImportResponse,
    PairingResponse,
    PairRequest,
    PairResponse,
)
from app.services import bee_connector_service as service

router = APIRouter(prefix="/integrations/bee-cli", tags=["bee-cli"])
Database = Annotated[Session, Depends(get_db)]


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


@router.post("/pairings", response_model=PairingResponse, dependencies=[Depends(no_store)])
def create_pairing(db: Database, user: CurrentUser):
    code, expires_at = service.create_pairing(db, user.id)
    return {"pairing_code": code, "expires_at": expires_at}


@router.post("/pair", response_model=PairResponse, dependencies=[Depends(no_store)])
def pair(payload: PairRequest, db: Database):
    token, connection_id, expires_at = service.pair(db, payload)
    return {"connector_token": token, "connection_id": connection_id, "expires_at": expires_at}


def connector(
    db: Database,
    authorization: Annotated[str | None, Header(max_length=512)] = None,
):
    if not authorization or not authorization.startswith("Bearer "):
        from app.core.exceptions import AuthenticationError

        raise AuthenticationError()
    return service.authenticate_connector(db, authorization[7:])


ConnectorCredential = Annotated[object, Depends(connector)]


@router.post("/bridge/candidates", dependencies=[Depends(no_store)])
def stage_candidates(payload: CandidateBatch, db: Database, credential: ConnectorCredential):
    return service.stage(db, credential, payload)


@router.get("/status", response_model=BeeCliStatus, dependencies=[Depends(no_store)])
def status(db: Database, user: CurrentUser):
    return service.status(db, user.id)


@router.get("/candidates", response_model=list[CandidateResponse], dependencies=[Depends(no_store)])
def candidates(db: Database, user: CurrentUser):
    return service.candidates(db, user.id)


@router.post("/imports", response_model=ImportResponse, dependencies=[Depends(no_store)])
def import_candidates(payload: ImportRequest, db: Database, user: CurrentUser):
    return service.import_candidates(db, user.id, payload)


@router.post("/disconnect", dependencies=[Depends(no_store)])
def disconnect(payload: DisconnectBeeRequest, db: Database, user: CurrentUser):
    return service.disconnect(db, user.id)
