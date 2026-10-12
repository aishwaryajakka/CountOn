"""Offline extraction cache and trusted Bedrock operation budgets."""

import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest

from app.ai.bedrock_client import BedrockClient, call_gate
from app.ai.exceptions import BedrockTimeoutError, BedrockValidationError
from app.integrations.extraction_cache import ExtractionCache
from tests.test_bedrock import Output, call, response, settings


def test_cache_scoped_versioned_bounded_and_immutable():
    clock = [0]
    cache = ExtractionCache(capacity=2, ttl_seconds=10, clock=lambda: clock[0])
    normalizer = Mock(return_value={"amount": 162})
    scope = ("owner", "connection", "generation", "scope")
    first = cache.extract(scope, "message", "email", {"body": "Total 162"}, normalizer)
    first["amount"] = 0
    assert (
        cache.extract(scope, "message", "email", {"body": "Total 162"}, normalizer)[
            "amount"
        ]
        == 162
    )
    assert normalizer.call_count == 1
    for changed in [("foreign", *scope[1:]), (*scope[:2], "new", scope[-1])]:
        cache.extract(changed, "message", "email", {"body": "Total 162"}, normalizer)
    assert normalizer.call_count == 3 and len(cache._entries) == 2
    clock[0] = 11
    cache.extract(scope, "message", "email", {"body": "Total 162"}, normalizer)
    assert normalizer.call_count == 4
    assert all("Total" not in key for key in cache._entries)


def test_cache_without_auth_context_never_reuses_result():
    cache, normalizer = ExtractionCache(), Mock(return_value={})
    for _ in range(2):
        cache.extract(None, "id", "email", {}, normalizer)
    assert normalizer.call_count == 2 and not cache._entries


def test_cache_invalidates_content_scope_and_extractor_version():
    cache, normalize = ExtractionCache(), Mock(return_value={"amount": 162})
    scope = ("owner", "connection", "generation", "scopes")
    cache.extract(scope, "mail", "email", {"body": "A"}, normalize)
    cache.extract(scope, "mail", "email", {"body": "B"}, normalize)
    cache.extract(
        scope, "mail", "email", {"body": "B"}, normalize, extractor_version="v-next"
    )
    cache.extract(
        (*scope[:3], "revoked-scope"), "mail", "email", {"body": "B"}, normalize
    )
    assert normalize.call_count == 4
    cache.close()


def test_idle_cache_physically_removes_private_facts_at_expiry():
    clock, timers = [0], []

    class Timer:
        def __init__(self, delay, callback):
            self.callback = callback
            timers.append(self)

        def start(self):
            pass

        def cancel(self):
            pass

    cache = ExtractionCache(ttl_seconds=10, clock=lambda: clock[0], timer_factory=Timer)
    cache.extract(("owner",), "mail", "email", {}, lambda _: {"subject": "private"})
    assert len(cache._entries) == 1 and len(timers) == 1
    clock[0] = 10
    timers[0].callback()  # timer runs without another cache read
    assert not cache._entries and cache._timer is None


@pytest.mark.parametrize(
    "operation,model",
    [
        ("expectation_compile", "compiler-model"),
        ("clarification_continue", "compiler-model"),
        ("mismatch_investigator", "investigator-model"),
        ("smoke", "test-model"),
    ],
)
def test_trusted_model_selection_by_operation(operation, model):
    runtime = Mock()
    runtime.converse.return_value = response()
    adapter = BedrockClient(
        settings(
            bedrock_compiler_model_id="compiler-model",
            bedrock_investigator_model_id="investigator-model",
        ),
        runtime=runtime,
    )
    assert (
        adapter.converse_json(
            system_prompt="safe",
            user_content="safe",
            output_model=Output,
            operation_name=operation,
        ).answer
        == 42
    )
    assert runtime.converse.call_args.kwargs["modelId"] == model


def test_token_budget_stops_validation_repair():
    runtime = Mock()
    runtime.converse.return_value = response(
        '{"answer":"invalid"}',
        usage={"inputTokens": 10, "outputTokens": 10, "totalTokens": 20},
    )
    adapter = BedrockClient(settings(bedrock_max_total_tokens=10), runtime=runtime)
    with pytest.raises(BedrockValidationError):
        call(adapter)
    assert runtime.converse.call_count == 1
    assert runtime.converse.call_args.kwargs["inferenceConfig"]["maxTokens"] == 10


def test_concurrent_clients_share_process_gate():
    active, maximum = [0], [0]
    entered, release = threading.Event(), threading.Event()
    lock = threading.Lock()

    class Runtime:
        def converse(self, **kwargs):
            with lock:
                active[0] += 1
                maximum[0] = max(maximum[0], active[0])
            entered.set()
            assert release.wait(2)
            with lock:
                active[0] -= 1
            return response()

    with ThreadPoolExecutor(max_workers=2) as pool:
        one = pool.submit(
            call,
            BedrockClient(settings(bedrock_max_concurrent_calls=1), runtime=Runtime()),
        )
        assert entered.wait(2)
        two = pool.submit(
            call,
            BedrockClient(settings(bedrock_max_concurrent_calls=1), runtime=Runtime()),
        )
        release.set()
        assert one.result().answer == two.result().answer == 42
    assert maximum[0] == 1


def test_gate_exhaustion_fails_without_model_call():
    gate = call_gate(3)
    for _ in range(3):
        gate.acquire()
    runtime = Mock()
    try:
        adapter = BedrockClient(
            settings(
                bedrock_max_concurrent_calls=3, bedrock_operation_timeout_seconds=1
            ),
            runtime=runtime,
        )
        with pytest.raises(BedrockTimeoutError):
            call(adapter)
        assert not runtime.converse.called
    finally:
        for _ in range(3):
            gate.release()


@pytest.mark.parametrize(
    "text",
    [
        "Make sure my Amazon package arrives Friday.",
        "Make sure my electricity bill is lower.",
    ],
)
def test_make_sure_routes_to_canonical_compiler_without_parsing_in_router(text):
    from uuid import uuid4

    from app.agent.actions import AgentAction
    from app.agent.models import AgentInput
    from app.agent.orchestrator import AgentOrchestrator
    from app.core.auth import AuthenticatedUser

    plan = AgentOrchestrator(settings=settings()).plan(
        AuthenticatedUser(id=uuid4()), AgentInput(text=text)
    )
    assert plan.action == AgentAction.COMPILE_EXPECTATION and plan.text == text
