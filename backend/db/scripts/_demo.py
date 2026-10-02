"""Tagged, atomic demo seeding/cleanup; no OAuth or invented Supabase identities."""
import os
from uuid import UUID,uuid5,NAMESPACE_URL
from datetime import datetime,timedelta,timezone
from sqlalchemy import delete,func,select,text
from sqlalchemy.orm import Session

TAG='counton-demo-v1'
LOCAL_DEMO_ID=uuid5(NAMESPACE_URL,'https://counton.example/demo/maya-chen/v1')
CONNECTIONS=[('google','email','Personal Gmail','personal-gmail',['mail.read']),
    ('google','calendar','Personal Calendar','personal-calendar',['calendar.read']),
    ('microsoft','calendar','Work Outlook Calendar','work-calendar',['calendar.read']),
    ('ring','camera','Front Door Ring','front-door',['camera.read']),
    ('bee','wearable','Bee Personal Context','personal-context',['context.read']),
    ('utility','utility','City Electric Utility','electricity',['bill.read'])]
SCENARIOS=[('bill','My next electricity bill should be lower.','numeric_comparison','total_cost','MISMATCH'),
    ('package','The package should arrive today.','boolean','delivered','MATCH'),
    ('plumber','My landlord said the plumber is coming Friday.','boolean','appointment_confirmed','MATCH'),
    ('dentist','My dentist appointment was moved to next Tuesday.','temporal','appointment_date','UNKNOWN'),
    ('after-hours','I should have no meetings after 5 PM tomorrow.','temporal','meeting_start','UNKNOWN')]
OBSERVATIONS={
    'bill':[('utility_usage','energy_usage_change',{'percentage':-18},'percent'),
            ('utility_bill','total_cost',{'amount':162},'USD'),
            ('tariff','rate_change',{'percentage':22},'percent')],
    'package':[('delivery','delivered',{'value':True,'description':'Delivery provider marked the package delivered'},None),
               ('ring','package_present',{'value':True,'description':'Mock front door package detection'},None)],
    'plumber':[('gmail','appointment_confirmed',{'value':True,'scheduled_for':'2026-10-09T10:00:00-05:00','description':'Landlord confirmation email'},None),
               ('google_calendar','appointment_confirmed',{'value':True,'scheduled_for':'2026-10-09T10:00:00-05:00'},None)],
    'dentist':[('outlook_calendar','appointment_date',{'date':'2026-10-05'},None),
               ('confirmation_email','appointment_date',{'date':'2026-10-06'},None)],
    'after-hours':[('google_calendar','meeting_start',{'start':'2026-10-03T18:30:00-05:00','description':'Evening project meeting'},None)],
}


def configured_owner(settings):
    from dotenv import dotenv_values
    from db.scripts._common import BACKEND_ROOT
    value=os.getenv('COUNTON_DEMO_USER_ID') or dotenv_values(BACKEND_ROOT/'.env.local').get('COUNTON_DEMO_USER_ID')
    if value:return UUID(value)
    if settings.database_target=='supabase':
        print('Set COUNTON_DEMO_USER_ID to an existing, dedicated Supabase Auth user UUID without an unrelated CountOn profile.')
        raise RuntimeError('Dedicated Auth identity required')
    return LOCAL_DEMO_ID


def lock(db,owner):
    # Covers all service savepoint commits until the outer script transaction ends.
    db.execute(text("SELECT pg_advisory_xact_lock(hashtextextended(:tag,0))"),{'tag':f'{TAG}:{owner}'})


