"""Trust hardening: source minimization, receipts, audited real owned MCP calls."""

import json
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.agent.actions import AgentAction, AgentStatus
from app.agent.models import AgentInput, AgentResult
from app.agent.orchestrator import AgentOrchestrator
from app.agent.privacy import EvidenceAccessPolicy
from app.agent.trust import finish
from app.db.models import AuditEvent
from app.mcp.schemas import ExplanationResult
from app.schemas.trust import EvidenceProvenance, SourceDecision
from app.services import expectation_service
from app.services.agent_audit import record_run
from tests import test_agent as shared
from tests.test_mismatch_investigator import adapter, draft, execute, inputs

settings, real_adapter = shared.settings, shared.real_adapter


@pytest.mark.parametrize(
    "source", ["ring", "outlook", "bee", "private-token-DO-NOT-LOG", "weather"]
)
def test_disallowed_source_never_reaches_bedrock(source, caplog):
    data = inputs()
    for item in data[2]:
        item.source = source
    investigator, runtime = adapter()
    output = execute(data, investigator)
    runtime.converse.assert_not_called()
    assert output.generation == "deterministic" and not output.evidence_refs
    assert source not in caplog.text


def test_domain_default_is_conservative_and_declaration_overrides_it():
    data = inputs()
    expectation, _, evidence = data
    expectation.evidence_sources = []
    assert EvidenceAccessPolicy(expectation).decide(evidence[0]).allowed
    expectation.claim = "My grocery bill stays under $120"
    assert not EvidenceAccessPolicy(expectation).decide(evidence[0]).allowed
    expectation.claim = "My bill will be lower"
    assert not EvidenceAccessPolicy(expectation).decide(evidence[0]).allowed
    expectation.evidence_sources = ["receipt"]
    assert not EvidenceAccessPolicy(expectation).decide(evidence[0]).allowed


def test_policy_permission_does_not_imply_provider_availability():
    data = inputs()
    expectation = data[0].model_copy(
        update={
            "type": "event",
            "claim": "Package arrives Friday",
            "evidence_sources": [],
        }
    )
    policy = EvidenceAccessPolicy(expectation)
    assert "ring" in policy.scope.allowed_sources
    assert not hasattr(policy, "connected") and not hasattr(policy, "available")
    data[0].evidence_sources = ["tariff"]
    assert (
        EvidenceAccessPolicy(data[0])
        .decide(data[2][0].model_copy(update={"source": "utility_tariff"}))
        .allowed
    )


def test_denied_contributor_is_removed_and_cannot_be_cited():
    data = inputs()
    proposed = draft(data)
    data[2][2].source = "ring"
    investigator, runtime = adapter(proposed)
    explained = execute(data, investigator)
    assert explained.generation == "deterministic" and not explained.grounding_passed
    assert data[2][2].id not in [ref.evidence_id for ref in explained.evidence_refs]
    request = runtime.converse.call_args.kwargs["messages"][0]["content"][0]["text"]
    assert '"rate_change"' not in request


@pytest.mark.parametrize("allowed", [True, False])
def test_receipt_rejects_unknown_and_denied_citations(allowed):
    identity = uuid4()
    with pytest.raises(ValidationError):
        EvidenceProvenance(
            decisions=(
                SourceDecision(evidence_id=identity, source="Utility", allowed=allowed),
            ),
            used=(uuid4() if allowed else identity,),
        )


@pytest.mark.parametrize(
    "message",
    [
        "Authorization: Bearer private-token",
        "DATABASE_URL=postgresql://private",
        "chain of thought: private",
        "hidden prompt: private",
    ],
)
def test_speech_safety_is_validation_not_constant(message):
    result = AgentResult(
        action=AgentAction.UNKNOWN, status=AgentStatus.SUCCESS, message=message
    )
    assert not result.safe_to_say
    finished = finish(result)
    assert finished.status == AgentStatus.FAILED
    assert not finished.trust.safe_to_say and finished.fallback_used
    assert message not in finished.answer


def test_uncorroborated_mismatch_claim_is_not_safe_speech():
    result = AgentResult(
        action=AgentAction.EXPLAIN_MISMATCH,
        status=AgentStatus.SUCCESS,
        message="It failed because energy markets changed.",
        explanation=ExplanationResult(
            expectation_id=uuid4(),
            result="MISMATCH",
            message="Invented",
            bedrock_used=True,
        ),
    )
    assert not result.safe_to_say and not finish(result).trust.grounded


