"""Every connected-account read is owner-scoped; no provider HTTP calls."""
from datetime import datetime, timezone

from sqlalchemy import select

from app.db.models.bee_connector import BeeCliCredential
from app.db.models.integration import IntegrationConnection, IntegrationCredential


def mark_credentials(db, items, user_id):
    ids = [item.id for item in items]
    configured = set(db.scalars(select(IntegrationCredential.connection_id).where(
        IntegrationCredential.connection_id.in_(ids), IntegrationCredential.user_id == user_id))) if ids else set()
    if ids:
        configured.update(db.scalars(select(BeeCliCredential.connection_id).where(
            BeeCliCredential.connection_id.in_(ids), BeeCliCredential.user_id == user_id,
            BeeCliCredential.revoked_at.is_(None), BeeCliCredential.expires_at > datetime.now(timezone.utc))))
    for item in items:
        item.__dict__['_credential_state'] = 'configured' if item.id in configured else 'not_configured'
    return items


def create(db,payload,user_id):
    values=payload.model_dump()
    values['connection_metadata']=values.pop('metadata')
    now = datetime.now(timezone.utc)
    if str(values.get('status')) == 'connected':
        values['connected_at'] = now
    elif str(values.get('status')) == 'disconnected':
        values['revoked_at'] = now
    item=IntegrationConnection(user_id=user_id,**values)
    db.add(item);db.flush()
    return item


def get(db,id,user_id):
    item = db.scalar(select(IntegrationConnection).where(IntegrationConnection.id==id,IntegrationConnection.user_id==user_id))
    if item is not None: mark_credentials(db, [item], user_id)
    return item


def list_connections(db,user_id,provider=None,connection_type=None,status=None,limit=100,offset=0):
    stmt=select(IntegrationConnection).where(IntegrationConnection.user_id==user_id)
    for field,value in [('provider',provider),('connection_type',connection_type),('status',status)]:
        if value is not None:stmt=stmt.where(getattr(IntegrationConnection,field)==value)
    return mark_credentials(db, list(db.scalars(stmt.order_by(IntegrationConnection.created_at.desc(),IntegrationConnection.id.desc()).limit(limit).offset(offset))), user_id)


def update(db,item,changes):
    if 'metadata' in changes:changes['connection_metadata']=changes.pop('metadata')
    for key,value in changes.items():setattr(item,key,value)
    db.flush()
    return item


def delete(db,item):
    db.delete(item);db.flush()
