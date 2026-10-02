"""Owned in-app notifications; no email, SMS or push endpoints."""
from datetime import datetime
from typing import Annotated,Literal
from uuid import UUID
from fastapi import APIRouter,Depends,Query
from pydantic import AliasChoices,BaseModel,ConfigDict,Field
from sqlalchemy.orm import Session
from app.api.dependencies import CurrentUser,get_db
from app.services import notification_service as service

router=APIRouter(prefix='/notifications',tags=['notifications'])
Database=Annotated[Session,Depends(get_db)]


class NotificationResponse(BaseModel):
    model_config=ConfigDict(from_attributes=True)
    id: UUID
    user_id: UUID
    expectation_id: UUID
    evaluation_id: UUID
    type: str
    channel: str
    status: str
    message: str
    metadata: dict = Field(validation_alias=AliasChoices('notification_metadata','metadata'))
    sent_at: datetime|None
    created_at: datetime


class NotificationUpdate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    status: Literal['read','dismissed']


@router.get('',response_model=list[NotificationResponse])
def notifications(db:Database,user:CurrentUser,status:Literal['pending','read','sent','failed','dismissed']|None=None,
    limit:Annotated[int,Query(ge=1,le=100)]=100,offset:Annotated[int,Query(ge=0)]=0):
    return service.list_notifications(db,user.id,status=status,limit=limit,offset=offset)


@router.get('/{id}',response_model=NotificationResponse)
def get(id:UUID,db:Database,user:CurrentUser):return service.get(db,id,user.id)


@router.patch('/{id}',response_model=NotificationResponse)
def update(id:UUID,payload:NotificationUpdate,db:Database,user:CurrentUser):return service.update(db,id,payload.status,user.id)
