"""Grounding and privacy matrix through the real Converse parser, entirely offline."""

import json
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from botocore.exceptions import EndpointConnectionError

from app.ai.bedrock_client import BedrockClient
from app.ai.investigation_evidence import InvestigationInputError, normalize
from app.ai.mismatch_investigator import BedrockMismatchInvestigator
from app.core.config import Settings
from app.core.exceptions import EvaluationNotFoundError, ExpectationNotFoundError
from app.core.logging import StructuredFormatter
from app.schemas.evaluation import EvaluationResponse
from app.schemas.evidence import EvidenceResponse
from app.schemas.expectation import ExpectationResponse
from app.schemas.investigation import InvestigationContext
from app.services import investigator_service
from app.services.investigation_service import investigate_mismatch

NOW = datetime(2026, 10, 8, 20, tzinfo=timezone.utc)
SECRET = "private-provider-token-DO-NOT-SEND"


def inputs():
    expectation = ExpectationResponse(
        id=uuid4(),
        user_id=uuid4(),
        claim="My next electricity bill will be lower",
        type="numeric_comparison",
        metric="total_cost",
        comparison="less_than",
        baseline=142.1,
        target_value=None,
        deadline=None,
        evidence_sources=["utility_bill"],
        materiality_threshold=0.05,
        status="contradicted",
        compiler_metadata={},
        created_at=NOW - timedelta(days=1),
        updated_at=NOW,
    )
    evidence = []
    for i, (metric, value, unit) in enumerate(
        [
            ("total_cost", {"amount": 162}, "USD"),
            ("energy_usage_change", {"percentage": -18}, "percent"),
            ("rate_change", {"percentage": 22}, "percent"),
        ]
    ):
        evidence.append(
            EvidenceResponse(
                id=UUID(int=i + 1),
                expectation_id=expectation.id,
                external_event_id=None,
                source="utility_bill",
                metric=metric,
                value=value,
                unit=unit,
                observed_at=NOW - timedelta(hours=1),
                confidence=1,
                raw_data={},
                created_at=NOW - timedelta(minutes=1),
            )
        )
    evaluation = EvaluationResponse(
        id=uuid4(),
        expectation_id=expectation.id,
        result="MISMATCH",
        expected={"metric": "total_cost", "comparison": "less_than", "target": 142.1},
        observed={
            "metric": "total_cost",
            "evidence_id": str(evidence[0].id),
            "value": 162,
        },
        confidence=1,
        reasoning={
            "materiality_threshold": 0.05,
            "tolerance_kind": "relative",
            "reason": "observed_value_failed_comparison",
        },
        created_at=NOW,
    )
    return expectation, evaluation, evidence


def facts(data):
    expectation, evaluation, evidence = data
    return normalize(
        expectation=expectation,
        evaluation=evaluation,
        evidence=evidence,
        context=None,
        max_evidence=6,
    )


def draft(data, *, factors=None, kind="possible_contribution"):
    normalized = facts(data)
    return {
        "expected": normalized.expected.model_dump(mode="json"),
        "observed": normalized.observed.model_dump(mode="json"),
        "summary_kind": kind,
        "key_factors": factors
        if factors is not None
        else [
            {
                "kind": "observed_measurement",
                "evidence_refs": ["E1"],
                "values": {"E1": 162},
            },
            {
                "kind": "possible_rate_offset",
                "evidence_refs": ["E1", "E2", "E3"],
                "values": {"E1": 162, "E2": -18, "E3": 22},
            },
        ],
    }


def adapter(*outputs, enabled=True, **settings_changes):
    runtime = Mock()
    runtime.converse.side_effect = [
        output
        if isinstance(output, Exception)
        else {
            "output": {
                "message": {
                    "role": "assistant",
                    "content": [
                        {
                            "text": output
                            if isinstance(output, str)
                            else json.dumps(output)
                        }
                    ],
                }
            },
            "stopReason": "end_turn",
        }
        for output in outputs
    ]
    settings = Settings(
        _env_file=None,
        database_target="local",
        local_database_url="postgresql+psycopg://localhost/test",
        bedrock_enabled=enabled,
        aws_region="us-east-2",
        bedrock_model_id="test-model",
        bedrock_max_retries=0,
        **settings_changes,
    )
    return BedrockMismatchInvestigator(
        client=BedrockClient(settings, runtime=runtime, sleep=Mock()), settings=settings
    ), runtime


