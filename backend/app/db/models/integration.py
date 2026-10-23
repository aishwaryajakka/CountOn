"""Provider metadata and separate backend-only encrypted credentials."""
from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Provider(StrEnum):
    google='google'
    microsoft='microsoft'
    ring='ring'
    bee='bee'
    utility='utility'
    delivery='delivery'


class ConnectionType(StrEnum):
    email='email'
    calendar='calendar'
    camera='camera'
    wearable='wearable'
    utility='utility'
    delivery='delivery'


class ConnectionStatus(StrEnum):
    pending='pending'
    connected='connected'
    disconnected='disconnected'
    error='error'


class IntegrationConnection(Base):
    __tablename__='integration_connections'
    __table_args__=(
        UniqueConstraint('id','user_id',name='uq_integration_owner'),
        CheckConstraint("provider IN ('google','microsoft','ring','bee','utility','delivery')",name='ck_integration_provider'),
        CheckConstraint("connection_type IN ('email','calendar','camera','wearable','utility','delivery')",name='ck_integration_type'),
        CheckConstraint("status IN ('pending','connected','disconnected','error')",name='ck_integration_status'),
        Index('ix_integration_owner_filters','user_id','provider','connection_type','status'),)
    id: Mapped[UUID]=mapped_column(PGUUID,primary_key=True,default=uuid4)
    user_id: Mapped[UUID]=mapped_column(PGUUID,ForeignKey('profiles.id',ondelete='CASCADE'),index=True)
    provider: Mapped[str]=mapped_column(String(20))
    connection_type: Mapped[str]=mapped_column(String(20))
    external_account_id: Mapped[str|None]=mapped_column(String(255))
    display_name: Mapped[str|None]=mapped_column(String(255))
    status: Mapped[str]=mapped_column(String(20),default='pending',server_default='pending')
    scopes: Mapped[list[str]]=mapped_column(ARRAY(String(100)),default=list,server_default=text('ARRAY[]::varchar[]'))
    oauth_generation: Mapped[str|None] = mapped_column(String(64))
    connection_metadata: Mapped[dict]=mapped_column('metadata',JSONB,default=dict,server_default=text("'{}'::jsonb"))
    last_synced_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    connected_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    failure_status: Mapped[str|None]=mapped_column(String(64))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now())

    @property
    def credential_state(self) -> str:
        return self.__dict__.get('_credential_state', 'not_configured')


class IntegrationCredential(Base):
    """Trusted backend only; authenticated encryption binds secrets to the account."""
    __tablename__ = 'integration_credentials'
    __table_args__ = (ForeignKeyConstraint(['connection_id','user_id'],
        ['integration_connections.id','integration_connections.user_id'], ondelete='CASCADE', name='fk_credential_owner'),)
    connection_id: Mapped[UUID] = mapped_column(PGUUID, primary_key=True)
    user_id: Mapped[UUID] = mapped_column(PGUUID)
    encrypted_tokens: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ProviderOAuthState(Base):
    __tablename__ = 'provider_oauth_states'
    __table_args__ = (ForeignKeyConstraint(['connection_id','user_id'],
        ['integration_connections.id','integration_connections.user_id'], ondelete='CASCADE', name='fk_oauth_owner'),)
    state_digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    connection_id: Mapped[UUID] = mapped_column(PGUUID)
    user_id: Mapped[UUID] = mapped_column(PGUUID)
    encrypted_verifier: Mapped[str] = mapped_column(Text)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
