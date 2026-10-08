# CountOn Bedrock intelligence

Bedrock interprets/explains; the deterministic evaluator alone decides
MATCH / UNKNOWN / MISMATCH. This package cannot create expectations, evidence,
evaluations, or notifications. It imports no repositories, database sessions or
business services. Compilation returns the existing `ExpectationCreate`
(or an explicit clarification result), then orchestration calls the authenticated
MCP `capture_expectation` tool. Never bypass MCP to save compiler output.

The production compiler is exposed through `app.services.compiler_service`; the
legacy `app/mcp/compiler.py` adapter strips ownership before delegation. The MCP intelligence tools now expose compilation/continuation/explanation;
see [the integration handoff](../../../docs/bedrock-integration.md). The mismatch investigator is
available through a pure service; see [grounding and integration](investigation.md). The bounded
clarification workflow is now available through the pure application service; see
[conversation state, security and integration](clarification.md). The authenticated Next.js `/alexa` route orchestrates the existing MCP tools.
It compiles/clarifies before capture and explains only confirmed mismatch.
This remains a web simulator; real Alexa/Echo integration is not complete.

## Configuration

Add configuration only to `backend/.env.local` or private deployment environment
variables. Do not commit credentials or put AWS settings in frontend public vars.
Existing Pydantic Settings owns configuration; no second loader is introduced.

| Variable | Default | Meaning |
| --- | --- | --- |
| `BEDROCK_ENABLED` | `false` | Explicit feature opt-in |
| `AWS_REGION` | `us-east-2` | Region supporting your selected model |
| `BEDROCK_MODEL_ID` | `openai.gpt-oss-120b-1:0` | Supported model ID or inference-profile ID/ARN |
| `BEDROCK_MAX_TOKENS` | `1000` | Maximum output tokens, 1–65536; obey model limits |
| `BEDROCK_TEMPERATURE` | `0.1` | Sampling temperature, 0–1; obey model limits |
| `BEDROCK_REQUEST_TIMEOUT_SECONDS` | `30` | Connect/read timeout per attempt, >0–120 |
| `BEDROCK_MAX_RETRIES` | `2` | Additional recoverable infrastructure attempts, 0–5 |
| `BEDROCK_NATIVE_STRUCTURED_OUTPUT` | `false` | Enable Converse JSON-schema output only for a compatible model/schema |

A disabled or incomplete configuration does not contact AWS during import,
construction or application startup. Calls raise a stable disabled/unavailable
error. Existing health/readiness continues to check core dependencies; optional
intelligence is not added as a dependency.

Use the normal boto3 credential provider chain: local AWS SSO/profile/shared
credentials or an appropriate workload role. Do not pass credentials to this
client. Authenticate an existing SSO profile using `aws sso login --profile NAME`
and set `AWS_PROFILE=NAME` locally if needed. A Lightsail deployment must supply
an appropriate supported credential provider; do not assume it has an IAM role.

IAM requires **`bedrock:InvokeModel`** for non-streaming Converse on the selected
model/inference profile. Scope resources to permitted models/profiles; cross-region
profiles may require destination model permissions in their participating regions.
Ensure account/model access and any required provider agreement are enabled.
This client does not need Supabase/admin keys or AWS model-listing permissions.

## Interface and output validation

`BedrockClient.converse_text(...) -> str` and generic
`converse_json(..., output_model: type[T]) -> T` are synchronous, matching CountOn
services. In async handlers, use the existing threadpool execution convention;
never block the event loop with boto3. Use a context manager or call `close()`.
Client creation is lazy and the SDK uses the configured region, no custom endpoint.

```python
from datetime import datetime, timezone
from app.schemas.compiler import CompileContext, CompiledExpectation
from app.services.compiler_service import compile_expectation

result = compile_expectation(
    "I'm counting on my grocery bill staying under $120 this week",
    CompileContext(
        current_time=datetime(2026, 10, 8, 18, tzinfo=timezone.utc),
        timezone="America/Chicago",
        locale="en-US",
    ),
)
if isinstance(result, CompiledExpectation):
    payload = result.expectation  # The actual ExpectationCreate, not a copy.
    # Later authenticated orchestration submits payload to MCP capture_expectation.
    # This service performs no capture, evidence ingestion or evaluation.
```

