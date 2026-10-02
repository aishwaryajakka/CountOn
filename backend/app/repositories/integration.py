"""Every connected-account read is owner-scoped; no provider HTTP calls."""
from sqlalchemy import select
from app.db.models.integration import IntegrationConnection


def create(db,payload,user_id):
    values=payload.model_dump()
    values['connection_metadata']=values.pop('metadata')
    item=IntegrationConnection(user_id=user_id,**values)
    db.add(item);db.flush()
    return item


def get(db,id,user_id):
    return db.scalar(select(IntegrationConnection).where(IntegrationConnection.id==id,IntegrationConnection.user_id==user_id))


def list_connections(db,user_id,provider=None,connection_type=None,status=None,limit=100,offset=0):
    stmt=select(IntegrationConnection).where(IntegrationConnection.user_id==user_id)
    for field,value in [('provider',provider),('connection_type',connection_type),('status',status)]:
        if value is not None:stmt=stmt.where(getattr(IntegrationConnection,field)==value)
    return list(db.scalars(stmt.order_by(IntegrationConnection.created_at.desc(),IntegrationConnection.id.desc()).limit(limit).offset(offset)))


def update(db,item,changes):
    if 'metadata' in changes:changes['connection_metadata']=changes.pop('metadata')
    for key,value in changes.items():setattr(item,key,value)
    db.flush()
    return item


def delete(db,item):
    db.delete(item);db.flush()
