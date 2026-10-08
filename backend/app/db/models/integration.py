"""Provider account metadata only: credentials require future encrypted storage."""
from datetime import datetime
from enum import StrEnum
from uuid import UUID,uuid4
from sqlalchemy import CheckConstraint,DateTime,ForeignKey,Index,String,func,text
from sqlalchemy.dialects.postgresql import ARRAY,JSONB,UUID as PGUUID
from sqlalchemy.orm import Mapped,mapped_column
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
    connection_metadata: Mapped[dict]=mapped_column('metadata',JSONB,default=dict,server_default=text("'{}'::jsonb"))
    last_synced_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    updated_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now(),onupdate=func.now())