JSON-only prompting is the portable default because model capability is unknown.
For a tested model/schema supporting native structured output, enable the flag;
it sends `outputConfig.textFormat` with the Pydantic JSON schema. Unsupported
schema/model errors fail safely; there is no silent capability downgrade.
Both paths parse a whole JSON document (optional single Markdown fence), reject
prose, Python literals, duplicate keys and non-finite numbers, and use strict
Pydantic JSON-mode validation. Valid JSON enum/UUID/date representations work;
string-to-number and invalid enum coercion do not. Downstream output models must
forbid extra fields and apply domain constraints. Schema validity is not evidence
that model interpretation is factually correct: deterministic services still
validate submitted expectations and evaluate evidence. Only complete `end_turn`
assistant text is accepted; truncation, tool execution or refusal blocks fail.

## Recovery and stable failures

Only throttling, connection/timeouts, model-not-ready and unavailable/internal
service errors retry, using the existing HTTP backoff base with exponential growth
capped at 5 seconds. AWS automatic retries are disabled so there is one owner.
Access denied, missing credentials, validation and unknown AWS errors do not retry.

Invalid JSON/schema gets at most one repair, retaining the original minimal
context and concise type/schema feedback, without echoing invalid model text or
Pydantic input values. Missing/unusable response content is not repaired.
Each generation has at most `1 + BEDROCK_MAX_RETRIES` attempts, so JSON is bounded
by `2 * (1 + BEDROCK_MAX_RETRIES)` total invocations including repair. Timeouts are
per connect/read, not an end-to-end deadline; callers should budget accordingly.
Retries/repair can incur extra inference charges. No writes occur in this layer.

Stable exceptions: `BedrockError`, `BedrockUnavailableError`,
`BedrockThrottledError`, `BedrockTimeoutError`, `BedrockResponseError`,
`BedrockValidationError`, `BedrockDisabledError`. Messages never contain AWS
payloads. Transport adapters map them to safe responses, without exposing
tracebacks or rendering model text as trusted markup.

## Privacy and telemetry

One event per logical call uses the existing JSON formatter/correlation ID:
operation/model, duration, retry/repair counts, result, validation, prompt version,
safe AWS request ID, aggregate input/output/total token usage and model latency.
Metadata is allowlisted to a short `prompt_version` label. It is never forwarded
wholesale to AWS. Operation names/version labels must be developer constants,
not user content. AWS SDK HTTP debug logs are suppressed by existing logging
configuration. No prompts, model outputs, headers, credentials or evidence logs.

`compilation_input` explicitly selects text, timezone and aware reference time;
it excludes the authenticated user/profile. This is field minimization, not a
universal secret detector: callers must never supply tokens in text. The
investigator selects evaluation snapshots and bounded numeric/boolean evidence,
excluding raw data, ownership, source text, claims and provider credentials.
Do not persist prompts by default. Treat all user/evidence content as untrusted
input and keep investigator output grounded in the returned evidence.
Compiler prompt version is `v2`; the implemented investigator uses `v2`.

## Verification

From `backend` with its existing virtual environment activated:

```sh
python -m pip install -r requirements.txt
pytest tests/test_bedrock.py tests/test_expectation_compiler.py
python db/scripts/bedrock_smoke.py
```

Default smoke prints SKIPPED and never makes an AWS call. To explicitly authorize
billed harmless inference, configure the enabled flag, region, model and credentials
privately, then run:

```sh
python db/scripts/bedrock_smoke.py --live
```

It checks reachability/model access and strict structured output. No database
writes or returned model content are printed. Normal pytest uses only mocks.
For local code checks install `requirements-dev.txt` and run from repository root:

```sh
backend/.venv/bin/ruff check backend/app/ai backend/tests/test_bedrock.py backend/db/scripts/bedrock_smoke.py
backend/.venv/bin/ruff format --check backend/app/ai backend/tests/test_bedrock.py backend/db/scripts/bedrock_smoke.py
backend/.venv/bin/mypy --strict --follow-imports=silent --ignore-missing-imports backend/app/ai backend/db/scripts/bedrock_smoke.py
```

