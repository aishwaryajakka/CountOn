"""Strict contracts for the local Bee CLI bridge and explicit imports."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, SecretStr


class PairingResponse(BaseModel):
    pairing_code: str = Field(repr=False)
    expires_at: datetime


class PairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    pairing_code: SecretStr = Field(min_length=32, max_length=256)
    cli_version: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._+-]+$")
    bee_account_ref: str = Field(min_length=8, max_length=255)


class PairResponse(BaseModel):
    connector_token: str = Field(repr=False)
    connection_id: UUID
    expires_at: datetime


class BeeCandidateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    external_id: str = Field(min_length=1, max_length=255)
    version: str = Field(min_length=1, max_length=64)
    category: Literal["fact", "todo", "conversation", "journal"]
    summary: str = Field(min_length=1, max_length=1000)
    observed_at: AwareDatetime
    confidence: float = Field(default=0.7, ge=0, le=1)
    completed: bool | None = None


class CandidateBatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    candidates: list[BeeCandidateInput] = Field(max_length=100)
    next_cursor: str | None = Field(default=None, min_length=1, max_length=512)


class CandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    connection_id: UUID
    external_id: str
    category: str
    summary: str
    observed_at: datetime
    confidence: float
    status: str


class BeeCliStatus(BaseModel):
    simulator_available: Literal[True] = True
    state: Literal["not_paired", "paired", "import_enabled", "disconnected", "error"]
    connection_id: UUID | None = None
    cli_version: str | None = None
    last_sync_at: datetime | None = None
    last_error: str | None = None
    pending_candidates: int = 0


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expectation_id: UUID
    candidate_ids: list[UUID] = Field(min_length=1, max_length=50)
    consent: Literal[True]
    confirm_source_binding: Literal[True]


class ImportResponse(BaseModel):
    imported: int
    duplicate: int
    evaluation_ids: list[UUID]
    binding_id: UUID


class DisconnectBeeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revoke: Literal[True] = True