def seed(db,owner):
    from app.db.models import Profile,Expectation,Evidence,Evaluation,Notification,IntegrationConnection
    from app.schemas.expectation import ExpectationCreate
    from app.schemas.evidence import EvidenceCreate
    from app.schemas.integration import IntegrationCreate
    from app.services import expectation_service,evidence_service,evaluation_service,integration_service
    from app.repositories.audit import record
    lock(db,owner)
    profile=db.get(Profile,owner)
    if profile is not None and profile.demo_tag != TAG:
        raise RuntimeError('Refusing to alter an unrelated profile')
    if profile is None:
        profile=Profile(id=owner,display_name='Maya Chen',timezone='America/Chicago',demo_tag=TAG)
        db.add(profile);db.flush()  # real auth.users FK is enforced on Supabase
        record(db,owner,'profile',owner,'profile.created',metadata={'demo':True,'demo_tag':TAG})
        db.commit()
    for provider,kind,name,key,scopes in CONNECTIONS:
        items=list(db.scalars(select(IntegrationConnection).where(IntegrationConnection.user_id==owner,
            IntegrationConnection.external_account_id==f'demo:{key}',IntegrationConnection.connection_metadata['demo_tag'].astext==TAG)))
        if len(items)>1:raise RuntimeError('Ambiguous demo connection; no rows overwritten')
        if not items:
            integration_service.create(db,IntegrationCreate(provider=provider,connection_type=kind,display_name=name,
                external_account_id=f'demo:{key}',status='connected',scopes=scopes,
                metadata={'mock':True,'demo':True,'demo_tag':TAG}),owner)
    for key,claim,kind,metric,expected in SCENARIOS:
        items=list(db.scalars(select(Expectation).where(Expectation.user_id==owner,
            Expectation.compiler_metadata['demo_tag'].astext==TAG,Expectation.compiler_metadata['demo_key'].astext==key)))
        if len(items)>1:raise RuntimeError('Ambiguous demo expectation; no rows overwritten')
        if items:
            expectation=items[0]
        else:
            payload=dict(claim=claim,type=kind,metric=metric,evidence_sources=[row[0] for row in OBSERVATIONS[key]])
            if kind=='numeric_comparison':payload.update(comparison='less_than',baseline=142.10,materiality_threshold=0.05)
            expectation=expectation_service.create_expectation(db,ExpectationCreate(**payload),owner,
                compiler_metadata={'demo':True,'demo_tag':TAG,'demo_key':key,'mock':True})
        for index,(source,evidence_metric,value,unit) in enumerate(OBSERVATIONS[key]):
            evidence_service.add_evidence(db,expectation.id,EvidenceCreate(source=source,metric=evidence_metric,
                value=value,unit=unit,observed_at=datetime(2026,10,2,12,tzinfo=timezone.utc)+timedelta(minutes=index),
                external_event_id=f'demo:{TAG}:{key}:{index}',raw_data={'mock':True,'demo':True,'demo_tag':TAG}),owner)
        previous=evaluation_service.get_latest_evaluation(db,expectation.id,owner) if db.scalar(select(Evaluation.id).where(Evaluation.expectation_id==expectation.id).limit(1)) else None
        result=previous or evaluation_service.evaluate_expectation(db,expectation.id,owner)
        if result.result.value!=expected:raise RuntimeError('Demo scenario contract differs; no existing rows overwritten')
    db.commit()
    ids=list(db.scalars(select(Expectation.id).where(Expectation.user_id==owner,Expectation.compiler_metadata['demo_tag'].astext==TAG)))
    return dict(connections=db.scalar(select(func.count()).select_from(IntegrationConnection).where(IntegrationConnection.user_id==owner,IntegrationConnection.connection_metadata['demo_tag'].astext==TAG)),
        expectations=len(ids),evidence=db.scalar(select(func.count()).select_from(Evidence).where(Evidence.expectation_id.in_(ids))),
        evaluations=db.scalar(select(func.count()).select_from(Evaluation).where(Evaluation.expectation_id.in_(ids))),
        notifications=db.scalar(select(func.count()).select_from(Notification).where(Notification.expectation_id.in_(ids))))


def clear(db,owner):
    from app.db.models import Profile,Expectation,IntegrationConnection,AuditEvent
    from app.services import expectation_service,integration_service
    lock(db,owner)
    profile=db.get(Profile,owner)
    if profile is None:return
    if profile.demo_tag != TAG:raise RuntimeError('Refusing to clear an unrelated profile')
    expectations=list(db.scalars(select(Expectation.id).where(Expectation.user_id==owner,
        Expectation.compiler_metadata['demo'].as_boolean()==True,Expectation.compiler_metadata['demo_tag'].astext==TAG)))
    integrations=list(db.scalars(select(IntegrationConnection.id).where(IntegrationConnection.user_id==owner,
        IntegrationConnection.connection_metadata['demo'].as_boolean()==True,IntegrationConnection.connection_metadata['demo_tag'].astext==TAG)))
    for eid in expectations:expectation_service.delete_expectation(db,eid,owner)
    for iid in integrations:integration_service.delete(db,iid,owner)
    # Only backend-tagged demo audits, never another user's history or untagged history.
    db.execute(delete(AuditEvent).where(AuditEvent.user_id==owner,AuditEvent.audit_metadata['demo'].as_boolean()==True,AuditEvent.audit_metadata['demo_tag'].astext==TAG))
    remaining=any(db.scalar(select(model.id).where(model.user_id==owner).limit(1)) for model in (Expectation,IntegrationConnection,AuditEvent))
    if not remaining:
        db.delete(profile)
    db.commit()


def run(operation):
    from app.core.config import get_settings
    from app.db.session import engine
    owner=configured_owner(get_settings())
    try:
        with engine.begin() as connection:
            with Session(bind=connection,join_transaction_mode='create_savepoint',expire_on_commit=False) as db:
                return operation(db,owner)
    finally:
        engine.dispose()
