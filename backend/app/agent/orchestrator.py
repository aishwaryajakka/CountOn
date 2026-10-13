"""Bounded traffic controller; interpretation/ownership/persistence stay in MCP."""

import logging
import re
from collections.abc import Callable
from contextvars import ContextVar
from datetime import datetime, timezone
from time import perf_counter
from uuid import UUID, uuid4

import anyio
from pydantic import SecretStr, ValidationError

from app.agent.actions import (
    AgentAction,
    AgentStatus,
    CapabilityTool,
    FailureCode,
    ReasonCode,
)
from app.agent.adapters import (
    CapabilityAdapter,
    CapabilityError,
    CapabilityRequest,
    CapabilityResponse,
    CountOnMcpAdapter,
)
from app.agent.models import AgentInput, AgentPlan, AgentResult, AgentStep
from app.agent.registry import tools_for
from app.agent.session import (
    AgentSessionResult,
    AgentSessionState,
    AgentSessionStore,
    SessionMarker,
)
from app.agent.trust import finish
from app.ai.clarification import CORRECTION
from app.core.auth import AuthenticatedUser
from app.core.config import Settings, get_settings
from app.core.exceptions import AuthenticationError
from app.mcp.conversation_state import StateError, decode_state
from app.mcp.schemas import (
    CaptureExpectationInput,
    CompilationResult,
    CompileExpectationInput,
    ContinueCompilationInput,
    ExpectationListResult,
    ExpectationResult,
    ExplainMismatchInput,
    ExplanationResult,
    GetExpectationInput,
    ListExpectationsInput,
)
from app.schemas.clarification import ClarificationStatus

logger = logging.getLogger(__name__)
_attempts: ContextVar[tuple[CapabilityTool, ...] | None] = ContextVar(
    "counton_capability_attempts", default=None
)

# Conservative routing guard, not a compiler or a universal injection detector.
_POLICY = re.compile(
    r"\b(?:user[_ -]?id|owner[_ -]?id|profile[_ -]?id)\b"
    r"|\b(?:call|invoke|execute)\s+(?:the\s+)?(?:[a-z]+_[a-z_]+|sql|tools?/call)\b"
    r"|\buse\s+(?:(?:this|the|hidden|internal)\s+)?tool\b"
    r"|\b(?:hidden|internal|admin|system)\b.{0,80}\b(?:tools?|prompts?|secrets?|keys?)\b"
    r"|\bignore\b.{0,80}\b(?:instructions|rules|policy)\b"
    r"|\b(?:choose|set|mark|declare|force|return|decide)\b.{0,100}\b(?:match|mismatch|unknown)\b"
    r"|\b(?:verdict|outcome|evaluation_result)\s*[:=]",
    re.IGNORECASE | re.DOTALL,
)
_CANCEL = re.compile(
    r"^(?:never mind|nevermind|cancel that|cancel|forget it)[.!?]*$", re.IGNORECASE
)
_LIST = re.compile(
    r"^(?:what am i (?:counting on|tracking)|what are my expectations|what's being monitored|what is being monitored|show (?:me )?my expectations)[.!?]*$",
    re.IGNORECASE,
)
_CAPTURE = re.compile(
    r"^(?:i'm counting on|i am counting on|i expect|i'm expecting|save|monitor|track)\s",
    re.IGNORECASE,
)
_WHY = re.compile(r"^why\s", re.IGNORECASE)
_DETAIL = re.compile(
    r"^(?:tell me about|check|what's happening with|what is happening with)\s",
    re.IGNORECASE,
)


def principal(user: AuthenticatedUser) -> None:
    if not isinstance(user, AuthenticatedUser) or not isinstance(user.id, UUID):
        raise AuthenticationError()


