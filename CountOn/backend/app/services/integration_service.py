"""Metadata-only connections with atomic audit writes and ownership checks."""
import logging
from app.core.exceptions import ResourceNotFoundError,InvalidIntegrationError
from app.repositories import integration as repository,audit
from app.repositories.profile import ensure_profile

logger=logging.getLogger(__name__)
ALLOWED_TYPES={'google':{'email','calendar'},'microsoft':{'email','calendar'},'ring':{'camera'},'bee':{'wearable'},'utility':{'utility'},'delivery':{'delivery'}}


def get(db,id,user_id):
    item=repository.get(db,id,user_id)
    if item is None:raise ResourceNotFoundError('INTEGRATION_NOT_FOUND','Integration not found')
    return item


def create(db,payload,user_id):
    if payload.connection_type not in ALLOWED_TYPES[payload.provider]:
        raise InvalidIntegrationError()
    try:
        ensure_profile(db,user_id)
        item=repository.create(db,payload,user_id)
        audit.record(db,user_id,'integration',item.id,'integration.created',metadata=demo_metadata(item))
        db.commit();db.refresh(item)
    except Exception:
        db.rollback();raise
    logger.info('Integration created',extra={'integration_id':str(item.id),'user_id':str(user_id)})
    return item


def list_connections(db,user_id,**filters):return repository.list_connections(db,user_id,**filters)


def update(db,id,payload,user_id):
    item=get(db,id,user_id)
    changes=payload.model_dump(exclude_unset=True)
    if any(changes.get(k) is None for k in ('status','scopes','metadata') if k in changes):raise InvalidIntegrationError()
    try:
        repository.update(db,item,changes)
        audit.record(db,user_id,'integration',item.id,'integration.updated',metadata=demo_metadata(item))
        db.commit();db.refresh(item)
    except Exception:
        db.rollback();raise
    return item


def delete(db,id,user_id):
    item=get(db,id,user_id)
    try:
        audit.record(db,user_id,'integration',item.id,'integration.deleted',metadata=demo_metadata(item))
        repository.delete(db,item)
        db.commit()
    except Exception:
        db.rollback();raise


def demo_metadata(item):
    return {k:v for k,v in item.connection_metadata.items() if k in ('demo','demo_tag')}
