"""Opt-in live auth/RLS checks using three temporary, confirmed Auth users.

Uses the backend-only secret key for admin create/delete, never for API auth.
No emails are sent. Deletes only identities created by this invocation.
"""
from uuid import UUID, uuid4
import os
import secrets
import subprocess
import sys

from _common import BACKEND_ROOT, require_target, run_cli


def main() -> int:
    if not require_target('supabase'):
        return 1
    import httpx
    from dotenv import dotenv_values
    from sqlalchemy import text
    from app.core.auth import get_token_verifier
    from app.core.config import get_settings
    from app.db.session import engine

    settings=get_settings()
    admin_key=os.getenv('SUPABASE_SECRET_KEY') or dotenv_values(BACKEND_ROOT/'.env.local').get('SUPABASE_SECRET_KEY')
    if not admin_key or not settings.supabase_url or not settings.supabase_publishable_key:
        raise RuntimeError('Backend Supabase Auth configuration is required')
    admin_headers={'apikey':admin_key}
    if not admin_key.startswith('sb_secret_'):
        admin_headers['Authorization']=f'Bearer {admin_key}'
    created=[]
    expectations=[]
    def check(condition,label):
        if not condition:
            print(f'FAIL {label}')
            raise RuntimeError('Identity verification failed')
    def api_headers(token):
        return {'Authorization':f'Bearer {token}'}
    def rest_headers(token=None):
        headers={'apikey':settings.supabase_publishable_key}
        if token:headers['Authorization']=f'Bearer {token}'
        return headers
    try:
        with httpx.Client(base_url=settings.supabase_url.rstrip('/'),timeout=30) as cloud, httpx.Client(base_url='http://localhost:8000',timeout=30) as api:
            try:
                users=[]
                for _ in range(3):
                    email=f'counton-check-{uuid4().hex}@example.com'
                    password=secrets.token_urlsafe(40)
                    response=cloud.post('/auth/v1/admin/users',headers=admin_headers,json={
                        'email':email,'password':password,'email_confirm':True,
                        'app_metadata':{'counton_verification':True}})
                    check(response.status_code in (200,201),'create temporary Auth user')
                    user_id=UUID(response.json()['id'])
                    created.append(user_id)
                    response=cloud.post('/auth/v1/token?grant_type=password',headers=rest_headers(),json={'email':email,'password':password})
                    check(response.status_code==200,'real Auth sign-in')
                    token=response.json()['access_token']
                    try:
                        verified=get_token_verifier().verify(token)
                    except Exception:
                        # Safe diagnostics: no token, identity, URL or key output.
                        import jwt
                        from time import time
                        decoded=jwt.decode(token,options={"verify_signature":False})
                        print('JWT clock offset (seconds):', round(decoded.get('iat',0)-time()))
                        print('JWT issuer matches:', decoded.get('iss')==get_token_verifier().issuer)
                        print('JWT authenticated role:', decoded.get('role')=='authenticated')
                        print('JWT algorithm:', jwt.get_unverified_header(token).get('alg'))
                        raise
                    check(verified.id==user_id,'real JWT verification')
                    users.append((user_id,token))
                demo_user=users[2][0]
                users=users[:2]
                a, b=users
                check(api.get('/api/v1/expectations').status_code==401,'missing token')
                check(api.get('/api/v1/expectations',headers=api_headers('invalid-token')).status_code==401,'invalid token')
                payload={'claim':'Temporary ownership verification','type':'numeric_comparison','metric':'total_cost','comparison':'less_than','baseline':142.1}
                bill={'source':'utility_bill','metric':'total_cost','value':{'amount':162},'unit':'USD','observed_at':'2026-10-01T20:00:00Z'}
                for uid,token in users:
                    response=api.post('/api/v1/expectations',headers=api_headers(token),json=payload)
                    check(response.status_code==201 and response.json()['user_id']==str(uid),'authenticated create ownership')
                    expectations.append(UUID(response.json()['id']))
                path=f'/api/v1/expectations/{expectations[0]}'
                check(api.post(path+'/evidence',headers=api_headers(a[1]),json=bill).status_code==201,'own evidence')
                check(api.post(path+'/evaluate',headers=api_headers(a[1])).json().get('result')=='MISMATCH','own evaluation')
                for method,suffix,body in [('get','',None),('patch','',{'claim':'forbidden'}),('delete','',None),('post','/evidence',bill),('get','/evidence',None),('post','/evaluate',None),('get','/evaluations',None),('get','/evaluations/latest',None)]:
                    kwargs={'json':body} if body is not None else {}
                    check(api.request(method,path+suffix,headers=api_headers(b[1]),**kwargs).status_code==404,'cross-user '+method+suffix)
                for (uid,token),eid in zip(users,expectations):
                    response=api.get('/api/v1/expectations',headers=api_headers(token))
                    check(response.status_code==200 and {row['id'] for row in response.json()}=={str(eid)},'own list')
                integration=api.post('/api/v1/integrations',headers=api_headers(a[1]),json={'provider':'microsoft','connection_type':'email','display_name':'Acceptance Work Mail','metadata':{'mock':True}})
                check(integration.status_code==201,'live integration create')
                integration_id=UUID(integration.json()['id'])
                integration_path=f'/api/v1/integrations/{integration_id}'
                for method,body in [('get',None),('patch',{'status':'disconnected'}),('delete',None)]:
                    kwargs={'json':body} if body is not None else {}
                    check(api.request(method,integration_path,headers=api_headers(b[1]),**kwargs).status_code==404,'cross-user integration '+method)
                notices=api.get('/api/v1/notifications',headers=api_headers(a[1])).json()
                notice_id=next(row['id'] for row in notices if row['expectation_id']==str(expectations[0]))
                for method,body in [('get',None),('patch',{'status':'dismissed'})]:
                    kwargs={'json':body} if body is not None else {}
                    check(api.request(method,'/api/v1/notifications/'+notice_id,headers=api_headers(b[1]),**kwargs).status_code==404,'cross-user notification '+method)
                print('PASS real Auth JWT, profile bootstrap, API ownership and cross-user isolation')

                # Real PostgREST requests exercise actual Supabase RLS and grants.
                for table,filter_name,own,other in [('profiles','id',a[0],b[0]),('expectations','id',expectations[0],expectations[1]),('evidence','expectation_id',expectations[0],expectations[1]),('evaluations','expectation_id',expectations[0],expectations[1]),('monitoring_jobs','expectation_id',expectations[0],expectations[1]),('notifications','expectation_id',expectations[0],expectations[1]),('audit_events','expectation_id',expectations[0],expectations[1]),('integration_connections','id',integration_id,uuid4())]:
                    own_response=cloud.get('/rest/v1/'+table,headers=rest_headers(a[1]),params={filter_name:f'eq.{own}'})
                    check(own_response.status_code==200 and len(own_response.json())>=1,'RLS own read '+table)
                    # User B cannot see A's row, including children.
                    hidden=cloud.get('/rest/v1/'+table,headers=rest_headers(b[1]),params={filter_name:f'eq.{own}'})
                    check(hidden.status_code==200 and hidden.json()==[],'RLS cross read '+table)
                    anon=cloud.get('/rest/v1/'+table,headers=rest_headers(),params={filter_name:f'eq.{own}'})
                    check(anon.status_code in (401,403),'anon denied '+table)
                for uid in (a[0],b[0]):
                    response=cloud.post('/rest/v1/profiles',headers=rest_headers(a[1]),json={'id':str(uid)},params={'on_conflict':'id'})
                    # Own already exists; never overwrite it. Cross must fail RLS.
                    check(response.status_code in ((409,) if uid==a[0] else (403,)),'profile insert ownership')
                response=cloud.patch('/rest/v1/profiles',headers=rest_headers(a[1]),params={'id':f'eq.{a[0]}'},json={'display_name':'Verification'})
                check(response.status_code==204,'RLS own profile update')
                response=cloud.post('/rest/v1/expectations',headers=rest_headers(a[1]),json=dict(payload,id=str(uuid4()),user_id=str(b[0])))
                check(response.status_code==403,'RLS cross expectation insert')
                response=cloud.patch('/rest/v1/expectations',headers=rest_headers(a[1]),params={'id':f'eq.{expectations[0]}'},json={'user_id':str(b[0])})
                check(response.status_code==403,'RLS ownership transfer denied')
                for eid,allowed in [(expectations[0],True),(expectations[1],False)]:
                    response=cloud.post('/rest/v1/evidence',headers=rest_headers(a[1]),json=dict(bill,id=str(uuid4()),expectation_id=str(eid)))
                    check(response.status_code==(201 if allowed else 403),'RLS evidence insert ownership')
                response=cloud.post('/rest/v1/evaluations',headers=rest_headers(a[1]),json={'id':str(uuid4()),'expectation_id':str(expectations[0]),'result':'MATCH'})
                check(response.status_code==403,'client cannot forge evaluation')
                response=cloud.delete('/rest/v1/expectations',headers=rest_headers(b[1]),params={'id':f'eq.{expectations[0]}'})
                check(response.status_code==204 and api.get(path,headers=api_headers(a[1])).status_code==200,'RLS cross delete leaves owner row')
                with engine.connect() as connection:
                    rows=connection.execute(text("SELECT relname, relrowsecurity FROM pg_class JOIN pg_namespace ON pg_namespace.oid=relnamespace WHERE nspname='public' AND relname IN ('profiles','expectations','evidence','evaluations','monitoring_jobs','notifications','audit_events','integration_connections')")).all()
                    check(len(rows)==8 and all(row[1] for row in rows),'RLS catalog')
                    check(connection.scalar(text("SELECT count(*) FROM pg_constraint WHERE conname='fk_profiles_auth_user'"))==1,'real auth.users FK')
                print('PASS Supabase RLS, grants, child ownership and Auth foreign key')
                child_env=dict(os.environ,COUNTON_ACCESS_TOKEN=a[1],DATABASE_TARGET='supabase')
                check(subprocess.run([sys.executable,str(BACKEND_ROOT/'db/scripts/operational_acceptance.py')],env=child_env,cwd=BACKEND_ROOT,check=False).returncode==0,'Supabase operational acceptance')
                local_env=dict(child_env,DATABASE_TARGET='local')
                check(subprocess.run([sys.executable,str(BACKEND_ROOT/'db/scripts/operational_acceptance.py')],env=local_env,cwd=BACKEND_ROOT,check=False).returncode==0,'local authenticated operational acceptance')
                for target in ('local','supabase'):
                    demo_env=dict(child_env,DATABASE_TARGET=target,COUNTON_DEMO_USER_ID=str(demo_user))
                    for script in ('seed_demo_data.py','seed_demo_data.py','clear_demo_data.py'):
                        check(subprocess.run([sys.executable,str(BACKEND_ROOT/'db/scripts'/script)],env=demo_env,cwd=BACKEND_ROOT,check=False).returncode==0,target+' '+script)
                print('PASS local/Supabase demo seed, repeat seed and tagged cleanup')
                for script in ['supabase_acceptance.py','api_smoke.py']:
                    check(subprocess.run([sys.executable,str(BACKEND_ROOT/'db/scripts'/script)],env=child_env,cwd=BACKEND_ROOT,check=False).returncode==0,script)
            finally:
                # No broad deletes: each ID came from this run's admin create.
                cleanup_ok=True
                from sqlalchemy import create_engine,delete
                from app.db.models import Profile
                local_engine=create_engine(settings.local_database_url)
                try:
                    with local_engine.begin() as local_connection:
                        local_connection.execute(delete(Profile).where(Profile.id.in_(created)))
                except Exception:
                    cleanup_ok=False
                finally:
                    local_engine.dispose()
                for uid in reversed(created):
                    try:
                        response=cloud.delete(f'/auth/v1/admin/users/{uid}',headers=admin_headers)
                        cleanup_ok=cleanup_ok and response.status_code in (200,204)
                    except httpx.HTTPError:
                        cleanup_ok=False
                check(cleanup_ok,'temporary Auth user cleanup')
        with engine.connect() as connection:
            for uid in created:
                check(connection.scalar(text('SELECT count(*) FROM public.profiles WHERE id=:id'),{'id':uid})==0,'profile cascade cleanup')
                check(connection.scalar(text('SELECT count(*) FROM public.expectations WHERE user_id=:id'),{'id':uid})==0,'expectation cascade cleanup')
            for eid in expectations:
                for table in ['evidence','evaluations','notifications','monitoring_jobs']:
                    check(connection.scalar(text(f'SELECT count(*) FROM public.{table} WHERE expectation_id=:id'),{'id':eid})==0,'child cascade cleanup')
        print('PASS temporary Auth users, profiles and application rows cleaned up')
        print('SUPABASE IDENTITY CHECK PASSED')
        return 0
    finally:
        engine.dispose()


if __name__=='__main__':
    raise SystemExit(run_cli(main))
