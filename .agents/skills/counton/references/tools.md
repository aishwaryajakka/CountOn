# CountOn MCP contracts and examples

Use the host-configured endpoint. The configured remote address is
`https://counton-mcp.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com/mcp`.
Transport is Streamable HTTP, with the current user's Supabase bearer session.
The skill supplies instructions, not credentials or a connection implementation.
Discover all six tools before use; this file does not certify the latest deployment
or live Bedrock access.

## Contracts

| Tool | Input inside `request` | Structured output |
| --- | --- | --- |
| `list_expectations` | Optional `limit` (1–100, default 50), `offset` (>=0, default 0), `status`, `type` | `expectations` array, `limit`, `offset` |
| `get_expectation` | `expectation_id`: real UUID from user or owned list result | Compact expectation |
| `capture_expectation` | Existing `ExpectationCreate` fields below, optional actual `compilation_state` | Saved compact expectation |
| `compile_expectation` | `text` (1–2000), IANA `timezone`, optional `locale`, `conversational`, stable `compilation_id` | Compilation result and lifecycle state; never saves an expectation |
| `continue_expectation_compilation` | Actual signed `state`, `answer` (1–2000) | Question, compilation, cancellation or safe failure |
| `explain_expectation_mismatch` | Actual owned `expectation_id` | Real evaluation result, grounded explanation or no-evaluation/non-mismatch message |

Compact fields are `id`, `claim`, `type`, `status`, `metric`, `created_at`.
Core tools remain compact. Compilation returns structured expectations; explanation
returns real evaluations and grounded factors. No generic evidence mutation tool exists. Page length is not a total count unless all pages were read.
Hosts may namespace names; choose the matching discovered CountOn tool.

Capture accepts nonempty `claim`, `type`, and optional `metric`, `comparison`,
`baseline`, `target_value`, timezone-aware `deadline`, `evidence_sources`, and
`materiality_threshold` (0–1, default 0.05). Numeric comparisons require metric,
comparison, and baseline or target. An actual returned `capture_state` is supplied
as optional `compilation_state`; it binds the final payload to its durable capture
receipt. Other extra fields, including identity, are rejected.

- Types: `numeric_comparison`, `boolean`, `temporal`, `event`.
- Comparisons: `less_than`, `less_than_or_equal`, `greater_than`,
  `greater_than_or_equal`, `equal`, `not_equal`.
- Stored statuses: `monitoring`, `fulfilled`, `contradicted`, `unknown`,
  `resolved`, `cancelled`. Status is neither capture input nor evaluation result.

Discover live schemas first. Repository contracts are in
`backend/app/mcp/schemas.py`, `backend/app/schemas/expectation.py`,
`backend/app/db/models/expectation.py`, and `frontend/lib/types.ts`.

## List

“What am I counting on?” → `list_expectations`:

```json
{"request":{"limit":50,"offset":0}}
```

Summarize actual claims and stored statuses. An empty complete list means
“You're not counting on anything yet.” Never generate demonstration rows.

## Detail

“Tell me about my electricity bill expectation.” → list first and match actual
claim/metric. If exactly one matches, get its returned UUID. For illustration
only, if an owned list result supplied this UUID, use:

```json
{"request":{"expectation_id":"12345678-1234-4234-8234-123456789abc"}}
```

Do not reuse this illustrative ID unless actually returned. Clarify multiple
matches; report no match honestly. Show returned fields without inventing amounts
or evaluations.

## Capture

“I'm counting on my grocery bill staying under $120 this week.”

Establish timezone/locale and call `compile_expectation` with this actual text.
Use clarification/continuation if requested; otherwise pass the returned structured
expectation unchanged to `capture_expectation`, including the returned `capture_state`
as `request.compilation_state` for replay-safe capture. Do not manually create a static
capture object or change the compiler's configured materiality threshold. The
compiler resolves the real reference time server-side; never copy an example date.
On success: “Got it. I saved that expectation in CountOn.” Link the returned ID
to the host-configured frontend's `/expectations/{id}`. Do not claim evidence,
evaluation, automatic ingestion or a notification was created.

## Clarify and disclose limits

“I'm counting on my bill being lower.” → compile, then ask the returned question
(for example “Which bill should I monitor?”). Continue one material question at a
time using the actual returned state. Wait for missing facts;
do not infer `total_cost`, baseline or provider from other examples.

“Why did it fail?” → List/match the owned record, then call
`explain_expectation_mismatch`. Report only its actual result and grounded factors;
retain uncertainty and fallback caveats. Do not guess a cause.

Missing/rejected auth → host sign-in. Unavailable server → disclose connection
failure. Validation error → clarify inputs without raw upstream errors. An
inaccessible UUID is not permission to enumerate another user's records.


## Intelligence examples

Compile using the user's actual text and established calendar context:
```json
{"request":{"text":"I'm counting on my grocery bill staying under $120 this week","timezone":"America/Chicago","locale":"en-US"}}
```
Compilation result: `status` compiled/clarification/cancelled/expired/unsupported/error,
`message`, nullable `expectation`/opaque `state`/`capture_state`/`code`, `bedrock_used`,
`prompt_version`, `clarification_turn`. Only a compiled expectation goes to capture.
Continuation:
```json
{"request":{"state":"<actual returned signed state>","answer":"My electricity bill"}}
```
Explanation:
```json
{"request":{"expectation_id":"<actual owned expectation UUID>"}}
```
Explanation response: `result` MATCH/UNKNOWN/MISMATCH/null, `evaluation_id`,
`message`, nullable `code`/`explanation`, `bedrock_used`, `fallback_used`,
`expectation_id` and selected real `evidence_ids` for internal provenance. Do not
speak private UUIDs. Explanation contains
immutable expected/observed, factors, caveats, confidence note and references.
NO_EVALUATION and NOT_MISMATCH never invoke investigation. NO_EVIDENCE and
INVESTIGATION_UNAVAILABLE accompany deterministic summaries when appropriate.
These limitations are not permission to create evidence or reevaluate.
