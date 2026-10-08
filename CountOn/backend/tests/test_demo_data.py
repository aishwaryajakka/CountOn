"""Demo scripts reuse only tagged rows and preserve other data, even same owner."""
from uuid import uuid4
import pytest
from sqlalchemy import func,select
from app.db.models import AuditEvent,Evidence,Evaluation,Expectation,IntegrationConnection,Notification,Profile
from app.schemas.expectation import ExpectationCreate
from app.schemas.integration import IntegrationCreate
from app.services import expectation_service,integration_service
from db.scripts._demo import seed,clear,TAG

pytestmark=pytest.mark.integration


def counts(db):return [db.scalar(select(func.count()).select_from(model)) for model in (Profile,IntegrationConnection,Expectation,Evidence,Evaluation,Notification,AuditEvent)]


def test_seed_repeat_and_clear_preserves_unrelated_data(db,numeric_payload):
    owner=uuid4()
    before=counts(db)
    first=seed(db,owner)
    assert first=={'connections':6,'expectations':5,'evidence':10,'evaluations':5,'notifications':1}
    after=counts(db)
    assert seed(db,owner)==first
    assert counts(db)==after
    other=expectation_service.create_expectation(db,ExpectationCreate(**numeric_payload),owner)
    connection=integration_service.create(db,IntegrationCreate(provider='google',connection_type='calendar',display_name='Keep this real metadata'),owner)
    clear(db,owner)
    assert db.get(Expectation,other.id) is not None
    assert db.get(IntegrationConnection,connection.id) is not None
    assert db.get(Profile,owner) is not None
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.resource_id==other.id))==1
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.resource_id==connection.id))==1
    assert db.scalar(select(func.count()).select_from(Expectation).where(Expectation.compiler_metadata['demo_tag'].astext==TAG))==0
    assert db.scalar(select(func.count()).select_from(AuditEvent).where(AuditEvent.audit_metadata['demo_tag'].astext==TAG))==0
    clear(db,owner)  # safe repeat; unrelated rows still remain
    assert db.get(Expectation,other.id) is not None


def test_clear_removes_demo_only_profile(db):
    owner=uuid4();before=counts(db)
    seed(db,owner);clear(db,owner)
    assert counts(db)==before
    assert db.get(Profile,owner) is None


def test_seed_refuses_existing_untagged_profile(db,users):
    before=counts(db)
    with pytest.raises(RuntimeError,match='unrelated profile'):seed(db,users[0].id)
    assert counts(db)==before


def test_failed_seed_rolls_back_service_commits(postgres_engine,monkeypatch):
    from types import SimpleNamespace
    from sqlalchemy.orm import Session
    from app.db import session as application_database
    from app.core import config
    from app.services import evidence_service
    from db.scripts._demo import run
    owner=uuid4()
    monkeypatch.setenv('COUNTON_DEMO_USER_ID',str(owner))
    monkeypatch.setattr(application_database,'engine',postgres_engine)
    monkeypatch.setattr(config,'get_settings',lambda:SimpleNamespace(database_target='local'))
    def fail(*args,**kwargs):raise RuntimeError('Injected seed failure after committed service writes')
    monkeypatch.setattr(evidence_service,'add_evidence',fail)
    with pytest.raises(RuntimeError,match='Injected seed failure'):run(seed)
    with Session(postgres_engine) as db:
        assert db.get(Profile,owner) is None
        for model in (Expectation,IntegrationConnection,AuditEvent):
            assert db.scalar(select(func.count()).select_from(model).where(model.user_id==owner))==0