def execute(data, investigator, context=None):
    expectation, evaluation, evidence = data
    return investigate_mismatch(
        expectation=expectation,
        evaluation=evaluation,
        evidence=evidence,
        context=context,
        investigator=investigator,
    )


def test_electricity_strong_grounded_demo():
    data = inputs()
    investigator, runtime = adapter(draft(data))
    result = execute(data, investigator)
    assert result.generation == "bedrock"
    assert (
        "< $142.10" in result.summary
        and "$162.00" in result.summary
        and "5%" in result.summary
    )
    assert (
        "18%" in result.key_factors[1].description
        and "22%" in result.key_factors[1].description
    )
    assert "could have contributed" in result.key_factors[1].description
    assert "do not establish" in result.key_factors[1].description
    assert [item.ref for item in result.evidence_refs] == ["E1", "E2", "E3"]
    assert result.confidence == 0.5 and not result.insufficient_evidence
    assert runtime.converse.call_args.kwargs["inferenceConfig"]["temperature"] == 0


@pytest.mark.parametrize("count", [0, 1, 2])
def test_sparse_evidence_no_invented_cause(count):
    data = inputs()
    data[2][:] = data[2][:count]
    output = draft(data, factors=[], kind="insufficient_cause")
    investigator, runtime = adapter(output)
    result = execute(data, investigator)
    assert "enough supporting evidence" in result.summary
    assert result.expected.target == 142.1 and result.observed.value == 162
    assert runtime.converse.call_count == (0 if count == 0 else 1)
    assert "causal certainty" in result.confidence_note
    assert result.insufficient_evidence and result.confidence == 0


@pytest.mark.parametrize("result", ["MATCH", "UNKNOWN"])
def test_refuses_non_mismatch(result):
    data = inputs()
    data[1].result = result
    investigator, runtime = adapter()
    with pytest.raises(InvestigationInputError):
        execute(data, investigator)
    runtime.converse.assert_not_called()


@pytest.mark.parametrize(
    "change",
    [
        "unknown_ref",
        "numeric",
        "expected",
        "observed",
        "result",
        "fabricated",
        "external",
        "chain",
        "description",
        "wrong_metric",
        "duplicate_ref",
        "missing_value",
    ],
)
def test_unsupported_output_falls_back(change):
    data = inputs()
    output = draft(data)
    if change == "unknown_ref":
        output["key_factors"][0]["evidence_refs"] = ["E99"]
    elif change == "numeric":
        output["key_factors"][0]["values"]["E1"] = 999
    elif change == "expected":
        output["expected"]["target"] = 100
    elif change == "observed":
        output["observed"]["value"] = 100
    elif change == "result":
        output["result"] = "MATCH"
    elif change in ("fabricated", "external"):
        output["key_factors"][0]["kind"] = "fuel_surcharge"
    elif change == "chain":
        output["reasoning"] = "secret chain"
    elif change == "description":
        output["key_factors"][0]["description"] = "Provider added a fuel surcharge"
    elif change == "wrong_metric":
        output["key_factors"][0]["kind"] = "usage_change"
    elif change == "duplicate_ref":
        output["key_factors"][0]["evidence_refs"] = ["E1", "E1"]
    elif change == "missing_value":
        output["key_factors"][0]["values"] = {}
    investigator, runtime = adapter(output, output)
    result = execute(data, investigator)
    assert result.generation == "deterministic"
    assert result.expected.target == 142.1 and result.observed.value == 162
    assert not result.key_factors
    assert "fuel surcharge" not in result.model_dump_json()
    assert runtime.converse.call_count <= 2


def test_repair_succeeds():
    data = inputs()
    investigator, runtime = adapter("invalid json", draft(data))
    assert execute(data, investigator).generation == "bedrock"
    assert runtime.converse.call_count == 2


