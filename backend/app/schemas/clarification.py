"""Trusted, short-lived conversation contracts; never store authentication here."""

import json
from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID, uuid4

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    field_validator,
    model_validator,
)

from app.ai.prompts import (
    CLARIFICATION_PROMPT_VERSION,
    EXPECTATION_COMPILER_PROMPT_VERSION,
)
from app.schemas.compiler import CompileContext, CompileOutcome
from app.schemas.expectation import ExpectationCreate

AnswerInteraction = Literal["answer", "correction", "unrelated"]
ConversationInteraction = Literal[
    "initial",
    "answer",
    "correction",
    "cancellation",
    "new_expectation",
    "unrelated",
    "expired",
    "terminal",
    "error",
]

ConversationField = Literal[
    "subject",
    "comparison",
    "operand",
    "target_value",
    "baseline",
    "deadline",
    "currency",
]


class ClarificationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPILED = "COMPILED"
    CANCELLED = "CANCELLED"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"


class PartialInterpretation(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    subject: str | None = Field(default=None, min_length=1, max_length=200)
    operand: Literal["target", "baseline"] | None = None
    baseline_reference: Literal["last_month", "previous_bill", "baseline"] | None = None
    currency: Literal["USD"] | None = None
    values: dict[str, JsonValue] = Field(default_factory=dict)
    deadline_phrase: str | None = Field(default=None, max_length=200)
    deadline_reference_time: AwareDatetime | None = None
    pending_reference_time: AwareDatetime | None = None
    pending_deadline: str | None = Field(default=None, max_length=200)

    @field_validator("values")
    @classmethod
    def existing_field_types(cls, values: dict[str, JsonValue]) -> dict[str, JsonValue]:
        allowed = {
            "type",
            "metric",
            "comparison",
            "target_value",
            "baseline",
            "deadline",
            "evidence_sources",
        }
        if set(values) - allowed:
            raise ValueError("Unknown or private partial field")
        result: dict[str, JsonValue] = {}
        for name, value in values.items():
            field = ExpectationCreate.model_fields[name]
            adapter: TypeAdapter[Any] = TypeAdapter(Annotated[field.annotation, field])
            validated = adapter.validate_json(json.dumps(value), strict=True)
            result[name] = adapter.dump_python(validated, mode="json")
        return result

    @model_validator(mode="after")
    def one_operand(self) -> "PartialInterpretation":
        if (
            self.values.get("baseline") is not None
            and self.values.get("target_value") is not None
        ):
            raise ValueError("Only one numeric operand is allowed")
        if self.values.get("target_value") is not None and self.operand != "target":
            raise ValueError("Target amount requires target semantics")
        if self.values.get("baseline") is not None and self.operand != "baseline":
            raise ValueError("Baseline amount requires baseline semantics")
        if (self.pending_deadline is None) != (self.pending_reference_time is None):
            raise ValueError("Pending deadline requires its reference instant")
        if (self.deadline_phrase is None) != (self.deadline_reference_time is None):
            raise ValueError("Deadline phrase requires its reference instant")
        return self


class ClarificationHistoryEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=500)
    user_response: str = Field(min_length=1, max_length=2000)
    interaction: Literal["answer", "correction", "unrelated"]
    accepted_fields: list[ConversationField] = Field(default_factory=list)


class ClarificationState(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    version: Literal["v1"] = "v1"
    session_id: UUID = Field(default_factory=uuid4)
    original_utterance: str = Field(min_length=1, max_length=8000)
    partial_interpretation: PartialInterpretation = Field(
        default_factory=PartialInterpretation
    )
    unresolved_fields: list[ConversationField] = Field(default_factory=list)
    clarification_history: list[ClarificationHistoryEntry] = Field(
        default_factory=list, max_length=12
    )
    turn_count: int = Field(default=0, ge=0, le=12)
    max_turns: int = Field(default=3, ge=1, le=12)
    require_timing: bool = False
    no_progress_count: int = Field(default=0, ge=0, le=2)
    status: ClarificationStatus = ClarificationStatus.ACTIVE
    created_at: AwareDatetime
    expires_at: AwareDatetime
    timezone: str
    locale: str | None = None
    compiler_prompt_version: str = EXPECTATION_COMPILER_PROMPT_VERSION
    clarification_prompt_version: str = CLARIFICATION_PROMPT_VERSION
    question: str | None = Field(default=None, max_length=500)
    compiled_expectation: ExpectationCreate | None = None

    @model_validator(mode="after")
    def consistent_state(self) -> "ClarificationState":
        CompileContext(
            current_time=self.created_at, timezone=self.timezone, locale=self.locale
        )
        if (
            self.expires_at <= self.created_at
            or self.turn_count != len(self.clarification_history)
            or self.turn_count > self.max_turns
        ):
            raise ValueError("Invalid clarification lifecycle")
        if self.status == ClarificationStatus.ACTIVE and (
            not self.question
            or not self.unresolved_fields
            or self.turn_count >= self.max_turns
        ):
            raise ValueError(
                "Active state requires an unresolved question and remaining turns"
            )
        if (self.status == ClarificationStatus.COMPILED) != (
            self.compiled_expectation is not None
        ):
            raise ValueError("Compiled state requires exactly one compiled expectation")
        if self.status != ClarificationStatus.ACTIVE and (
            self.question or self.unresolved_fields
        ):
            raise ValueError("Terminal state cannot ask further questions")
        return self


class FieldPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    field: ConversationField
    value: JsonValue
    quote: str = Field(min_length=1, max_length=200)


class ContinuationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["answer", "correction", "unrelated"]
    patches: list[FieldPatch] = Field(default_factory=list, max_length=7)

    @model_validator(mode="after")
    def unique_patches(self) -> "ContinuationDecision":
        names = [p.field for p in self.patches]
        if len(names) != len(set(names)) or (self.kind == "unrelated" and self.patches):
            raise ValueError("Invalid continuation patch set")
        return self


class ClarificationTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error_code: str | None = None
    bedrock_used: bool = False
    state: ClarificationState
    outcome: CompileOutcome | None = None
    message: str
    interaction: Literal[
        "initial",
        "answer",
        "correction",
        "cancellation",
        "new_expectation",
        "unrelated",
        "expired",
        "terminal",
        "error",
    ]
    replaced_state: ClarificationState | None = None
