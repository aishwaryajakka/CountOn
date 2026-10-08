"""PostgreSQL-backed ownership isolation including all nested routes."""
from uuid import UUID

import pytest
from sqlalchemy import func, select

from app.api.dependencies import get_current_user
from app.db.models import Profile, AuditEvent
from app.main import app
from app.services.profile_service import ensure_profile


pytestmark=pytest.mark.integration


def test_owner_is_authenticated_and_client_cannot_assign_owner(client,users,numeric_payload):
    assert client.post('/api/v1/expectations',json=dict(numeric_payload,user_id=str(users[1].id))).status_code==422
    response=client.post('/api/v1/expectations',json=numeric_payload)
    assert response.status_code==201
    assert response.json()['user_id']==str(users[0].id)
    assert client.get('/api/v1/expectations/'+response.json()['id']).status_code==200


def test_two_users_isolated_on_every_route(client,users,numeric_payload,bill_payload):
    a=client.post('/api/v1/expectations',json=numeric_payload).json()
    path='/api/v1/expectations/'+a['id']
    assert client.post(path+'/evidence',json=bill_payload).status_code==201
    assert client.post(path+'/evaluate').status_code==200
    app.dependency_overrides[get_current_user]=lambda:users[1]
    assert client.get('/api/v1/expectations').json()==[]
    b=client.post('/api/v1/expectations',json=numeric_payload).json()
    assert [item['id'] for item in client.get('/api/v1/expectations').json()]==[b['id']]
    for method,suffix,payload in [('get','',None),('patch','',{'claim':'stolen'}),('delete','',None),
        ('post','/evidence',bill_payload),('get','/evidence',None),('post','/evaluate',None),
        ('get','/evaluations',None),('get','/evaluations/latest',None)]:
        kwargs={'json':payload} if payload is not None else {}
        response=getattr(client,method)(path+suffix,**kwargs)
        assert response.status_code==404,(method,suffix)
    app.dependency_overrides[get_current_user]=lambda:users[0]
    assert client.get(path).json()['claim']==numeric_payload['claim']
    assert len(client.get(path+'/evidence').json())==1
    assert len(client.get(path+'/evaluations').json())==1
    assert [item['id'] for item in client.get('/api/v1/expectations').json()]==[a['id']]


def test_profile_upsert_preserves_data(db,users):
    profile=db.get(Profile,users[0].id)
    profile.display_name='Kept name'
    db.commit()
    first=ensure_profile(db,users[0].id)
    second=ensure_profile(db,users[0].id)
    assert first.id==second.id==users[0].id
    assert second.display_name=='Kept name'
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.user_id==users[0].id,AuditEvent.action=='profile.created'))==1
    assert db.scalar(select(func.count()).select_from(Profile).where(Profile.id==users[0].id))==1


def test_verified_token_bootstraps_profile(client,db,monkeypatch,numeric_payload):
    from cryptography.hazmat.primitives.asymmetric import ec
    from types import SimpleNamespace
    from time import time
    from uuid import uuid4
    import jwt
    from app.core.auth import TokenVerifier
    from app.core.config import Settings
    verifier=TokenVerifier(Settings(_env_file=None,database_target='local',
        local_database_url='postgresql+psycopg://fixture@localhost/fixture',supabase_url='https://auth.example.test'))
    key=ec.generate_private_key(ec.SECP256R1())
    monkeypatch.setattr(verifier.jwks,'get_signing_key_from_jwt',lambda _:SimpleNamespace(key=key.public_key()))
    claims=dict(sub=str(uuid4()),iss=verifier.issuer,aud='authenticated',role='authenticated',iat=int(time())-1,exp=int(time())+300)
    encoded=jwt.encode(claims,key,algorithm='ES256',headers={'kid':'test-key'})
    monkeypatch.setattr('app.api.dependencies.get_token_verifier',lambda:verifier)
    app.dependency_overrides.pop(get_current_user)
    response=client.post('/api/v1/expectations',json=numeric_payload,headers={'Authorization':f'Bearer {encoded}'})
    assert response.status_code==201
    assert response.json()['user_id']==claims['sub']
    assert db.get(Profile,UUID(claims['sub'])) is not None
