"""Full authenticated application acceptance for either selected target.

Uses the exact FastAPI dependencies/services/engine and a real Auth access token.
No global auth bypass or environment-file rewrites.
"""
from uuid import UUID,uuid4
from _common import run_cli


def main():
    from fastapi.testclient import TestClient
    from sqlalchemy import func,select
    from _token import access_token
    from _cleanup import cleanup_expectations,remove_audits
    from app.core.auth import get_token_verifier
    from app.core.config import get_settings
    from app.db.models import AuditEvent,Evidence,Expectation,MonitoringJob,Profile,IntegrationConnection
    from app.db.session import SessionLocal,engine
    from app.main import app
    token=access_token()
    owner=get_token_verifier().verify(token).id
    run_id=uuid4()
    claim=f'Operational acceptance [{run_id}]'
    connection_tag=f'acceptance:{run_id}'
    def check(value,label):
        if not value:
            print('FAIL '+label)
            raise RuntimeError('Operational acceptance failed')
    try:
        try:
            with TestClient(app) as client:
                headers={'Authorization':f'Bearer {token}'}
                check(client.get('/health').status_code==200,'health')
                check(client.get('/ready').status_code==200,'readiness')
                account=client.post('/api/v1/integrations',headers=headers,json={'provider':'google','connection_type':'calendar','display_name':'Acceptance Personal Calendar','external_account_id':connection_tag,'metadata':{'mock':True}})
                check(account.status_code==201 and account.json()['credential_state']=='not_configured','metadata-only connected account')
                payload={'claim':claim,'type':'numeric_comparison','metric':'total_cost','comparison':'less_than','baseline':142.1}
                response=client.post('/api/v1/expectations',headers=headers,json=payload)
                check(response.status_code==201,'authenticated create')
                eid=UUID(response.json()['id']);path=f'/api/v1/expectations/{eid}'
                bill={'source':'utility_bill','metric':'total_cost','value':{'amount':162},'unit':'USD','observed_at':'2026-10-01T20:00:00Z','external_event_id':f'acceptance:{run_id}'}
                evidence_headers=dict(headers,**{'Idempotency-Key':str(uuid4())})
                first=client.post(path+'/evidence',headers=evidence_headers,json=bill)
                retry=client.post(path+'/evidence',headers=evidence_headers,json=bill)
                check(first.status_code==retry.status_code==201 and first.json()['id']==retry.json()['id'],'duplicate evidence retry')
                evaluated=client.post(path+'/evaluate',headers=headers)
                check(evaluated.status_code==200 and evaluated.json()['result']=='MISMATCH','deterministic mismatch')
                notice=client.get('/api/v1/notifications',headers=headers).json()
                check(any(row['expectation_id']==str(eid) for row in notice),'mismatch notification')
                with SessionLocal() as db:
                    check(db.get(Profile,owner) is not None,'profile')
                    check(db.get(Expectation,eid).user_id==owner,'ownership')
                    check(db.scalar(select(func.count()).select_from(Evidence).where(Evidence.expectation_id==eid))==1,'idempotent persistence')
                    check(db.scalar(select(func.count()).select_from(MonitoringJob).where(MonitoringJob.expectation_id==eid,MonitoringJob.user_id==owner))==1,'monitoring job')
                    audit=list(db.scalars(select(AuditEvent).where(AuditEvent.expectation_id==eid,AuditEvent.user_id==owner)))
                    check(len(audit)==4 and all(row.request_id for row in audit),'correlated audit events')
            print('PASS authentication/profile, connected account, provider evidence retry, evaluation, notification, audit, monitoring job and ownership')
        finally:
            with SessionLocal() as db:
                ids=list(db.scalars(select(Expectation.id).where(Expectation.claim==claim,Expectation.user_id==owner)))
                cleanup_expectations(db,owner,ids)
                from app.services import integration_service
                integration_ids=list(db.scalars(select(IntegrationConnection.id).where(IntegrationConnection.user_id==owner,IntegrationConnection.external_account_id==connection_tag)))
                for integration_id in integration_ids:integration_service.delete(db,integration_id,owner)
                remove_audits(db,owner,integration_ids)
                check(db.scalar(select(func.count()).select_from(Expectation).where(Expectation.claim==claim,Expectation.user_id==owner))==0,'tagged cleanup')
        print(f'{get_settings().database_target.upper()} OPERATIONAL ACCEPTANCE PASSED')
        return 0
    finally:
        engine.dispose()


if __name__=='__main__':
    raise SystemExit(run_cli(main))
