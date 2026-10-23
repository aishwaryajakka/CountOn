"""Every connected-account read is owner-scoped; no provider HTTP calls."""
from sqlalchemy import select
from app.db.models.integration import IntegrationConnection
from app.db.models.oauth_credential import OAuthCredential

def create(db,payload,user_id):
    values=payload.model_dump()
    values['connection_metadata']=values.pop('metadata')
    item=IntegrationConnection(user_id=user_id,**values)
    db.add(item);db.flush()
    return item


def get(db, id, user_id, *, for_update=False):
    stmt = select(IntegrationConnection).where(
        IntegrationConnection.id == id,
        IntegrationConnection.user_id == user_id,
    )

    if for_update:
        stmt = stmt.with_for_update()

    return db.scalar(stmt)



def list_connections(
    db,
    user_id,
    provider=None,
    connection_type=None,
    status=None,
    limit=100,
    offset=0,
):
    stmt = select(IntegrationConnection).where(
        IntegrationConnection.user_id == user_id
    )

    for field, value in [
        ("provider", provider),
        ("connection_type", connection_type),
        ("status", status),
    ]:
        if value is not None:
            stmt = stmt.where(
                getattr(IntegrationConnection, field) == value
            )

    connections = list(
        db.scalars(
            stmt.order_by(
                IntegrationConnection.created_at.desc(),
                IntegrationConnection.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
    )

    for connection in connections:
        credential = db.scalars(
            select(OAuthCredential).where(
                OAuthCredential.integration_id == connection.id,
                OAuthCredential.user_id == user_id,
                OAuthCredential.provider == connection.provider,
            )
        ).first()

        connection.credential_state = (
            "configured" if credential is not None else "not_configured"
        )

    return connections



def update(db,item,changes):
    if 'metadata' in changes:changes['connection_metadata']=changes.pop('metadata')
    for key,value in changes.items():setattr(item,key,value)
    db.flush()
    return item


def delete(db,item):
    db.delete(item);db.flush()
