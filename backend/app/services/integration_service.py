"""Metadata-only connections with atomic audit writes and ownership checks."""
import logging
from datetime import datetime, timezone

from app.core.exceptions import InvalidIntegrationError, ResourceNotFoundError
from app.repositories import audit
from app.repositories import integration as repository
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
        audit.record(
            db,user_id,'integration',item.id,'integration.created',metadata=demo_metadata(item),
            event_type='SOURCE_CONNECTED' if item.status == 'connected' else None,
            actor_type='USER',source_provider=item.provider.upper(),
            source_type=item.connection_type.upper(),
            source_provenance='SIMULATED' if item.connection_metadata.get('demo') else 'METADATA_ONLY',
            source_reference=item.external_account_id,
            idempotency_key=f'SOURCE_CONNECTED:{item.id}:{item.connected_at.isoformat()}'
            if item.status == 'connected' and item.connected_at else None,
        )
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
        identity_changed = any(key in changes and changes[key] != getattr(item, key) for key in ('scopes', 'external_account_id', 'status'))
        old_status = item.status
        repository.update(db,item,changes)
        now = datetime.now(timezone.utc)
        if item.status == 'connected' and old_status != 'connected':
            item.connected_at, item.revoked_at, item.failure_status = now, None, None
        elif item.status == 'disconnected' and old_status != 'disconnected':
            item.revoked_at, item.failure_status = now, None
        if item.provider in ('microsoft', 'google') and (identity_changed or changes.get('status') in ('disconnected','pending')):
            from sqlalchemy import delete

            from app.db.models.integration import (
                IntegrationCredential,
                ProviderOAuthState,
            )
            db.execute(delete(IntegrationCredential).where(IntegrationCredential.connection_id == item.id))
            db.execute(delete(ProviderOAuthState).where(ProviderOAuthState.connection_id == item.id))
            from app.db.models.provider_sync import ProviderSyncState
            db.execute(delete(ProviderSyncState).where(ProviderSyncState.connection_id == item.id))
            item.oauth_generation = None
            item.__dict__['_credential_state'] = 'not_configured'
        audit.record(
            db,user_id,'integration',item.id,'integration.updated',metadata=demo_metadata(item),
            event_type='SOURCE_CONNECTED' if item.status == 'connected' and old_status != 'connected' else None,
            actor_type='USER',source_provider=item.provider.upper(),
            source_type=item.connection_type.upper(),
            source_provenance='SIMULATED' if item.connection_metadata.get('demo') else 'METADATA_ONLY',
            source_reference=item.external_account_id,
            idempotency_key=f'SOURCE_CONNECTED:{item.id}:{item.connected_at.isoformat()}'
            if item.status == 'connected' and old_status != 'connected' and item.connected_at else None,
        )
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