class AgentOrchestrator:
    """Only trusted hosts supply an already JWT-verified principal.

    Hosted by the narrow authenticated agent route. Owned lookup uses MCP list,
    never database access.
    Explicit IDs are references, not ownership. Existing signed
    state is verified here; MCP's durable ledger owns consumption/replay. No retries.
    """

    def __init__(
        self,
        adapter: CapabilityAdapter | None = None,
        *,
        settings: Settings | None = None,
        session_store: AgentSessionStore | None = None,
        audit_sink: Callable[[AuthenticatedUser, AgentResult, int], None] | None = None,
    ) -> None:
        self.adapter = adapter or CountOnMcpAdapter()
        self.audit_sink = audit_sink
        self.settings = settings or get_settings()
        self.sessions = session_store or AgentSessionStore(
            ttl_seconds=self.settings.clarification_ttl_seconds
        )

    @staticmethod
    def _context_action(text: str) -> AgentAction | None:
        text = text.lower().replace("’", "'").strip().rstrip(".!?")
        reference = r"(?:it|this|that)(?: expectation)?"
        if re.fullmatch(
            rf"why (?:(?:did|has) {reference} (?:fail|failed|not match)|(?:didn't|did not) {reference} match|(?:was|is) {reference} (?:higher|lower|different))",
            text,
        ):
            return AgentAction.EXPLAIN_MISMATCH
        if re.fullmatch(
            rf"(?:{reference}|(?:tell me about|check|what happened with|what's happening with|what is happening with) {reference}(?: again)?)",
            text,
        ):
            return AgentAction.GET_EXPECTATION
        return None

    async def _selected_read(
        self, user: AuthenticatedUser, identity: UUID, action: AgentAction
    ) -> AgentResult:
        # A previous selection is a reference, never an ownership grant. Read it
        # again through MCP before reuse; explain does its own ownership check too.
        got = await self.handle(
            user,
            AgentInput(text="Tell me about that expectation", expectation_id=identity),
        )
        if got.status != AgentStatus.SUCCESS or action == AgentAction.GET_EXPECTATION:
            return got
        explained = await self.handle(
            user, AgentInput(text="Why did it fail?", expectation_id=identity)
        )
        return explained.model_copy(
            update={
                "steps": got.steps + explained.steps,
                "expectation": got.expectation,
            }
        )

    def _next_session(
        self, state: AgentSessionState, result: AgentResult
    ) -> AgentSessionState:
        fields = state.model_dump(mode="python")
        fields["last_action"] = result.action
        if result.captured:
            fields.update(
                selected_expectation_id=result.expectation_id,
                clarification_reference=None,
                pending_disambiguation_ids=(),
                marker=SessionMarker.COMPLETED,
            )
        elif result.clarification_state is not None:
            fields.update(
                selected_expectation_id=None,
                clarification_reference=result.clarification_state,
                pending_disambiguation_ids=(),
                marker=SessionMarker.READY,
            )
        elif result.status == AgentStatus.CANCELLED:
            fields.update(
                selected_expectation_id=None,
                clarification_reference=None,
                pending_disambiguation_ids=(),
                marker=SessionMarker.CANCELLED,
            )
        elif result.status == AgentStatus.DISAMBIGUATION_REQUIRED:
            fields.update(
                selected_expectation_id=None,
                pending_disambiguation_ids=tuple(row.id for row in result.candidates),
            )
        elif result.status == AgentStatus.SUCCESS and result.expectation_id is not None:
            fields.update(
                selected_expectation_id=result.expectation_id,
                pending_disambiguation_ids=(),
            )
        elif result.action in (
            AgentAction.COMPILE_EXPECTATION,
            AgentAction.CONTINUE_CLARIFICATION,
        ):
            # Failed/unsupported/expired drafts cannot be carried into a new turn.
            # Policy rejection is UNKNOWN and keeps the existing draft intact.
            fields.update(
                selected_expectation_id=None,
                clarification_reference=None,
                pending_disambiguation_ids=(),
                marker=SessionMarker.READY,
            )
        elif result.code in (FailureCode.NOT_FOUND, FailureCode.STATE_REJECTED):
            fields.update(selected_expectation_id=None, pending_disambiguation_ids=())
            if result.code == FailureCode.STATE_REJECTED:
                fields.update(clarification_reference=None, marker=SessionMarker.READY)
        elif state.pending_disambiguation_ids:
            # A list/unsupported interruption must not lose the pending read intent.
            fields["last_action"] = state.last_action
        return AgentSessionState.model_validate(fields)

    async def handle_session(
        self,
        user: AuthenticatedUser,
        input_: AgentInput,
        session_reference: SecretStr | None = None,
    ) -> AgentSessionResult:
        principal(user)
        started = perf_counter()
        run_id = uuid4()
        token = _attempts.set(())
        result = AgentResult(
            action=AgentAction.UNKNOWN,
            status=AgentStatus.FAILED,
            message="The run was interrupted. Check CountOn before retrying a save.",
            fallback_used=True,
            code=FailureCode.UNAVAILABLE,
        )
        try:
            turn = await self._handle_session(user, input_, session_reference)
            result = turn.result
        finally:
            result = finish(
                result.model_copy(
                    update={"invoked_capabilities": _attempts.get() or ()}
                ),
                run_id,
            )
            _attempts.reset(token)
            await self._audit_result(user, result, started)
        return turn.model_copy(update={"result": result})

    async def _audit_result(
        self, user: AuthenticatedUser, result: AgentResult, started: float
    ) -> None:
        duration = round((perf_counter() - started) * 1000)
        audit_status = "not_configured"
        if self.audit_sink is not None:
            try:
                await anyio.to_thread.run_sync(self.audit_sink, user, result, duration)
                audit_status = "persisted"
            except Exception:  # noqa: BLE001 - Audit failure must never cause write retries
                audit_status = "failed"
        log = logger.warning if audit_status == "failed" else logger.info
        log(
            "Orchestration run completed",
            extra={
                "run_id": str(result.trust.run_id) if result.trust else None,
                "user_id": str(user.id),
                "action": result.action.value,
                "result_status": result.status.value,
                "duration_ms": duration,
                "audit_status": audit_status,
            },
        )

    async def _handle_session(
        self,
        user: AuthenticatedUser,
        input_: AgentInput,
        session_reference: SecretStr | None = None,
    ) -> AgentSessionResult:
        """Trusted host API. Clients may carry a handle, never trusted JSON state."""
        principal(user)
        input_ = AgentInput.model_validate(input_)
        if input_.clarification_state is not None:
            return AgentSessionResult(
                result=AgentResult(
                    action=AgentAction.UNKNOWN,
                    status=AgentStatus.REJECTED,
                    code=FailureCode.INVALID_REQUEST,
                    message="Use the active conversation handle instead of supplying draft state.",
                )
            )
        try:
            reference = session_reference or self.sessions.create(user)
            async with self.sessions.turn(user, reference) as entry:
                state = entry.state
                if state.clarification_reference is not None:
                    # Canonical version/signature/owner/expiry, not new state crypto.
                    self._verify_state(
                        user,
                        AgentPlan(
                            action=AgentAction.CONTINUE_CLARIFICATION,
                            reason_code=ReasonCode.FOLLOW_UP,
                            allowed_tools=tools_for(AgentAction.CONTINUE_CLARIFICATION),
                            clarification_state=state.clarification_reference,
                            text="pending",
                        ),
                    )
                result = await self._session_turn(user, input_, state)
                next_reference = self.sessions.advance(
                    entry, self._next_session(state, result)
                )
                return AgentSessionResult(
                    result=result, session_reference=next_reference
                )
        except CapabilityError as error:
            return AgentSessionResult(
                result=AgentResult(
                    action=AgentAction.UNKNOWN,
                    status=AgentStatus.FAILED,
                    code=error.code,
                    message="This conversation is no longer available. Please restate your request in a new session.",
                    fallback_used=True,
                )
            )

    async def _session_turn(
        self, user: AuthenticatedUser, input_: AgentInput, state: AgentSessionState
    ) -> AgentResult:
        text = input_.text.lower().replace("’", "'").rstrip(".!?")
        if _POLICY.search(text):
            return await self.handle(user, input_)
        if _CANCEL.fullmatch(text) and state.clarification_reference is None:
            return AgentResult(
                action=AgentAction.CANCEL,
                status=AgentStatus.CANCELLED,
                message="Cancelled. Nothing was saved.",
            )
        # A bounded pending list never implicitly selects its first candidate.
        ordinal = re.fullmatch(r"(?:the )?(first|second|third|[1-9]|10)(?: one)?", text)
        if state.pending_disambiguation_ids and (
            input_.expectation_id is not None or ordinal
        ):
            identity = input_.expectation_id
            if identity is None and ordinal is not None:
                labels = {"first": 1, "second": 2, "third": 3}
                index = labels.get(ordinal[1]) or int(ordinal[1])
                if index <= len(state.pending_disambiguation_ids):
                    identity = state.pending_disambiguation_ids[index - 1]
            if identity not in state.pending_disambiguation_ids:
                return AgentResult(
                    action=AgentAction.UNKNOWN,
                    status=AgentStatus.CLARIFICATION,
                    code=ReasonCode.MISSING_REFERENCE,
                    message="Please choose one of the listed expectations or restate which one you mean.",
                )
            assert identity is not None
            action = state.last_action
            if action not in (
                AgentAction.GET_EXPECTATION,
                AgentAction.EXPLAIN_MISMATCH,
            ):
                raise CapabilityError(FailureCode.STATE_REJECTED)
            return await self._selected_read(user, identity, action)
        contextual = self._context_action(text)
        bare_reference = re.fullmatch(r"(?:it|this|that)(?: expectation)?", text)
        if contextual is not None and not (
            bare_reference and state.clarification_reference
        ):
            if input_.expectation_id is not None:
                return await self._selected_read(
                    user, input_.expectation_id, contextual
                )
            if (
                state.selected_expectation_id is None
                or state.pending_disambiguation_ids
            ):
                return AgentResult(
                    action=AgentAction.UNKNOWN,
                    status=AgentStatus.CLARIFICATION,
                    code=ReasonCode.MISSING_REFERENCE,
                    message="Which expectation do you mean? Select an actual CountOn record.",
                )
            return await self._selected_read(
                user, state.selected_expectation_id, contextual
            )
        if state.pending_disambiguation_ids and not (
            _LIST.fullmatch(text)
            or _WHY.match(text)
            or _DETAIL.match(text)
            or _CAPTURE.match(text)
            or _CANCEL.fullmatch(text)
            or (state.clarification_reference is not None and CORRECTION.match(text))
        ):
            return AgentResult(
                action=AgentAction.UNKNOWN,
                status=AgentStatus.CLARIFICATION,
                code=ReasonCode.MISSING_REFERENCE,
                message="Which listed expectation do you mean? Choose one or restate the topic.",
            )
        trusted = input_.model_copy(
            update={"clarification_state": state.clarification_reference}
        )
        return await self.handle(user, trusted)

    async def reset_session(
        self, user: AuthenticatedUser, session_reference: SecretStr
    ) -> AgentSessionResult:
        """Explicit trusted-host reset; consume an active draft before discarding."""
        principal(user)
        try:
            async with self.sessions.turn(user, session_reference) as entry:
                if entry.state.clarification_reference is not None:
                    cancelled = await self.handle(
                        user,
                        AgentInput(
                            text="Never mind",
                            clarification_state=entry.state.clarification_reference,
                        ),
                    )
                    if (
                        cancelled.status != AgentStatus.CANCELLED
                        and cancelled.code != FailureCode.STATE_REJECTED
                    ):
                        reference = self.sessions.advance(entry, entry.state)
                        return AgentSessionResult(
                            result=cancelled, session_reference=reference
                        )
                self.sessions.remove(entry)
                reference = self.sessions.create(user)
                return AgentSessionResult(
                    result=AgentResult(
                        action=AgentAction.CANCEL,
                        status=AgentStatus.CANCELLED,
                        message="Conversation reset. Tell me what you'd like to monitor.",
                    ),
                    session_reference=reference,
                )
        except CapabilityError as error:
            return AgentSessionResult(
                result=AgentResult(
                    action=AgentAction.UNKNOWN,
                    status=AgentStatus.FAILED,
                    code=error.code,
                    message="This conversation is no longer available. Start a new session.",
                    fallback_used=True,
                )
            )

    def plan(self, user: AuthenticatedUser, input_: AgentInput) -> AgentPlan:
        principal(user)
        input_ = AgentInput.model_validate(input_)
        text = input_.text.replace("’", "'")
        action, reason = AgentAction.UNKNOWN, ReasonCode.UNSUPPORTED_REQUEST
        if _POLICY.search(text):
            reason = ReasonCode.POLICY_REJECTED
        elif _CANCEL.fullmatch(text):
            action, reason = (
                (AgentAction.CANCEL, ReasonCode.CANCEL_REQUEST)
                if input_.clarification_state
                else (AgentAction.UNKNOWN, ReasonCode.NO_ACTIVE_CLARIFICATION)
            )
        elif _LIST.fullmatch(text):
            action, reason = AgentAction.LIST_EXPECTATIONS, ReasonCode.LIST_REQUEST
        elif _WHY.match(text) or _DETAIL.match(text):
            if input_.expectation_id is None:
                reason = ReasonCode.MISSING_REFERENCE
            else:
                action, reason = (
                    (AgentAction.EXPLAIN_MISMATCH, ReasonCode.WHY_QUESTION)
                    if _WHY.match(text)
                    else (AgentAction.GET_EXPECTATION, ReasonCode.DETAIL_REQUEST)
                )
        elif input_.clarification_state is not None:
            # Canonical continuation handles correction, unrelated answers/new topics.
            action, reason = AgentAction.CONTINUE_CLARIFICATION, ReasonCode.FOLLOW_UP
        elif _CAPTURE.match(text):
            action, reason = AgentAction.COMPILE_EXPECTATION, ReasonCode.CAPTURE_INTENT
        return AgentPlan(
            action=action,
            reason_code=reason,
            allowed_tools=tools_for(action),
            expectation_id=input_.expectation_id
            if action in (AgentAction.GET_EXPECTATION, AgentAction.EXPLAIN_MISMATCH)
            else None,
            requires_evidence=action == AgentAction.EXPLAIN_MISMATCH,
            clarification_state=input_.clarification_state
            if action in (AgentAction.CONTINUE_CLARIFICATION, AgentAction.CANCEL)
            else None,
            text=input_.text
            if action
            in (AgentAction.COMPILE_EXPECTATION, AgentAction.CONTINUE_CLARIFICATION)
            else None,
            timezone=input_.timezone,
            locale=input_.locale,
            compilation_id=input_.compilation_id
            if action == AgentAction.COMPILE_EXPECTATION
            else None,
        )

    async def handle(self, user: AuthenticatedUser, input_: AgentInput) -> AgentResult:
        input_ = AgentInput.model_validate(input_)
        plan = self.plan(user, input_)
        if plan.reason_code != ReasonCode.MISSING_REFERENCE:
            return await self.execute(user, plan)
        topic = self._reference_terms(input_.text)
        if not topic:
            # Pronouns need an explicit trusted selection, never the newest row.
            return await self.execute(user, plan)
        return await self._resolve(user, input_, topic)

    @staticmethod
    def _reference_terms(text: str) -> tuple[str, ...]:
        # Same constrained detail/why forms as the existing Alexa router. This is
        # record selection, not compilation or model-based semantic inference.
        text = text.lower().replace("’", "'").strip().rstrip(".!?")
        detail = re.fullmatch(
            r"(?:tell me about|check|what's happening with|what is happening with)\s+(?:my |the )?(.+)",
            text,
        )
        why = (
            re.fullmatch(
                r"why (?:did|has)\s+(?:my |the )?(.+?)\s+(?:fail|failed|not match)",
                text,
            )
            or re.fullmatch(
                r"why (?:didn't|did not)\s+(?:my |the )?(.+?)\s+match", text
            )
            or re.fullmatch(
                r"why (?:was|is)\s+(?:my |the )?(.+?)\s+(?:higher|lower|different)",
                text,
            )
        )
        match = detail or why
        if not match:
            return ()
        topic = match[1]
        if re.fullmatch(r"(?:it|this|that)(?: expectation)?", topic):
            return ()
        return tuple(
            word
            for word in re.findall(r"[a-z0-9]+", topic)
            if word not in ("my", "the", "a", "an", "expectation")
        )

    async def _resolve(
        self, user: AuthenticatedUser, input_: AgentInput, terms: tuple[str, ...]
    ) -> AgentResult:
        list_plan = AgentPlan(
            action=AgentAction.LIST_EXPECTATIONS,
            reason_code=ReasonCode.LIST_REQUEST,
            allowed_tools=tools_for(AgentAction.LIST_EXPECTATIONS),
        )
        action = (
            AgentAction.EXPLAIN_MISMATCH
            if _WHY.match(input_.text.lower())
            else AgentAction.GET_EXPECTATION
        )
        steps: list[AgentStep] = []
        matches: dict[UUID, ExpectationResult] = {}
        try:
            # Bound network/work and never assume a unique match in a truncated
            # collection. Every page uses the registered, authenticated list tool.
            for offset in range(0, 1000, 100):
                page = await self._call(
                    user,
                    list_plan,
                    list_request=ListExpectationsInput(limit=100, offset=offset),
                )
                steps.append(
                    AgentStep(action=list_plan.action, tool=CapabilityTool.LIST)
                )
                if (
                    not isinstance(page, ExpectationListResult)
                    or page.limit != 100
                    or page.offset != offset
                    or len(page.expectations) > 100
                ):
                    raise CapabilityError(FailureCode.PROTOCOL_ERROR)
                for row in page.expectations:
                    searchable = f"{row.claim} {row.metric or ''}".lower().replace(
                        "_", " "
                    )
                    if all(term in searchable for term in terms):
                        matches[row.id] = row
                if len(matches) > 1:
                    return AgentResult(
                        action=action,
                        status=AgentStatus.DISAMBIGUATION_REQUIRED,
                        code=ReasonCode.AMBIGUOUS_REFERENCE,
                        message="More than one expectation matches. Which one do you mean?",
                        candidates=tuple(matches.values())[:10],
                        steps=tuple(steps),
                    )
                if len(page.expectations) < 100:
                    break
            else:
                return AgentResult(
                    action=action,
                    status=AgentStatus.DISAMBIGUATION_REQUIRED,
                    code=ReasonCode.RESOLUTION_LIMIT,
                    message="Please select an expectation or use a more specific reference; I couldn't check every record safely.",
                    candidates=tuple(matches.values()),
                    steps=tuple(steps),
                )
            if not matches:
                return AgentResult(
                    action=action,
                    status=AgentStatus.FAILED,
                    code=FailureCode.NOT_FOUND,
                    message="I couldn't find a matching expectation in your CountOn records.",
                    steps=tuple(steps),
                )
            selected = input_.model_copy(update={"expectation_id": next(iter(matches))})
            result = await self.execute(user, self.plan(user, selected))
            return result.model_copy(update={"steps": tuple(steps) + result.steps})
        except Exception as error:  # noqa: BLE001 -- never expose private transport details
            return AgentResult(
                action=action,
                status=AgentStatus.FAILED,
                code=error.code
                if isinstance(error, CapabilityError)
                else FailureCode.UNAVAILABLE,
                message="I couldn't look up your expectations just now. Please try again.",
                fallback_used=True,
                steps=tuple(steps),
            )

    def _verify_state(self, user: AuthenticatedUser, plan: AgentPlan) -> None:
        if plan.clarification_state is None:
            return
        try:
            state = decode_state(
                plan.clarification_state.get_secret_value(), user.id, self.settings
            )
        except StateError:
            raise CapabilityError(FailureCode.STATE_REJECTED) from None
        expected = (
            ClarificationStatus.COMPILED
            if plan.action == AgentAction.CAPTURE_EXPECTATION
            else ClarificationStatus.ACTIVE
        )
        if state.status != expected or datetime.now(timezone.utc) >= state.expires_at:
            raise CapabilityError(FailureCode.STATE_REJECTED)
        if (
            plan.action == AgentAction.CAPTURE_EXPECTATION
            and state.compiled_expectation != plan.compiled_expectation
        ):
            raise CapabilityError(FailureCode.INVALID_REQUEST)

    async def _call(
        self,
        user: AuthenticatedUser,
        plan: AgentPlan,
        *,
        list_request: ListExpectationsInput | None = None,
    ) -> CapabilityResponse:
        plan = AgentPlan.model_validate(plan.model_dump(mode="python"))
        if plan.text is not None and _POLICY.search(plan.text):
            raise CapabilityError(FailureCode.INVALID_REQUEST)
        if plan.action == AgentAction.COMPILE_EXPECTATION and (
            plan.text is None or not _CAPTURE.match(plan.text.replace("’", "'"))
        ):
            raise CapabilityError(FailureCode.INVALID_REQUEST)
        self._verify_state(user, plan)
        tool = tools_for(plan.action)[0]
        if list_request is not None and tool != CapabilityTool.LIST:
            raise CapabilityError(FailureCode.INVALID_REQUEST)
        request: CapabilityRequest
        if tool == CapabilityTool.LIST:
            request = list_request or ListExpectationsInput()
        elif tool in (CapabilityTool.GET, CapabilityTool.EXPLAIN):
            assert plan.expectation_id is not None
            request = (
                GetExpectationInput(expectation_id=plan.expectation_id)
                if tool == CapabilityTool.GET
                else ExplainMismatchInput(expectation_id=plan.expectation_id)
            )
        elif tool == CapabilityTool.COMPILE:
            assert plan.text is not None
            request = CompileExpectationInput(
                text=plan.text,
                timezone=plan.timezone,
                locale=plan.locale,
                conversational=True,
                compilation_id=plan.compilation_id,
            )
        elif tool == CapabilityTool.CONTINUE:
            assert plan.clarification_state is not None
            answer = "Never mind" if plan.action == AgentAction.CANCEL else plan.text
            assert answer is not None
            request = ContinueCompilationInput(
                state=plan.clarification_state.get_secret_value(), answer=answer
            )
        else:
            assert (
                plan.compiled_expectation is not None
                and plan.clarification_state is not None
            )
            request = CaptureExpectationInput(
                **plan.compiled_expectation.model_dump(),
                compilation_state=plan.clarification_state.get_secret_value(),
            )
        attempts = _attempts.get()
        if attempts is not None:
            _attempts.set(attempts + (tool,))
        return await self.adapter.call(user, tool, request)

    async def execute(self, user: AuthenticatedUser, plan: AgentPlan) -> AgentResult:
        principal(user)
        started = perf_counter()
        steps: list[AgentStep] = []
        result_status = AgentStatus.FAILED
        bedrock_used = False
        # A model_construct/altered plan must not bypass validation or execute.
        safe_action = (
            plan.action if isinstance(plan.action, AgentAction) else AgentAction.UNKNOWN
        )
        try:
            plan = AgentPlan.model_validate(plan.model_dump(mode="python"))
            if plan.action == AgentAction.UNKNOWN:
                message = (
                    "I can only use approved CountOn capabilities; I can't change evaluations or identities."
                    if plan.reason_code == ReasonCode.POLICY_REJECTED
                    else "Which expectation do you mean? Select an actual CountOn record."
                    if plan.reason_code == ReasonCode.MISSING_REFERENCE
                    else "There isn't an active expectation draft to cancel."
                    if plan.reason_code == ReasonCode.NO_ACTIVE_CLARIFICATION
                    else "Ask about your expectations, explain a recorded result, or describe one expectation to monitor."
                )
                result_status = (
                    AgentStatus.REJECTED
                    if plan.reason_code == ReasonCode.POLICY_REJECTED
                    else AgentStatus.CLARIFICATION
                    if plan.reason_code == ReasonCode.MISSING_REFERENCE
                    else AgentStatus.UNSUPPORTED
                )
                return AgentResult(
                    action=plan.action,
                    status=result_status,
                    message=message,
                    code=plan.reason_code,
                )
            output = await self._call(user, plan)
            if isinstance(output, (CompilationResult, ExplanationResult)):
                bedrock_used = output.bedrock_used
            steps.append(AgentStep(action=plan.action, tool=tools_for(plan.action)[0]))
            if isinstance(output, CompilationResult) and plan.action in (
                AgentAction.COMPILE_EXPECTATION,
                AgentAction.CONTINUE_CLARIFICATION,
                AgentAction.CANCEL,
            ):
                if plan.action == AgentAction.CANCEL and output.status not in (
                    "cancelled",
                    "expired",
                    "error",
                ):
                    raise CapabilityError(FailureCode.PROTOCOL_ERROR)
                if output.status == "compiled":
                    if output.expectation is None or not output.capture_state:
                        raise CapabilityError(FailureCode.PROTOCOL_ERROR)
                    capture = AgentPlan(
                        action=AgentAction.CAPTURE_EXPECTATION,
                        reason_code=ReasonCode.COMPILED_READY,
                        allowed_tools=tools_for(AgentAction.CAPTURE_EXPECTATION),
                        compiled_expectation=output.expectation,
                        clarification_state=SecretStr(output.capture_state),
                        metadata=plan.metadata,
                    )
                    saved = await self._call(user, capture)
                    steps.append(
                        AgentStep(action=capture.action, tool=CapabilityTool.CAPTURE)
                    )
                    if not isinstance(saved, ExpectationResult):
                        raise CapabilityError(FailureCode.PROTOCOL_ERROR)
                    result_status = AgentStatus.SUCCESS
                    return AgentResult(
                        action=plan.action,
                        status=result_status,
                        message="Got it. I saved that expectation in CountOn.",
                        expectation=saved,
                        compiled_expectation=output.expectation,
                        captured=True,
                        steps=tuple(steps),
                        bedrock_used=output.bedrock_used,
                    )
                if output.status == "clarification":
                    if not output.state:
                        raise CapabilityError(FailureCode.PROTOCOL_ERROR)
                    follow_up = AgentPlan(
                        action=AgentAction.CONTINUE_CLARIFICATION,
                        reason_code=ReasonCode.FOLLOW_UP,
                        allowed_tools=tools_for(AgentAction.CONTINUE_CLARIFICATION),
                        clarification_state=SecretStr(output.state),
                        text="pending",
                    )
                    self._verify_state(user, follow_up)
                    result_status = AgentStatus.CLARIFICATION
                    return AgentResult(
                        action=plan.action,
                        status=result_status,
                        message=output.message,
                        clarification_state=SecretStr(output.state),
                        steps=tuple(steps),
                        bedrock_used=output.bedrock_used,
                    )
                result_status = (
                    AgentStatus.CANCELLED
                    if output.status == "cancelled"
                    else AgentStatus.UNSUPPORTED
                    if output.status == "unsupported"
                    else AgentStatus.FAILED
                )
                return AgentResult(
                    action=plan.action,
                    status=result_status,
                    message=output.message,
                    fallback_used=output.status in ("error", "expired"),
                    code=FailureCode.STATE_REJECTED
                    if output.status == "expired"
                    else FailureCode.INTELLIGENCE_UNAVAILABLE
                    if output.status == "error"
                    else None,
                    steps=tuple(steps),
                    bedrock_used=output.bedrock_used,
                )
            if (
                isinstance(output, ExpectationListResult)
                and plan.action == AgentAction.LIST_EXPECTATIONS
            ):
                result_status = AgentStatus.SUCCESS
                return AgentResult(
                    action=plan.action,
                    status=result_status,
                    expectations=output,
                    steps=tuple(steps),
                    message="Here are your expectations."
                    if output.expectations
                    else "You aren't counting on anything yet.",
                )
            if isinstance(output, ExpectationResult) and plan.action in (
                AgentAction.GET_EXPECTATION,
                AgentAction.CAPTURE_EXPECTATION,
            ):
                if (
                    plan.action == AgentAction.GET_EXPECTATION
                    and output.id != plan.expectation_id
                ):
                    raise CapabilityError(FailureCode.PROTOCOL_ERROR)
                result_status = AgentStatus.SUCCESS
                return AgentResult(
                    action=plan.action,
                    status=result_status,
                    message=output.claim,
                    expectation=output,
                    captured=plan.action == AgentAction.CAPTURE_EXPECTATION,
                    compiled_expectation=plan.compiled_expectation,
                    steps=tuple(steps),
                )
            if (
                isinstance(output, ExplanationResult)
                and plan.action == AgentAction.EXPLAIN_MISMATCH
            ):
                if output.expectation_id != plan.expectation_id:
                    raise CapabilityError(FailureCode.PROTOCOL_ERROR)
                result_status = AgentStatus.SUCCESS
                return AgentResult(
                    action=plan.action,
                    status=result_status,
                    message=output.message,
                    explanation=output,
                    fallback_used=output.fallback_used,
                    steps=tuple(steps),
                    bedrock_used=output.bedrock_used,
                )
            raise CapabilityError(FailureCode.PROTOCOL_ERROR)
        except (CapabilityError, ValidationError) as error:
            result_status = AgentStatus.FAILED
            code = (
                error.code
                if isinstance(error, CapabilityError)
                else FailureCode.INVALID_REQUEST
            )
            return AgentResult(
                action=safe_action,
                status=AgentStatus.FAILED,
                steps=tuple(steps),
                code=code,
                fallback_used=True,
                bedrock_used=bedrock_used,
                message="I couldn't find that expectation in your CountOn records."
                if code == FailureCode.NOT_FOUND
                else "Your expectation draft is no longer available. Please start again."
                if code == FailureCode.STATE_REJECTED
                else "I couldn't complete that safely. Check your CountOn records before retrying a save.",
            )
        except Exception:  # noqa: BLE001 -- injected adapters may raise private transport errors
            result_status = AgentStatus.FAILED
            return AgentResult(
                action=safe_action,
                status=AgentStatus.FAILED,
                steps=tuple(steps),
                code=FailureCode.UNAVAILABLE,
                fallback_used=True,
                bedrock_used=bedrock_used,
                message="CountOn is temporarily unavailable. Check your records before retrying a save.",
            )
        finally:
            logger.info(
                "Agent action completed",
                extra={
                    "user_id": str(user.id),
                    "result_status": result_status.value,
                    "tool_name": steps[-1].tool.value if steps else None,
                    "operation_name": "agent_orchestration",
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                },
            )