def test_repair_fails():
    data = inputs()
    investigator, runtime = adapter("invalid json", "still invalid")
    assert execute(data, investigator).generation == "deterministic"
    assert runtime.converse.call_count == 2


def test_bedrock_unavailable_fallback():
    investigator, _runtime = adapter(
        EndpointConnectionError(endpoint_url="https://private.test")
    )
    result = execute(inputs(), investigator)
    assert result.generation == "deterministic"
    assert "MISMATCH" in result.summary
    assert "private.test" not in result.model_dump_json()


def test_disabled_fallback_no_network():
    investigator, runtime = adapter(enabled=False)
    assert execute(inputs(), investigator).generation == "deterministic"
    runtime.converse.assert_not_called()


@pytest.mark.parametrize("confidence", [1.0, 0.1])
def test_conflicts_surface_without_choosing_cause(confidence):
    data = inputs()
    data[2][0].confidence = confidence
    other = data[2][0].model_copy(update={"id": uuid4(), "value": {"amount": 170}})
    data[2].append(other)
    output = draft(
        data,
        kind="insufficient_cause",
        factors=[
            {
                "kind": "conflicting_observations",
                "evidence_refs": ["E1", "E2"],
                "values": {"E1": 162, "E2": 170},
            }
        ],
    )
    investigator, _ = adapter(output)
    result = execute(data, investigator)
    assert result.generation == "bedrock"
    assert "conflicting" in " ".join(result.caveats)
    assert result.observed.value == 162
    assert result.key_factors[0].strength == "conflicting"
    assert result.insufficient_evidence and result.confidence <= 0.25
    assert result.confidence < min(0.5, confidence)
    assert "conflicting" in result.summary


def test_conflict_disallows_possible_cause():
    data = inputs()
    data[2].append(
        data[2][2].model_copy(update={"id": uuid4(), "value": {"percentage": 5}})
    )
    investigator, _ = adapter(draft(data))
    result = execute(data, investigator)
    assert result.generation == "deterministic" and "conflicting" in " ".join(
        result.caveats
    )


def test_private_data_never_sent_or_logged(caplog):
    data = inputs()
    data[0].claim = SECRET
    data[0].compiler_metadata = {"token": SECRET}
    for item in data[2]:
        item.raw_data = {"body": SECRET * 10000}
        item.source = SECRET
        item.external_event_id = SECRET
        item.value["payload"] = SECRET
    data[1].reasoning["private"] = SECRET
    investigator, runtime = adapter(draft(data))
    with caplog.at_level(logging.INFO):
        result = execute(data, investigator)
    wire = json.dumps(runtime.converse.call_args.kwargs)
    for private in [SECRET, str(data[0].id), str(data[0].user_id), str(data[1].id)]:
        assert private not in wire
    assert SECRET not in caplog.text and SECRET not in result.model_dump_json()
    assert "raw_data" not in wire and "Authorization" not in wire
    formatter = StructuredFormatter()
    assert all(SECRET not in formatter.format(record) for record in caplog.records)


@pytest.mark.parametrize("boundary", ["principal", "expectation", "evaluation"])
def test_ownership_boundary(boundary):
    data = inputs()
    context = None
    if boundary == "principal":
        context = InvestigationContext(authenticated_user_id=uuid4())
    elif boundary == "expectation":
        data[2][0].expectation_id = uuid4()
    else:
        data[1].expectation_id = uuid4()
    investigator, runtime = adapter()
    with pytest.raises(InvestigationInputError):
        execute(data, investigator, context)
    runtime.converse.assert_not_called()


def test_read_only_input_and_output_no_chain_of_thought():
    data = inputs()
    before = [item.model_dump_json() for item in [data[0], data[1], *data[2]]]
    investigator, _ = adapter(draft(data))
    result = execute(data, investigator)
    assert before == [item.model_dump_json() for item in [data[0], data[1], *data[2]]]
    assert not any(
        key in result.model_dump()
        for key in ("reasoning", "analysis", "chain_of_thought")
    )


