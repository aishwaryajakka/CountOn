# Expectation Lifecycle

The normal API, MCP, ASK adapter and web conversation share domain models. File
references below are under `backend/` unless stated otherwise.

## 1. User input

Web `/alexa` and the ASK adapter supply language to `AgentOrchestrator`. Identity
is verified separately. A body or spoken slot cannot select `user_id`, a trusted
plan, arbitrary tool, evaluation result or provider permission.

Structured `POST /api/v1/expectations` and MCP capture also exist for clients that
already have valid criteria. Those paths use the existing `ExpectationCreate`.

## 2. Compilation

`compiler_service` invokes the existing Bedrock compiler. Its typed result is a
compiled expectation, a clarification request or an unsupported result. Numeric
criteria require metric, comparison and either baseline or target. Grounding checks
require values and temporal meaning to be supported by the user's actual words.
Compilation neither saves an expectation nor evaluates evidence.

## 3. Clarification

`ClarificationState`, `clarification.py` and `clarification_facts.py` retain known
facts and ask the next missing material question. Corrections change the intended
fact; explicit topic switches replace the old draft. Cancellation, expiry,
unsupported input and turn limits close or reject state safely.

The orchestrator exposes an opaque owner-bound session reference. The MCP lifecycle
uses signed state plus `compilation_sessions`, locking/digests and expiry. Do not
put a bearer token in either state. “My last bill” selects the operand; it does
not supply an amount or authorize a historical-mailbox search.

## 4. Capture

Web conversations require explicit capture approval. Production ASK configuration
requires `ALEXA_REQUIRE_CONFIRMATION=true`. Complete, approved drafts call the
existing MCP `capture_expectation` with nested `request` and its capture ticket.
The ticket must match the payload and owner. Its durable receipt prevents another
row on replay. Plain structured capture has no general retry-idempotency promise.

## 5. Persistence

| Entity | Actual model and purpose |
| --- | --- |
| Expectation | `app/db/models/expectation.py`: owner, claim, type, metric, comparison, baseline/target, deadline, evidence sources, materiality, lifecycle status and compiler metadata. |
| Evidence | `evidence.py`: expectation, source/metric/value/unit, observation and ingestion timestamps, confidence, external/idempotency references and minimized metadata. |
| Evaluation | `evaluation.py`: expectation, deterministic result, expected/observed snapshots, confidence, reasoning, timestamp and run idempotency key. |
| Notification | `operations.py`: owned expectation/evaluation linkage, channel, message, status, metadata and dedupe reference. |
| AuditEvent | `operations.py`: owner, typed action/source/provenance, linked IDs, result and allowlisted action metadata. |

One Expectation has many Evidence and Evaluation records. Notifications reference
their owned Expectation and, when applicable, its Evaluation. Audit links retain
safe history; deleting a domain row can null its audit link rather than erase the
entire action record. Alembic defines the database contract, not inspection SQL.

Trusted creation metadata distinguishes `web`, `mcp`, `alexa_web` and
`alexa_skill`. Public expectation payloads cannot inject compiler metadata or owner.

## 6. Evidence ingestion

Provider source enrollment and exact binding confirmation precede automatic
imports. Email/calendar records use authorized connections and grounded identifiers
such as a thread/order ID or calendar UID; sharing a provider type is insufficient.
The public evidence API accepts user-submitted facts and cannot impersonate live
provider provenance. Simulator APIs require the named simulator in the expectation's
declared sources and stamp `SIMULATED_RING`/`SIMULATED_BEE` themselves.

The normalized record preserves source time and stable external identity. Replay
with the same identity and same payload reuses evidence; incompatible reuse fails.
History remains available even when an older observation arrives later. Relevant
direct evidence is selected by `observed_at`, not ingestion time alone.

## 7. Evaluation

Direct numeric/boolean evaluation uses the exact metric and declared sources.
Monitoring additionally checks bindings, access, freshness, conflicts and supported
time/coverage policies. Generic temporal/event direct evaluation is UNKNOWN.
The persisted snapshots explain what was checked at that moment, even if the
Expectation's current criteria are edited later.

MATCH normally fulfills an active expectation; MISMATCH contradicts it. UNKNOWN
preserves the current lifecycle status, including a previous result or terminal
status. Always read latest Evaluation and lifecycle status as distinct fields.

## 8. Notification

Eligible MISMATCH creates an in-app inbox entry in the evaluation transaction.
`pending` means the existing unread inbox state, not a promise of external email
delivery. MATCH does not create a mismatch alert; UNKNOWN does not resolve an old
mismatch episode. Evaluation/run and monitoring-observation dedupe suppress retries;
arbitrary new manual evaluations are not all the same run.

Preferences can disable alerts. Optional encrypted email outbox processing is
separate, opt-in and requires live delivery configuration. Alexa proactive delivery
is not implemented. Read/dismiss/sent/failure transitions use canonical audit paths.

## 9. Explanation

Why resolves an owned expectation and latest Evaluation. MATCH, UNKNOWN or no
Evaluation returns a deterministic answer without invoking the investigator.
Only MISMATCH selects real relevant evidence for the shared grounded investigator.
Unsupported citations or model failure yield a safe fallback. Internal metadata
retains expectation/evaluation/evidence IDs and Bedrock/fallback flags; speech
omits private details. The audit API records the receipt, not exact prior wording.

## 10. Audit/history

The normal `/activity`, expectation detail and notifications pages read real API
records. Creation/confirmation, clarification, evidence, evaluation, explanation and
notification events have trusted channel metadata and linked IDs. They do not
derive imaginary actions from a frontend status change.

## Examples

- **MISMATCH:** target `< $150`, DEMO bill $180 → recorded discrepancy, eligible
  notification and a Why grounded only in those observations.
- **MATCH:** positive DEMO delivery and SIMULATED Ring package observation before
  the saved Friday deadline → boolean delivery confirmation, no mismatch alert.
- **UNKNOWN:** SIMULATED Bee records a landlord's promise → commitment context,
  no observed arrival value, continued monitoring.

See [demo guide](demo-guide.md), [audit contract](audit-history-contract.md) and
[data policy](data-minimization-and-audit-policy.md) for operational details.
