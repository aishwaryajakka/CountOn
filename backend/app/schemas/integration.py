"""Strict metadata-only account contracts; token/credential input is unsupported."""
from datetime import datetime
from typing import Annotated,Literal
from uuid import UUID
from pydantic import AliasChoices,BaseModel,ConfigDict,Field
from app.db.models.integration import Provider,ConnectionType,ConnectionStatus


class ConnectionMetadata(BaseModel):
    model_config=ConfigDict(extra='forbid')
    mock: bool = False
    demo: bool = False
    demo_tag: Literal['counton-demo-v1'] | None = None
    account_kind: Literal['personal','work','family'] | None = None


class IntegrationCreate(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    provider: Provider
    connection_type: ConnectionType
    external_account_id: str|None = Field(default=None,min_length=1,max_length=255)
    display_name: str|None = Field(default=None,min_length=1,max_length=255)
    status: ConnectionStatus = ConnectionStatus.pending
    scopes: list[Annotated[str,Field(min_length=1,max_length=100)]] = Field(default_factory=list,max_length=50)
    metadata: ConnectionMetadata = Field(default_factory=ConnectionMetadata)


class IntegrationUpdate(BaseModel):
    model_config=ConfigDict(extra='forbid',str_strip_whitespace=True)
    display_name: str|None = Field(default=None,min_length=1,max_length=255)
    external_account_id: str|None = Field(default=None,min_length=1,max_length=255)
    status: ConnectionStatus|None = None
    scopes: list[Annotated[str,Field(min_length=1,max_length=100)]]|None = Field(default=None,max_length=50)
    metadata: ConnectionMetadata|None = None


class IntegrationResponse(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id: UUID
    user_id: UUID
    provider: Provider
    connection_type: ConnectionType
    external_account_id: str|None
    display_name: str|None
    status: ConnectionStatus
    scopes: list[str]
    metadata: ConnectionMetadata = Field(validation_alias=AliasChoices('connection_metadata','metadata'))
    last_synced_at: datetime|None
    created_at: datetime
    updated_at: datetime
    credential_state: Literal['not_configured'] = 'not_configured'