def test_historical_snapshot_wins_over_current_expectation():
    data = inputs()
    data[0].baseline = 999
    data[0].materiality_threshold = 0.9
    investigator, _ = adapter(draft(data))
    result = execute(data, investigator)
    assert (
        result.expected.target == 142.1
        and result.expected.materiality_threshold == 0.05
    )
    assert result.evaluator_reason == "observed_value_failed_comparison"


def test_newer_evidence_does_not_replace_recorded_measurement():
    data = inputs()
    data[2].append(
        data[2][0].model_copy(
            update={
                "id": uuid4(),
                "value": {"amount": 130},
                "observed_at": NOW,
                "created_at": NOW + timedelta(seconds=1),
            }
        )
    )
    investigator, _ = adapter(draft(data))
    assert execute(data, investigator).observed.value == 162
    data[2][:] = data[2][1:]
    investigator, runtime = adapter()
    result = execute(data, investigator)
    assert result.generation == "deterministic" and result.observed.value == 162
    runtime.converse.assert_not_called()


def test_latest_contributor_observed_not_ingested():
    data = inputs()
    data[2].append(
        data[2][1].model_copy(
            update={
                "id": uuid4(),
                "value": {"percentage": 99},
                "observed_at": NOW - timedelta(days=1),
                "created_at": NOW,
            }
        )
    )
    assert facts(data).evidence[1].value == -18


def test_deterministic_selection_with_long_unrelated_input():
    data = inputs()
    for i in range(200):
        data[2].append(
            data[2][0].model_copy(
                update={
                    "id": uuid4(),
                    "metric": "unrelated",
                    "value": {"amount": i},
                    "raw_data": {"body": SECRET * 100},
                }
            )
        )
    first = facts(data)
    data[2].reverse()
    assert first == facts(data)
    investigator, runtime = adapter(draft(data))
    execute(data, investigator)
    assert len(json.dumps(runtime.converse.call_args.kwargs)) < 15000


def test_evidence_limit_and_truncation_caveat():
    data = inputs()
    investigator, runtime = adapter(
        draft(data, factors=[], kind="insufficient_cause"), investigator_max_evidence=1
    )
    result = execute(data, investigator)
    assert len(result.evidence_refs) == 1
    assert "bounded selection" in " ".join(result.caveats)
    assert (
        len(
            json.loads(
                runtime.converse.call_args.kwargs["messages"][0]["content"][0]["text"]
            )["evidence"]
        )
        == 1
    )


def test_tiny_prompt_budget_skips_aws():
    investigator, runtime = adapter(investigator_max_prompt_bytes=2048)
    assert execute(inputs(), investigator).generation == "deterministic"
    runtime.converse.assert_not_called()


@pytest.mark.parametrize("unit", ["USD", "untrusted unit"])
def test_non_percentage_contributor_not_relabelled(unit):
    data = inputs()
    data[2][1].unit = unit
    assert "energy_usage_change" not in [item.metric for item in facts(data).evidence]


def test_boolean_snapshot_preserved():
    data = inputs()
    data[1].expected = {"metric": "door_closed", "value": True}
    data[1].observed = {
        "metric": "door_closed",
        "value": False,
        "evidence_id": str(data[2][0].id),
    }
    data[2][:] = [
        data[2][0].model_copy(
            update={"metric": "door_closed", "value": {"value": False}, "unit": None}
        )
    ]
    output = draft(
        data,
        factors=[
            {
                "kind": "observed_measurement",
                "evidence_refs": ["E1"],
                "values": {"E1": False},
            }
        ],
        kind="insufficient_cause",
    )
    investigator, _ = adapter(output)
    result = execute(data, investigator)
    assert result.expected.target is True and result.observed.value is False
    assert "true" in result.summary and "false" in result.summary


def test_boolean_is_not_zero_grounding():
    data = inputs()
    output = draft(data)
    output["observed"]["value"] = False
    investigator, _ = adapter(output)
    assert execute(data, investigator).generation == "deterministic"


def test_absolute_threshold_not_rendered_as_percentage():
    data = inputs()
    data[1].expected["target"] = 0
    data[1].reasoning["tolerance_kind"] = "absolute"
    investigator, _ = adapter(draft(data))
    result = execute(data, investigator)
    assert "0.05 (absolute)" in result.summary and "5%" not in result.summary