These scoped checks do not reformat unrelated legacy backend modules. Runtime
boto3 is untyped here; a small protocol types the adapter boundary.

References: [Converse API](https://docs.aws.amazon.com/boto3/latest/reference/services/bedrock-runtime/client/converse.html),
[native structured output support](https://docs.aws.amazon.com/bedrock/latest/userguide/structured-output.html),
[Converse permissions](https://docs.aws.amazon.com/bedrock/latest/userguide/conversation-inference.html).


## Production expectation compiler

Public application interface:
`compile_expectation(text, context: CompileContext) -> CompileOutcome`.
`CompileContext` contains only aware `current_time`, validated IANA `timezone`
and optional locale. No identity, credentials, profile, unrelated records or
unvalidated continuation state enters the prompt. The MCP legacy adapter retains
its original authenticated context type but strips `user` before compilation;
it does not call any MCP tool.

The model emits a discriminated `CompileResult` envelope (a RootModel union):

- `CompiledExpectation`: `result="compiled"`, the existing `ExpectationCreate`,
  and exact utterance `grounding` quotes for subject/amount/comparison/sources.
- `ClarificationRequest`: `result="clarification"`, question, missing/ambiguous
  fields, partial interpretation, and structured reason code.
- `CannotCompile`: `result="unsupported"`, `UNSUPPORTED_EXPECTATION` and reason.

Schemas reject unknown fields and wrong result shapes. Successful model parsing
is followed by deterministic grounding and another strict validation of the
actual `ExpectationCreate`. Invalid model structure gets one foundation repair
with safe Pydantic error type codes (no input values, error locations or raw model
text). A repeated structure failure or semantic grounding failure raises stable
`CompilerError`; it never returns a bogus successful expectation. Missing facts
belong in clarification; infrastructure failures are errors, not clarifications.
Compiler sampling is explicitly temperature 0 even if another operation uses a
higher configured temperature.

### Meaning and grounding

Claim is preserved verbatim (trimmed). Subject quotes must exist in the utterance;
metrics normalize conservatively to snake_case. Grocery/electricity/utility
bill/cost/spending uses `total_cost`, matching the existing bill evidence and
simulator convention; package uses `package_delivery`. Other explicit subjects
normalize from their exact quote. Generic `my bill` requires clarification.

Numeric results require metric, an actual comparison enum and exactly one
operand. Direct limits are targets; stated previous amounts are baselines.
Each value requires a verbatim numeric proof span and the target must be linked
to its comparison. Last month's unstated number cannot be invented. Numeric
strings/booleans/invalid enums are rejected; decimal values, comma-separated
thousands, negatives and zero remain valid under the current schema. Negative
amounts are not universally forbidden by CountOn; individual integrations may
need additional domain checks.

Evidence sources must be explicitly selected using/from/via/source in the
utterance, with matching literal quotes. Mentioning a provider does not prove it
is connected. No source/connection/evidence is inferred. Materiality is assigned
from `ExpectationCreate`'s actual default **0.05** outside the model. The compiler
retains strict comparison enums; the existing evaluator's tolerance behavior
still applies. `/alexa` preserves the compiler-produced default rather than
overriding it with the former browser demo's zero tolerance. Requests for custom tolerance or recurring schedules return
unsupported instead of silently dropping those requirements.

The current schema has no currency field. For `total_cost`, explicit USD/US dollars
or caller-supplied `en-US` locale grounds the existing USD bill convention.
Unknown currency needs clarification. Non-USD amounts are not silently converted.
If locale is omitted by the legacy adapter, ambiguous dollars need clarification.

### Calendar rules

All dates derive from the explicit caller instant converted to its IANA timezone:

- `today`/`tomorrow`: that local day's end, 23:59:59.999.
- `this week`: Sunday 23:59:59.999, using the compiler's grounded calendar convention.
- Weekday: upcoming occurrence (including today if its deadline is still future).
- `next Tuesday` (or another weekday): next strictly future occurrence.
- `by/at/before 5 PM tomorrow`: explicit local clock time on the resolved date.
- Bare `5 tomorrow`, conflicting dates, DST gaps/folds, expired deadlines and
  unsupported date syntax require clarification. `after 5` is a window, not a
  single deadline. No temporal phrase means no invented deadline.

The conservative initial date vocabulary does not yet parse arbitrary absolute
calendar dates or every natural-language date phrase. Unsupported syntax asks
clarification rather than delegating unchecked calendar calculations to the model.
Temporal/event records are representable but their deterministic evaluation is
currently deferred and returns UNKNOWN. The compiler never claims they are
already operationally evaluated. Non-numeric negative/absence assertions cannot
be converted into positive assertions; the current boolean evaluator asserts True.
Changing appointments/records, absence windows and schedules need a richer contract.

### Clarification and injection safety

Supported reason codes: `MISSING_SUBJECT`, `MISSING_TARGET`, `MISSING_BASELINE`,
`AMBIGUOUS_COMPARISON`, `AMBIGUOUS_DEADLINE`, `AMBIGUOUS_CURRENCY`,
`MULTIPLE_EXPECTATIONS`. Questions use safe targeted templates or deterministic
calendar questions; arbitrary model instructions are not rendered as questions.
One-shot model partials retain **only the verbatim claim**. Model-invented
partial amounts, tokens or profiles are discarded. Stateful multi-turn continuation
is implemented in the separate grounded-patch
state machine. Do not treat user-supplied partial JSON as trusted facts; use
[the trusted-state application contract](clarification.md).

Utterances (including quoted instructions) are JSON user data in a separate message,
never interpolated into system instructions. Schemas, provenance checks and no
persistence/tool-execution capability provide independent safeguards. Prompting is
not a proof of semantic correctness: callers should present interpretation clearly,
clarify uncertainty, and never treat a model response as observed evidence. Multiple
independent expectations require one-at-a-time clarification, not automatic batches.

### Examples

With the context above, the grocery example's actual creation payload is:

```json
{
  "claim": "I'm counting on my grocery bill staying under $120 this week",
  "type": "numeric_comparison",
  "metric": "total_cost",
  "comparison": "less_than",
  "baseline": null,
  "target_value": 120,
  "deadline": "2026-10-12T04:59:59.999Z",
  "evidence_sources": [],
  "materiality_threshold": 0.05
}
```

For `My electricity bill should be lower than last month.`:

```json
{
  "result": "clarification",
  "question": "What baseline amount should I compare against?",
  "missing_fields": ["baseline"],
  "ambiguous_fields": [],
  "partial_interpretation": {
    "claim": "My electricity bill should be lower than last month."
  },
  "reason_code": "MISSING_BASELINE"
}
```

The compiler logs a safe result event (`compiled/clarification/unsupported/error`)
and duration/version. The underlying Bedrock event carries model, validation,
retry/repair count and usage under the same request correlation. No raw utterance,
proof quotes, model text, headers or tokens are logged. Tests use mocked Converse
responses through the actual strict parsing/repair path. Live model interpretation quality and IAM/model access must be evaluated
separately when enabling a deployment; the local orchestrator is implemented.


## Grounded Why? integration

The existing `explain_expectation_mismatch` MCP tool accepts only
`{"request":{"expectation_id":"<owned UUID>"}}`. Ownership precedes reads, and
the latest recorded evaluation gates investigation. MATCH, UNKNOWN and missing
evaluation skip the investigator. MISMATCH uses evaluation-anchored bounded real
evidence, the current Bedrock client, typed validation and safe telemetry.
Unavailable Bedrock, invalid citations or no useful evidence return a deterministic
fallback. The deterministic evaluator alone decides MATCH / UNKNOWN / MISMATCH;
Bedrock interprets/explains only and never changes evaluation.

Structured provenance retains expectation/evaluation IDs, selected evidence IDs,
Bedrock usage and fallback usage. These IDs are not spoken. Speech is rendered
from accepted grounded facts; credentials, provider payloads and unrelated data
are excluded. Constrained routing asks for disambiguation rather than choosing
an arbitrary owned expectation.

`tests/test_mcp_intelligence.py` exercises real MCP compile → clarification →
capture → PostgreSQL → deterministic evaluation → explanation, then a newer MATCH
which must skip investigation. Model responses are mocked; live model quality and
actual Alexa/Echo deployment remain separate validation/integration work.
