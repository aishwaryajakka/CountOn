# Amazon Bedrock

## Purpose and boundary

`backend/app/ai/bedrock_client.py` is the shared boto3 Bedrock Runtime adapter.
It calls the non-streaming **Converse API**. The compiler, clarification engine
and mismatch investigator use it; they are the model-based specialists in this
repository. Provider normalization, source planning, routing, monitoring and
evaluation are deterministic Python services.

**Bedrock cannot decide final MATCH / UNKNOWN / MISMATCH.** It has no database
session, provider-connection authority or tool-execution loop. Services validate
its output before an independent action can persist an expectation. Live model
availability, account permissions and latency are not established by unit tests.

## Model configuration

The existing `Settings` loads ignored `backend/.env.local`; environment variables
override it. These defaults are verified in `app/core/config.py`:

| Variable | Default / role |
| --- | --- |
| `BEDROCK_ENABLED` | `false`; disabled calls fail safely before runtime creation |
| `AWS_REGION` | `us-east-2` |
| `BEDROCK_MODEL_ID` | `openai.gpt-oss-120b-1:0` |
| `BEDROCK_MAX_TOKENS` / `BEDROCK_TEMPERATURE` | `1000` / `0.1` |
| `BEDROCK_REQUEST_TIMEOUT_SECONDS` | `30`, SDK connection/read timeout |
| `BEDROCK_OPERATION_TIMEOUT_SECONDS` | `45`, checked around inference/retry work |
| `BEDROCK_MAX_RETRIES` | `2`, selected transient failures only |
| `BEDROCK_MAX_CONCURRENT_CALLS` | `4`, process-local semaphore |
| `BEDROCK_MAX_TOTAL_TOKENS` | `8192`, logical-call budget including repairs |
| `BEDROCK_NATIVE_STRUCTURED_OUTPUT` | `false`; native schema output is opt-in |
| `BEDROCK_COMPILER_MODEL_ID` / `BEDROCK_INVESTIGATOR_MODEL_ID` | Optional task-specific overrides; otherwise the common model |

The SDK obtains credentials from its normal provider chain. Do not pass credentials
to the frontend or put them in templates. Runtime access requires `bedrock:InvokeModel`
and account/model permissions for the selected model or inference profile. A
Lightsail container must be provisioned with an actual supported credential source;
this repository does not establish that a workload role is attached.

See [setup](setup.md), `backend/bedrock.env.sample` and [deployment](deployment.md).
Model IDs are configuration, not a claim of currently granted AWS access.

## Compilation flow

`compiler_service.compile_expectation(text, context)` uses the existing compiler
and `CompileContext` (trusted current time, timezone, locale). `CompiledExpectation`,
`ClarificationRequest` and `CannotCompile` form the typed result contract. Grounding
requires real utterance spans, supported criteria and conservative temporal parsing.
The compiler reuses `ExpectationCreate`; no second persistence schema is introduced.

A compiled result is not saved or evaluated. The conversational orchestrator asks
for approval, then sends the compiler ticket and structured payload to MCP capture.
See [compiler implementation](../backend/app/ai/README.md) for detailed semantics.

## Clarification flow

The existing stateful engine combines known facts with a typed patch for the next
answer. It preserves established fields, checks corrections, replaces explicit new
topics and enforces expiry/turn/context limits. It sends selected state and the
current answer, not a full transcript. “My last bill” cannot become a made-up
baseline; an actual amount is required by numeric capture.

The signed MCP state and durable compilation ledger enforce ownership and replay
consumption. They are distinct from the encrypted conversation transport store.
See [clarification reference](../backend/app/ai/clarification.md) and [security](security.md).

## Mismatch explanation flow

The explanation boundary loads an owned Expectation and its latest persisted
Evaluation. MATCH, UNKNOWN and absent evaluation return controlled messages without
model investigation. MISMATCH selects relevant persisted evidence and assigns
bounded internal labels such as E1 and E2.

`InvestigatorDraft` permits structured factor kinds and cited values, rather than
an unconstrained causal essay. Post-validation checks actual evidence IDs, values,
direction and conflict rules. Unknown citations or unsupported factors are rejected.
Backend rendering constructs the explanation. Outcome fields are backend-authored,
not model decisions. Missing evidence, conflicting evidence and Bedrock failure
produce an appropriately qualified deterministic fallback.

`investigation_service.py` owns explanation execution; `investigator_service.py`
loads the owned records. [Investigation reference](../backend/app/ai/investigation.md).

## Validation, repair and failure behavior

Pydantic generates JSON Schema for the prompt and validates complete JSON in strict
JSON mode. Parsing rejects arbitrary prose, duplicate keys, non-finite numbers and
unsupported response blocks. A single enclosing JSON code fence is supported.
There is **one bounded JSON repair** after parse/schema failure; invalid raw output
is not echoed into the repair prompt. Semantic grounding failures fail conservatively.

Native `outputConfig.textFormat` uses the same schema only when explicitly enabled
for a verified model. Unsupported capability does not silently become successful
unvalidated text. SDK retries are disabled so CountOn owns retry counts. Selected
timeouts/throttling/service errors use bounded exponential backoff through the
configured HTTP backoff; credential, access and configuration failures are not
repeated blindly. Socket timeouts and surrounding budgets do not imply that a
cancelled remote write was undone. Capture reconciliation still uses its ledger.

## Metrics and privacy

`CallTelemetry` records operation, duration, safe request ID, retries, repairs,
validation result and token/latency usage when supplied by AWS. Counters are
process-local; there is no durable cross-replica billing or metrics store.
`/metrics` requires its configured operations credential. Raw prompts, responses,
reasoning blocks, tokens and arbitrary provider metadata are excluded from logs.

Selected text/facts do reach the configured model during inference. Review that
processing and database retention against the deployment's privacy requirements.
The compilation ledger retains typed JSON state; do not mistake a signed reference
for encrypted contents. See [security](security.md).

## Verification

Offline tests inject the runtime and test real parser/grounding behavior. They do
not require AWS credentials. From a configured backend:

```sh
python -m pytest -q tests/test_bedrock.py tests/test_expectation_compiler.py tests/test_clarification.py tests/test_mismatch_investigator.py
python db/scripts/aws_preflight.py --verify-identity
python db/scripts/bedrock_smoke.py --live
```

The last two are opt-in live checks, not prerequisites for offline tests. Review
the smoke script and enable Bedrock deliberately before incurring an AWS request.
[Rollout](bedrock-integration.md) retains component integration details;
[testing](testing.md) records commands actually executed for this documentation pass.