def test_conflict_flag_survives_truncation():
    data = inputs()
    data[2].append(
        data[2][0].model_copy(update={"id": uuid4(), "value": {"amount": 170}})
    )
    investigator, _ = adapter(
        draft(data, factors=[], kind="insufficient_cause"), investigator_max_evidence=1
    )
    assert "conflicting" in " ".join(execute(data, investigator).caveats)


def test_duplicate_id_with_different_value_rejected():
    data = inputs()
    data[2].append(data[2][0].model_copy(update={"value": {"amount": 170}}))
    investigator, runtime = adapter()
    with pytest.raises(InvestigationInputError):
        execute(data, investigator)
    runtime.converse.assert_not_called()


@pytest.mark.parametrize(
    "comparison,target", [("greater_than", 200), ("less_than", 200), ("equal", 142.1)]
)
def test_rate_contribution_does_not_explain_wrong_direction(comparison, target):
    data = inputs()
    data[1].expected.update(comparison=comparison, target=target)
    investigator, _ = adapter(draft(data))
    assert execute(data, investigator).generation == "deterministic"


def test_boolean_without_expected_metric_uses_recorded_observed_metric():
    data = inputs()
    data[0].type = "boolean"
    data[1].expected = {"metric": None, "value": True}
    data[1].observed = {
        "metric": "door_closed",
        "value": False,
        "evidence_id": str(data[2][0].id),
    }
    data[2][:] = [
        data[2][0].model_copy(
            update={"metric": "door_closed", "value": {"value": False}, "unit": None}
        )
    ]
    output = draft(
        data,
        factors=[
            {
                "kind": "observed_measurement",
                "evidence_refs": ["E1"],
                "values": {"E1": False},
            }
        ],
        kind="insufficient_cause",
    )
    investigator, _ = adapter(output)
    result = execute(data, investigator)
    assert result.generation == "bedrock" and result.expected.metric is None
    assert result.observed.value is False


def test_snapshot_boolean_target_cannot_be_changed_to_numeric_one():
    data = inputs()
    data[1].expected["target"] = True
    output = draft(data)
    output["expected"]["target"] = 1
    investigator, _ = adapter(output)
    assert execute(data, investigator).generation == "deterministic"


def owned_reads(monkeypatch, data):
    expectation, evaluation, evidence = data
    load_expectation = Mock(return_value=expectation)
    load_evaluation = Mock(return_value=evaluation)
    load_evidence = Mock(return_value=evidence)
    monkeypatch.setattr(
        investigator_service.expectation_service, "get_expectation", load_expectation
    )
    monkeypatch.setattr(
        investigator_service.evaluation_service,
        "get_latest_evaluation",
        load_evaluation,
    )
    monkeypatch.setattr(
        investigator_service.evidence_repository,
        "investigation_evidence",
        load_evidence,
    )
    return load_expectation, load_evaluation, load_evidence


def test_owned_service_uses_latest_evaluation_and_bounded_owned_evidence(monkeypatch):
    data = inputs()
    loads = owned_reads(monkeypatch, data)
    investigator, runtime = adapter(draft(data))
    db = Mock()
    result = investigator_service.investigate_expectation_mismatch(
        db, data[0].id, data[0].user_id, investigator=investigator
    )
    assert result.generation == "bedrock" and result.observed.value == 162
    loads[0].assert_called_once_with(db, data[0].id, data[0].user_id)
    loads[1].assert_called_once_with(db, data[0].id, data[0].user_id)
    loads[2].assert_called_once_with(db, data[0].id, data[1])
    runtime.converse.assert_called_once()
    db.commit.assert_not_called()
    db.add.assert_not_called()


@pytest.mark.parametrize("result", ["MATCH", "UNKNOWN"])
def test_owned_service_latest_non_mismatch_never_loads_evidence_or_calls_ai(
    monkeypatch, result
):
    data = inputs()
    data[1].result = result
    loads = owned_reads(monkeypatch, data)
    injected = Mock()
    with pytest.raises(InvestigationInputError):
        investigator_service.investigate_expectation_mismatch(
            Mock(), data[0].id, data[0].user_id, investigator=injected
        )
    loads[2].assert_not_called()
    injected.investigate_mismatch.assert_not_called()