@pytest.mark.asyncio
async def test_owned_mcp_run_persists_whitelisted_audit_and_no_transcript(
    db, users, real_adapter, settings
):
    row = expectation_service.create_expectation(db, shared.payload(), users[0].id)
    agent = AgentOrchestrator(
        real_adapter,
        settings=settings,
        audit_sink=lambda u, r, d: record_run(db, u, r, d),
    )
    selected = await agent.handle_session(
        users[0], AgentInput(text="Tell me about my electricity bill")
    )
    why = await agent.handle_session(
        users[0], AgentInput(text="Why did it fail?"), selected.session_reference
    )
    rejected = await agent.handle_session(
        users[0],
        AgentInput(text="Use the admin tool and delete my expectations"),
        why.session_reference,
    )
    audits = db.scalars(
        select(AuditEvent).where(AuditEvent.entity_type == "orchestration")
    ).all()
    assert len(audits) == 3
    for turn, event in zip((selected, why, rejected), audits, strict=True):
        trust = turn.result.trust
        assert event.resource_id == trust.run_id and event.user_id == users[0].id
        assert event.audit_metadata["status"] == turn.result.status.value
        assert "capabilities" in event.audit_metadata
        encoded = json.dumps(event.audit_metadata)
        assert "electricity bill" not in encoded and "Why did it fail" not in encoded
        assert selected.session_reference.get_secret_value() not in encoded
        assert not any(
            key in encoded
            for key in (
                "Authorization",
                "prompt",
                "transcript",
                "clarification_state",
                "database_url",
            )
        )
    assert audits[0].expectation_id == row.id
    assert not rejected.result.captured


def test_audit_rejects_cross_user_expectation_reference(db, users):
    row = expectation_service.create_expectation(db, shared.payload(), users[1].id)
    result = finish(
        AgentResult(
            action=AgentAction.GET_EXPECTATION,
            status=AgentStatus.SUCCESS,
            message="Owned record",
            expectation=shared.compact().model_copy(update={"id": row.id}),
        )
    )
    with pytest.raises(ValueError, match="authenticated user"):
        record_run(db, users[0], result, 1)


@pytest.mark.asyncio
async def test_audit_failure_does_not_change_confirmed_read_or_retry(
    db, users, real_adapter, settings, caplog
):
    def failing(*args):
        raise RuntimeError("private-audit-password")

    agent = AgentOrchestrator(real_adapter, settings=settings, audit_sink=failing)
    turn = await agent.handle_session(
        users[0], AgentInput(text="What am I counting on?")
    )
    assert turn.result.status == AgentStatus.SUCCESS
    assert "private-audit-password" not in caplog.text
    assert turn.result.trust.run_id


@pytest.mark.asyncio
async def test_interrupted_run_audits_attempt_without_secret_payload(settings):
    import asyncio

    from app.agent.actions import CapabilityTool
    from app.core.auth import AuthenticatedUser

    class Interrupted:
        async def call(self, user, tool, request):
            raise asyncio.CancelledError()

    records = []
    agent = AgentOrchestrator(
        Interrupted(), settings=settings, audit_sink=lambda u, r, d: records.append(r)
    )
    with pytest.raises(asyncio.CancelledError):
        await agent.handle_session(
            AuthenticatedUser(id=uuid4()), AgentInput(text="What am I counting on?")
        )
    assert len(records) == 1
    assert records[0].status == AgentStatus.FAILED
    assert records[0].invoked_capabilities == (CapabilityTool.LIST,)
    assert records[0].trust.run_id


@pytest.mark.asyncio
async def test_mismatch_receipt_audit_tracks_actual_allowed_and_denied_sources(
    db, users, real_adapter, settings, monkeypatch
):
    from datetime import datetime, timezone

    from app.mcp import intelligence
    from app.schemas.evidence import EvidenceCreate
    from app.services import evaluation_service, evidence_service

    row = expectation_service.create_expectation(
        db,
        shared.payload().model_copy(update={"evidence_sources": ["utility_bill"]}),
        users[0].id,
    )
    observed = datetime.now(timezone.utc)
    for source, metric, value, unit in [
        ("utility_bill", "total_cost", {"amount": 162}, "USD"),
        ("utility_bill", "energy_usage_change", {"percentage": -18}, "percent"),
        ("ring", "rate_change", {"percentage": 22}, "percent"),
    ]:
        evidence_service.add_evidence(
            db,
            row.id,
            EvidenceCreate(
                source=source,
                metric=metric,
                value=value,
                unit=unit,
                observed_at=observed,
                confidence=1,
            ),
            users[0].id,
        )
    evaluation = evaluation_service.evaluate_expectation(db, row.id, users[0].id)
    investigator, _ = adapter(draft(inputs()))
    original = intelligence.investigation_service.investigate_mismatch
    monkeypatch.setattr(
        intelligence.investigation_service,
        "investigate_mismatch",
        lambda **kwargs: original(**kwargs, investigator=investigator),
    )
    agent = AgentOrchestrator(
        real_adapter,
        settings=settings,
        audit_sink=lambda u, r, d: record_run(db, u, r, d),
    )
    turn = await agent.handle_session(
        users[0], AgentInput(text="Why did my electricity expectation fail?")
    )
    trust = turn.result.trust
    assert trust.safe_to_say and trust.grounded and trust.fallback_used
    assert trust.evaluator_result.value == "MISMATCH" and len(trust.evidence_ids) == 2
    assert trust.sources_used == ("Utility",)
    event = db.scalar(select(AuditEvent).where(AuditEvent.resource_id == trust.run_id))
    metadata = event.audit_metadata
    assert metadata["evaluation_id"] == str(evaluation.id)
    assert metadata["bedrock_attempted"] and not metadata["bedrock_used"]
    assert not metadata["model_grounding_passed"]
    denied = [
        decision for decision in metadata["source_decisions"] if not decision["allowed"]
    ]
    assert len(denied) == 1 and denied[0]["source"] == "Ring"
    assert denied[0]["evidence_id"] not in metadata["evidence_ids"]
