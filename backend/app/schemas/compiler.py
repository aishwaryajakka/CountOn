"""Compiler and Investigator HTTP contract schemas and canonical interpretation contracts."""

from enum import StrEnum
from typing import Annotated, Any, Literal
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    RootModel,
    field_validator,
    model_validator,
)

from app.db.models.expectation import ExpectationType
from app.schemas.expectation import ExpectationCreate
from app.ai.models.expectation import (
    Expectation,
    ClarificationRequest as AIClarificationRequest,
    CancellationRequest,
    InvestigationResult,
)
from app.ai.outlook_intelligence import (
    OutlookEmailContext,
    OutlookCalendarContext,
    OutlookContextPayload,
    OutlookExtractionResult,
)
from app.ai.gmail_intelligence import (
    GmailEmailContext,
    GoogleCalendarContext,
    GmailContextPayload,
    GmailExtractionResult,
)
from app.ai.amazon_intelligence import (
    AmazonOrderContext,
    AmazonDeliveryPayload,
    AmazonExtractionResult,
)


class CompileContext(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    current_time: AwareDatetime | None = None
    timezone: str = Field(default="UTC", min_length=1, max_length=100)
    locale: str | None = Field(default=None, pattern=r"^[a-z]{2}(?:-[A-Z]{2})?$")

    @field_validator("timezone")
    @classmethod
    def valid_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("timezone must be an IANA timezone") from None
        return value


class ClarificationReason(StrEnum):
    MISSING_SUBJECT = "MISSING_SUBJECT"
    MISSING_TARGET = "MISSING_TARGET"
    MISSING_BASELINE = "MISSING_BASELINE"
    AMBIGUOUS_COMPARISON = "AMBIGUOUS_COMPARISON"
    AMBIGUOUS_DEADLINE = "AMBIGUOUS_DEADLINE"
    AMBIGUOUS_CURRENCY = "AMBIGUOUS_CURRENCY"
    MULTIPLE_EXPECTATIONS = "MULTIPLE_EXPECTATIONS"


class ClarificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    result: Literal["clarification"]
    question: str = Field(min_length=1, max_length=500)
    missing_fields: list[str] = Field(default_factory=list, max_length=10)
    ambiguous_fields: list[str] = Field(default_factory=list, max_length=10)
    partial_interpretation: dict[str, JsonValue] = Field(default_factory=dict)
    reason_code: ClarificationReason

    @field_validator("missing_fields", "ambiguous_fields")
    @classmethod
    def actual_fields(cls, names: list[str]) -> list[str]:
        allowed = set(ExpectationCreate.model_fields) | {"subject", "currency"}
        if any(name not in allowed for name in names):
            raise ValueError("Unknown expectation field")
        return names


class Grounding(BaseModel):
    """Exact utterance spans; not confidence scores or evidence observations."""

    model_config = ConfigDict(extra="forbid")
    subject_quote: str = Field(min_length=1, max_length=200)
    target_quote: str | None = Field(default=None, max_length=200)
    baseline_quote: str | None = Field(default=None, max_length=200)
    comparison_quote: str | None = Field(default=None, max_length=100)
    source_quotes: list[str] = Field(default_factory=list, max_length=10)


class CompiledExpectation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: Literal["compiled"]
    expectation: ExpectationCreate
    grounding: Grounding

    @model_validator(mode="after")
    def domain_contract(self) -> "CompiledExpectation":
        e = self.expectation
        if e.type == ExpectationType.numeric_comparison:
            if (
                not e.metric
                or e.comparison is None
                or (e.baseline is None and e.target_value is None)
            ):
                raise ValueError(
                    "Numeric expectation requires metric, comparison and baseline or target"
                )
            if e.baseline is not None and e.target_value is not None:
                raise ValueError("Compiler must select one comparison operand")
        elif (
            e.baseline is not None
            or e.target_value is not None
            or e.comparison is not None
        ):
            raise ValueError(
                "Non-numeric expectations cannot carry numeric comparison fields"
            )
        return self


class CannotCompile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result: Literal["unsupported"]
    reason_code: Literal["UNSUPPORTED_EXPECTATION"]
    unsupported_reason: str = Field(min_length=1, max_length=500)


CompileOutcome = Annotated[
    CompiledExpectation | ClarificationRequest | CannotCompile,
    Field(discriminator="result"),
]


class CompileResult(RootModel[CompileOutcome]):
    """Discriminated JSON envelope; service returns its typed root outcome."""


class CompileRequest(BaseModel):
    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    text: str = Field(..., description="Casual user statement to compile into a structured expectation")
    mock_mode: bool | None = Field(default=None, description="Optional override to force mock vs Bedrock mode")
    conversation_history: list[dict[str, str]] | None = Field(
        default=None,
        description="Prior conversation turns e.g. [{'role': 'user', 'content': '...'}] for multi-turn clarification memory",
    )
    draft_expectation: dict[str, Any] | None = Field(
        default=None,
        description="Partial expectation drafted from previous turn",
    )
    expectation_id: UUID | str | None = Field(
        default=None,
        description="ID of existing expectation if user is updating/correcting/cancelling",
    )


class CompileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: Literal["expectation", "clarification", "cancellation"]
    expectation: Expectation | None = None
    clarification: Any | None = None
    cancellation: CancellationRequest | None = None
    is_correction: bool = Field(default=False, description="True if this compilation represents a correction or amendment")


class InvestigationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expectation_id: UUID = Field(..., description="ID of the expectation to investigate after a mismatch")
    mock_mode: bool | None = Field(default=None, description="Optional override to force mock vs Bedrock mode")


class InvestigationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    explanation: str
    key_factors: list[str] = Field(default_factory=list)
    confidence: float
