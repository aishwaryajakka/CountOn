"""Pure Bedrock interpretation with independent grounding; no persistence."""

import json
import logging
import re
from time import monotonic

from app.ai.bedrock_client import BedrockClient
from app.ai.compiler_grounding import (
    NUMBER,
    GroundingError,
    clarification,
    ground_compiled,
    resolve_deadline,
)
from app.ai.exceptions import BedrockError, intelligence_error_code
from app.ai.prompts import (
    EXPECTATION_COMPILER_PROMPT_VERSION,
    compilation_input,
    expectation_compiler_prompt,
)
from app.schemas.compiler import (
    CannotCompile,
    ClarificationReason,
    ClarificationRequest,
    CompileContext,
    CompiledExpectation,
    CompileOutcome,
    CompileResult,
)

logger = logging.getLogger("app.ai.compiler")

CLARIFICATION_QUESTIONS = {
    ClarificationReason.MISSING_SUBJECT: "Which bill or subject should CountOn monitor?",
    ClarificationReason.MISSING_TARGET: "What numeric limit or target should CountOn monitor?",
    ClarificationReason.MISSING_BASELINE: "What baseline amount should I compare against?",
    ClarificationReason.AMBIGUOUS_COMPARISON: "Should the value be lower, higher, equal, or within an inclusive limit?",
    ClarificationReason.AMBIGUOUS_DEADLINE: "Which local date and time should be the deadline? Specify AM or PM if needed.",
    ClarificationReason.AMBIGUOUS_CURRENCY: "Which currency do you mean? Current bill monitoring uses USD.",
    ClarificationReason.MULTIPLE_EXPECTATIONS: "Which single expectation should I compile first?",
}


class CompilerError(Exception):
    """Stable compiler failure, not a clarification or business evaluation."""

    def __init__(self, code: str = "COMPILER_INVALID_OUTPUT") -> None:
        self.code = code
        super().__init__("Expectation compilation failed safely")


class BedrockExpectationCompiler:
    def __init__(self, client: BedrockClient | None = None) -> None:
        self.client = client or BedrockClient()

    def compile_expectation(self, text: str, context: CompileContext) -> CompileOutcome:
        if not isinstance(text, str) or not text.strip() or len(text) > 8000:
            raise ValueError("text must contain 1–8000 characters")
        started = monotonic()
        outcome = "error"
        try:
            data = json.loads(
                compilation_input(
                    text=text.strip(),
                    timezone=context.timezone,
                    reference_time=context.current_time,
                )
            )
            data["locale"] = context.locale
            response = self.client.converse_json(
                system_prompt=expectation_compiler_prompt(),
                user_content=json.dumps(data),
                output_model=CompileResult,
                operation_name="expectation_compile",
                metadata={"prompt_version": EXPECTATION_COMPILER_PROMPT_VERSION},
                temperature=0,
            )
            result = response.root
            if isinstance(result, CompiledExpectation):
                # Explicit repeated clauses require one-at-a-time intent, even if
                # a model incorrectly returns only the first independent claim.
                if (
                    re.search(r"\b(?:and|also)\b", text, re.IGNORECASE)
                    and len(
                        re.findall(
                            rf"\b(?:under|over|at most|at least|below|above)\s+[$€£]?{NUMBER}",
                            text,
                            re.IGNORECASE,
                        )
                    )
                    > 1
                ):
                    result = clarification(
                        text,
                        ClarificationReason.MULTIPLE_EXPECTATIONS,
                        "Which single expectation should I compile first?",
                        "claim",
                    )
                elif re.search(
                    r"\b(?:tolerance|materiality|threshold|daily|weekly|monthly|every)\b|\bwithin\s+\d+\s*%",
                    text,
                    re.IGNORECASE,
                ):
                    result = CannotCompile(
                        result="unsupported",
                        reason_code="UNSUPPORTED_EXPECTATION",
                        unsupported_reason="Custom tolerance or recurring schedules require a supported contract; the compiler cannot silently discard those requirements.",
                    )
                else:
                    result = ground_compiled(text, context, result)
            elif isinstance(result, ClarificationRequest):
                # Do not trust model-produced partials as continuation state. This
                # first pass retains only the verbatim claim, an explicit fact.
                result.partial_interpretation = {"claim": text.strip()}
                # Questions are a trusted UI surface. Use a targeted safe template
                # rather than rendering arbitrary instructions from model output.
                result.question = CLARIFICATION_QUESTIONS[result.reason_code]
                temporal = resolve_deadline(text, context)
                if isinstance(temporal, ClarificationRequest):
                    result = temporal
            outcome = result.result
            return result
        except (BedrockError, GroundingError) as error:
            raise CompilerError(intelligence_error_code(error)) from None
        finally:
            logger.info(
                "Expectation compilation completed",
                extra={
                    "operation_name": "expectation_compile",
                    "result_status": outcome,
                    "prompt_version": EXPECTATION_COMPILER_PROMPT_VERSION,
                    "duration_ms": round((monotonic() - started) * 1000, 2),
                },
            )

    def close(self) -> None:
        self.client.close()