def test_owned_service_denies_another_user_before_evidence_or_ai(monkeypatch):
    data = inputs()
    loads = owned_reads(monkeypatch, data)
    loads[0].side_effect = ExpectationNotFoundError(data[0].id)
    injected = Mock()
    with pytest.raises(ExpectationNotFoundError):
        investigator_service.investigate_expectation_mismatch(
            Mock(), data[0].id, uuid4(), investigator=injected
        )
    loads[1].assert_not_called()
    loads[2].assert_not_called()
    injected.investigate_mismatch.assert_not_called()


def test_owned_service_no_evaluation_never_loads_evidence_or_calls_ai(monkeypatch):
    data = inputs()
    loads = owned_reads(monkeypatch, data)
    loads[1].side_effect = EvaluationNotFoundError(data[0].id)
    injected = Mock()
    with pytest.raises(EvaluationNotFoundError):
        investigator_service.investigate_expectation_mismatch(
            Mock(), data[0].id, data[0].user_id, investigator=injected
        )
    loads[2].assert_not_called()
    injected.investigate_mismatch.assert_not_called()


@pytest.mark.parametrize("field", ["result", "outcome", "verdict"])
def test_model_cannot_supply_any_verdict_field(field):
    data = inputs()
    output = draft(data)
    output[field] = "MISMATCH"
    investigator, _ = adapter(output, output)
    result = execute(data, investigator)
    assert result.generation == "deterministic"
    assert result.result == "MISMATCH"
    assert result.confidence == 0 and result.insufficient_evidence


def test_demo_numbers_are_data_not_constants():
    data = inputs()
    data[2][1].value = {"percentage": -7}
    data[2][2].value = {"percentage": 11}
    output = draft(data)
    output["key_factors"][1]["values"].update(E2=-7, E3=11)
    investigator, _ = adapter(output)
    result = execute(data, investigator)
    assert result.generation == "bedrock"
    assert "7%" in result.key_factors[1].description
    assert "11%" in result.key_factors[1].description
    assert "18%" not in result.model_dump_json()
    assert "22%" not in result.model_dump_json()


def test_lower_evidence_confidence_limits_support_indicator():
    data = inputs()
    data[2][1].confidence = 0.1
    investigator, _ = adapter(draft(data))
    result = execute(data, investigator)
    assert result.confidence == 0.1


@pytest.mark.integration
def test_owned_service_database_latest_result_and_ownership(
    client, db, users, numeric_payload, bill_payload
):
    from app.services import evaluation_service

    identity = UUID(
        client.post("/api/v1/expectations", json=numeric_payload).json()["id"]
    )
    assert (
        client.post(
            f"/api/v1/expectations/{identity}/evidence", json=bill_payload
        ).status_code
        == 201
    )
    evaluation_service.evaluate_expectation(db, identity, users[0].id)
    investigator, runtime = adapter(enabled=False)
    result = investigator_service.investigate_expectation_mismatch(
        db, identity, users[0].id, investigator=investigator
    )
    assert result.result == "MISMATCH" and result.insufficient_evidence
    with pytest.raises(ExpectationNotFoundError):
        investigator_service.investigate_expectation_mismatch(
            db, identity, users[1].id, investigator=investigator
        )
    updated = dict(
        bill_payload, value={"amount": 130}, observed_at="2026-10-03T12:00:00Z"
    )
    assert (
        client.post(
            f"/api/v1/expectations/{identity}/evidence", json=updated
        ).status_code
        == 201
    )
    matched = evaluation_service.evaluate_expectation(db, identity, users[0].id)
    assert matched.result == "MATCH"
    # Savepoint isolation shares PostgreSQL now() across both evaluations.
    # Explicit chronology avoids interpreting a random UUID tie as a newer result.
    matched.created_at += timedelta(seconds=1)
    db.flush()
    with pytest.raises(InvestigationInputError):
        investigator_service.investigate_expectation_mismatch(
            db, identity, users[0].id, investigator=investigator
        )
    runtime.converse.assert_not_called()
