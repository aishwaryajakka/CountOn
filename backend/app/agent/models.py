"""Strict plans/results, reusing existing CountOn payload and response models."""

import re
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    computed_field,
    field_validator,
    model_validator,
)

from app.agent.actions import (
    AgentAction,
    AgentStatus,
    CapabilityTool,
    FailureCode,
    ReasonCode,
)
from app.agent.registry import REASONS, tools_for
from app.evaluators.base import EvaluationResult
from app.mcp.schemas import ExpectationListResult, ExpectationResult, ExplanationResult
from app.schemas.compiler import CompileContext
from app.schemas.expectation import ExpectationCreate
from app.schemas.trust import EvidenceSource

STRICT = ConfigDict(
    extra="forbid",
    frozen=True,
    strict=True,
    allow_inf_nan=False,
    hide_input_in_errors=True,
    revalidate_instances="always",
)


def checked_reference(value: SecretStr | None) -> SecretStr | None:
    if value is not None and not re.fullmatch(
        r"[A-Za-z0-9_-]+\.[0-9a-f]{64}", value.get_secret_value()
    ):
        raise ValueError("An actual signed continuation/capture reference is required")
    if value is not None and len(value.get_secret_value()) > 24000:
        raise ValueError("Reference exceeds the existing transport limit")
    return value


class AgentMetadata(BaseModel):
    model_config = STRICT
    request_id: UUID = Field(default_factory=uuid4)


class AgentInput(BaseModel):
    """Untrusted input; identity comes separately from verified auth context."""

    model_config = STRICT
    text: str = Field(min_length=1, max_length=2000, repr=False)
    expectation_id: UUID | None = None
    clarification_state: SecretStr | None = Field(default=None, repr=False)
    timezone: str = Field(default="UTC", min_length=1, max_length=100)
    locale: str | None = Field(default=None, pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")
    compilation_id: UUID = Field(default_factory=uuid4)

    @field_validator("text")
    @classmethod
    def nonempty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A nonempty request is required")
        return value.strip()

    @field_validator("clarification_state")
    @classmethod
    def signed_shape(cls, value: SecretStr | None) -> SecretStr | None:
        return checked_reference(value)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        return CompileContext.valid_timezone(value)


class AgentPlan(BaseModel):
    """Internal plan, never a user-authorized capability grant or database command."""

    model_config = STRICT
    action: AgentAction
    expectation_id: UUID | None = None
    requires_evidence: bool = False
    allowed_tools: tuple[CapabilityTool, ...]
    clarification_state: SecretStr | None = Field(default=None, repr=False)
    compiled_expectation: ExpectationCreate | None = Field(default=None, repr=False)
    text: str | None = Field(default=None, min_length=1, max_length=2000, repr=False)
    timezone: str = Field(default="UTC", min_length=1, max_length=100)
    locale: str | None = Field(default=None, pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")
    compilation_id: UUID | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    reason_code: ReasonCode
    metadata: AgentMetadata = Field(default_factory=AgentMetadata)

    @field_validator("clarification_state")
    @classmethod
    def signed_shape(cls, value: SecretStr | None) -> SecretStr | None:
        # Shape only; authentication/signature/lifecycle are verified at execution.
        return checked_reference(value)

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        return CompileContext.valid_timezone(value)

    @model_validator(mode="after")
    def capability_policy(self) -> "AgentPlan":
        if self.reason_code not in REASONS[self.action]:
            raise ValueError("Reason must match the action policy")
        if self.allowed_tools != tools_for(self.action):
            raise ValueError("Tools must exactly match the immutable action policy")
        explain = self.action == AgentAction.EXPLAIN_MISMATCH
        if self.requires_evidence != explain:
            raise ValueError("Only explanation may delegate relevant evidence reads")
        reference = self.action in (
            AgentAction.GET_EXPECTATION,
            AgentAction.EXPLAIN_MISMATCH,
        )
        if reference != (self.expectation_id is not None):
            raise ValueError("Expectation reference is required only for get/explain")
        continuation = self.action in (
            AgentAction.CONTINUE_CLARIFICATION,
            AgentAction.CANCEL,
        )
        capture = self.action == AgentAction.CAPTURE_EXPECTATION
        if (continuation or capture) != (self.clarification_state is not None):
            raise ValueError(
                "An existing signed reference is required only for continuation/capture"
            )
        if capture != (self.compiled_expectation is not None):
            raise ValueError("Capture requires the existing final compiled payload")
        textual = self.action in (
            AgentAction.COMPILE_EXPECTATION,
            AgentAction.CONTINUE_CLARIFICATION,
        )
        if textual != (self.text is not None) or (
            self.text is not None and not self.text.strip()
        ):
            raise ValueError("Only compile/continue accept one nonempty utterance")
        if (self.action == AgentAction.COMPILE_EXPECTATION) != (
            self.compilation_id is not None
        ):
            raise ValueError("Only initial compilation has a replay identity")
        return self


class AgentStep(BaseModel):
    model_config = STRICT
    action: AgentAction
    tool: CapabilityTool


class TrustResponse(BaseModel):
    """Deterministic final receipt. Never accepted from browser or Bedrock."""

    model_config = STRICT
    answer: str = Field(min_length=1, max_length=4000, repr=False)
    status: AgentStatus
    evaluator_result: EvaluationResult | None
    expectation_id: UUID | None
    sources_used: tuple[EvidenceSource, ...] = ()
    evidence_ids: tuple[UUID, ...] = ()
    bedrock_used: bool
    fallback_used: bool
    grounded: bool
    safe_to_say: bool
    run_id: UUID


class AgentResult(BaseModel):
    model_config = STRICT
    action: AgentAction
    status: AgentStatus
    message: str = Field(min_length=1, max_length=4000)
    code: FailureCode | ReasonCode | None = None
    steps: tuple[AgentStep, ...] = Field(default=(), max_length=12)
    clarification_state: SecretStr | None = Field(default=None, repr=False)
    expectation: ExpectationResult | None = None
    expectations: ExpectationListResult | None = None
    explanation: ExplanationResult | None = None
    bedrock_used: bool = False

    fallback_used: bool = False
    captured: bool = False
    confirmation_required: bool = False
    capture_state: SecretStr | None = Field(default=None, repr=False)
    compiled_expectation: ExpectationCreate | None = Field(default=None, repr=False)
    candidates: tuple[ExpectationResult, ...] = Field(default=(), max_length=10)
    trust: TrustResponse | None = None
    invoked_capabilities: tuple[CapabilityTool, ...] = Field(default=(), max_length=12)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def answer(self) -> str:
        return self.message

    @computed_field  # type: ignore[prop-decorator]
    @property
    def expectation_id(self) -> UUID | None:
        if self.expectation is not None:
            return self.expectation.id
        return self.explanation.expectation_id if self.explanation is not None else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def clarification_required(self) -> bool:
        return self.status in (
            AgentStatus.CLARIFICATION,
            AgentStatus.DISAMBIGUATION_REQUIRED,
        )

    @computed_field  # type: ignore[prop-decorator]
    @property
    def evaluator_status(self) -> EvaluationResult | None:
        # Only a recorded deterministic evaluation, never inferred from status/text.
        return self.explanation.result if self.explanation is not None else None

    @computed_field  # type: ignore[prop-decorator]
    @property
    def safe_to_say(self) -> bool:
        from app.agent.trust import speech_is_safe

        if self.trust is not None:
            return self.trust.safe_to_say
        return speech_is_safe(self)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def trace_events(self) -> tuple[AgentStep, ...]:
        return self.steps
