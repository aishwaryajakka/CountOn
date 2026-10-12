# Typed source orchestration and bounded intelligence

This extends the existing CountOn application. It adds no agent framework, MCP
tool, credential store, compiler, clarification state format or database table.
The deterministic evaluator remains the only authority over MATCH/MISMATCH/UNKNOWN.

## Audit and decisions

| Capability | Existing component / improvement |
| --- | --- |
| Language and ambiguity | `AgentOrchestrator`, canonical Bedrock compiler, grounding and stateful clarification retained. “Make sure …” now routes to the same compiler. |
| Authenticated actions | The six MCP tools and nested `request` contracts retained; API JWT verification and restricted OAuth-client permissions unchanged. |
| Account access | Existing Gmail/Graph/Calendar OAuth, refresh, encrypted credentials, exact scopes and generation fencing retained. Metadata alone does not authorize a source. |
| Source planning | New typed `source_planning_service` searches bounded owned projections, asks one selection question and rechecks references on confirmation. |
| Evidence extraction | Existing conservative normalizers retained and extended with explicitly labeled calendar identifiers/timestamps and fractional-second delivery timestamps. No message body is retained or sent to a model. |
| Correlation | New deterministic monitoring policy permits at most four explicitly associated sources. Stable identifiers and current official projections are required. |
| Events and delivery | Existing verified push wake markers, periodic reconciliation, PostgreSQL leases/retries/fencing, transactional evidence/evaluation/inbox and opt-in email outbox retained. |
| Why / summaries | Existing grounded investigator and typed citations retained; only confirmed MISMATCH invokes it. Notification speech/text uses deterministic reason/metric templates, never arbitrary provider prose. |
| Cost controls | Authorization-scoped normalization cache, unchanged-projection suppression, model routing, per-process inference concurrency and aggregate token-usage budget added. |
| Evaluation | Synthetic golden corpus and benchmark added. Human review is an explicit unresolved release gate; automated agreement is not real extraction accuracy. |

## Dependency and deployment diagram

```text
Browser /alexa or signed ASK request
  -> existing authenticated orchestrator + durable conversation state
  -> canonical compile / continue -> complete expectation -> confirmed capture
  -> existing MCP Streamable HTTP -> existing services -> PostgreSQL

Owned web expectation detail -> review suggested sources
  -> authenticated FastAPI monitoring-plan preview
  -> owned, encrypted Gmail / Outlook / Google-MS Calendar projections
  -> exact source selection + explicit confirm
  -> reauthorize + atomic existing bindings + existing monitoring job

Verified provider wake hint or reconciliation poll
  -> existing source sync worker (lease/backoff/dead-letter)
  -> bounded official provider page -> cached rules-first normalization
  -> current version + generation -> stable source matching -> evidence
  -> durable monitoring wake -> deterministic single/correlated evaluation
  -> evaluation history + source references + deduplicated inbox/outbox
  -> dashboard / MCP / Alexa share the same persisted state

Bedrock: bounded compile / clarification / grounded confirmed-mismatch explanation
No model inside event publication, evaluation or notification SQL transactions.
The legacy Outlook polling worker also locks the account before expectation/job
publication, matching source confirmation/revocation. A real concurrent SQL test
checks this order to avoid account/expectation lock inversion.
```

Compilation and source selection are separate stages: save a complete expectation
using the existing path, then confirm which authorized sources may monitor it.
An unbound expectation does not fabricate facts or a mismatch. The current voice
adapter does not conduct source-account/order-selection dialogue: finish that
permission-sensitive step in the web detail view. Restricted Alexa OAuth tokens
cannot manage provider accounts or call the new plan endpoints. Do not expand
those permissions merely to bypass this boundary.

## Typed monitoring plan

Normal Supabase web authentication is required. Responses use `Cache-Control:
no-store`. Neither endpoint accepts user ID, provider URL, token, model prompt,
raw evidence, SQL, or a browser-authored trusted plan.

```text
POST /api/v1/expectations/{owned_id}/monitoring-plan/preview
{}
```

Optional filters are exact `order_id`, `calendar_uid`, and aware `expected_start`
for unchanged-meeting criteria. The server returns:

- `ready`: one stable association group; select its account references and confirm.
- `clarification`: multiple orders/events/threads or a missing material criterion;
  one question, bounded candidate references, no mutation.
- `permission_required`: authorize and synchronize a supported account first.
- `unsupported`: terminal expectation or unsupported evidence metric.
- `bounded`: too much candidate data; use the manual exact-source controls.

Search is capped at 20 authorized streams, 200 projections and 20 returned choices.
The cap is global, not a promise of full-inbox search. It deliberately abstains on
overflow, stale streams, corrupt projections or missing scope/credentials. Account
display names and subject/title labels are presentation data, never instructions
or proof that records are related.

```json
{
  "confirmed": true,
  "query": {"order_id": "123-1234567-1234567"},
  "sources": [{"sync_id": "<returned UUID>", "external_id": "<returned reference>"}]
}
```

Send this to `POST /api/v1/expectations/{owned_id}/monitoring-plan/confirm`.
The server recomputes the plan, rechecks ownership/permissions and encrypted grant identity,
and serializes account → stream → expectation locks in deterministic order. It refreshes
cached SQL identities before checking cancellation or credential removal, then uses
existing bind/wake services in one transaction.
It rejects foreign/stale references, unrelated groups, two rules for one stream,
and silent removal/overwriting of prior choices. Repeating the same confirmed
selection returns the existing job/bindings without resetting its run key, pause,
completed state or dead letter. Failure on a later binding rolls back the whole plan.

Preview checks enabled provider configuration, required read scopes, encrypted account identity
and access/refresh grant usability without performing network requests. An expired access
token with a valid local refresh grant can remain eligible; an expired token without a
refresh grant cannot. Remote revocation is detected when the provider reports it, not by
guessing from cached data. Known disconnection/auth failure denies further use.

Candidate responses include a short rules-based `suggestion_reason`, `synced_at` and
`sync_status`. The UI clears selections when filters change or confirmation fails,
requires fresh discovery after stale-plan errors, and guards duplicate submissions.

Existing manual bind/unbind and tracking controls remain available. No calendar,
email or external account is modified by source selection.

## Correlation, chronology and certainty

Matching defaults to exact sender/thread/message/recipient/event IDs. The new planner
uses sender + exact order ID for orders, allowing updates in a different email thread.
It never invents merchant senders, packages, account connections or tracking IDs.

For multiple bindings:

- Unrelated identities, over four bindings or unsupported associations remain
  `UNKNOWN/ambiguous_sources`.
- Order references require the same exact order ID. Prediction-only updates may
  issue one deduplicated potential-delay warning while the evaluation remains
  UNKNOWN. `package_delivery` from the canonical compiler now shares the existing
  `delivery_reported` ingestion path. A delivery statement without an explicit
  occurrence timestamp cannot use email receipt time as arrival time. Current reports
  from different selected accounts must agree on both result and arrival time; a later
  alleged arrival never resolves conflicting reports.
- Calendar/email references require the same `calendar_uid` and occurrence/start
  criteria. Google `iCalUID` and Graph `iCalUId` are official identifiers, not event
  titles. Recurring series identifiers alone cannot identify one occurrence;
  the planner skips a recurring record lacking its original occurrence start.
- Current calendars are authoritative over older email references. A newer
  contradictory email requires reconciliation (UNKNOWN). Two current conflicting
  calendars remain UNKNOWN, including different rescheduled start times even when
  both individually mismatch. Policy `stable_sources_v2` participates in fingerprints;
  AI never chooses a winner.
- Every selected source must still be available, fresh and grounded against its
  current encrypted projection/version/generation. Stale, missing, malformed or
  conflicting observations abstain rather than letting a good source hide a bad one.
- Evaluation metadata preserves all evidence/binding IDs, per-source results,
  authoritative evidence IDs, primary reason and correlation policy version.

Email sender identity and delivery statements are provider-reported data, not
proof of sender authenticity, carrier telemetry or physical fulfillment. Distinct
packages/occurrences that lack a safe common identifier require explicit selection.
No consumer Amazon account API or semantic entity resolution was added.

Identifier semantics: [Google Calendar events](https://developers.google.com/workspace/calendar/api/v3/reference/events),
[Microsoft Graph event resource](https://learn.microsoft.com/en-us/graph/api/resources/event?view=graph-rest-1.0).
Google recurring instances use `originalStartTime`; Graph occurrences/exceptions use
UTC `originalStart`. Graph `iCalUId` can differ per occurrence, unlike a Google series
UID. Calendar UID formats/occurrence conventions can differ; unmatched IDs are not guessed.

## Efficiency and trusted configuration

`ExtractionCache` is a 256-entry, 900-second, process-local LRU. Its key includes
verified owner, connection, OAuth generation, scopes, stream, source reference,
operation, normalizer version and input content hash. It stores minimized facts,
never message bodies/tokens/prompts. No auth context means no cache. Outputs are
copied to prevent caller mutation; capacity/TTL bound retention. One lazy daemon timer
per cache removes expired facts even while the process is idle; `close()` clears entries
and cancels its timer. `normalization_v3` explicitly versions the extractor. Reconnection or
changed content/scope/generation cannot reuse an old entry. Cache loss requires
normalization again and has no effect on authorization or durability.

The cache saves deterministic parsing, not provider API calls. Existing incremental
cursors/pagination control network volume. Official messages are still synchronized
under the existing read-only enrollment; no complete inbox/calendar is sent to Bedrock.
Ambiguous natural-language evidence is omitted or clarified. There is deliberately
no LLM-per-event fallback or fuzzy automatic association.

Trusted backend settings in `backend/bedrock.env.sample`:

```env
BEDROCK_MAX_CONCURRENT_CALLS=4
BEDROCK_MAX_TOTAL_TOKENS=8192
# Optional; absent overrides use BEDROCK_MODEL_ID:
# BEDROCK_COMPILER_MODEL_ID=<approved model/profile>
# BEDROCK_INVESTIGATOR_MODEL_ID=<approved model/profile>
```

Compile/continue use the compiler override; confirmed-mismatch investigation uses
the investigator override. Model selection is trusted configuration, not user/model
input. No cheaper model was silently selected. Verify model access, structured-output
compatibility and grounded quality before assigning task models. The existing
[Converse client](https://docs.aws.amazon.com/boto3/latest/reference/services/bedrock-runtime/client/converse.html)
and AWS provider chain remain canonical.

Inference attempts share a process-local semaphore, including queue wait in the
existing operation deadline. Socket timeouts, retry owner and bounded repair remain.
The aggregate budget checks actual reported input/output usage across retries/repair
and bounds requested output tokens. It stops further work when exhausted; it is not
a pre-invocation billing guarantee or a hard cancellation of an in-flight boto call.
Per-process limits do not enforce a cluster-wide concurrency/rate budget.

## Measurement and golden review

Existing metrics already report compile outcomes, clarification events, model latency,
usage, failures and monitoring attempt duration. Added bounded-label counters include:

| Metric | Interpretation |
| --- | --- |
| `source_plans`, `source_plan_latency_seconds` | Outcome count / summed latency, no private candidate labels |
| `evidence_extraction_cache` | Hit/miss; unchanged parsing avoided |
| `provider_duplicate_suppression` | Unchanged projection/evidence suppression |
| `provider_sync_results`, `provider_sync_records` | Page/complete/failure and bounded record counts |
| `provider_sync_latency_seconds`, `provider_reconciliation_seconds` | Attempt duration / completed reconciliation duration |
| `provider_wake_latency_seconds` | Accepted wake hint to completed round, when the hint is newly covered; coalesced hints are not individual events |
| `source_correlations` | Agreement/conflict/insufficient-source outcomes |
| `monitoring_outcomes`, `monitoring_unknown_reasons` | Final deterministic results / abstention causes |
| `monitoring_source_outcomes` | Intermediate per-source results, separate from final evaluation counts |
| `notification_delivery_results` | Confirmed outbox attempt result, not inbox read or recipient receipt |

Existing metrics sink is process-local and counters hold sums, not histograms.
Export/supervision is still required in deployment. Provider logs use the lease UUID
as `run_id`; no authorization header, private message, account address or credential
is added to metrics/logs. Real extraction accuracy, matching precision and evaluation
false positives/negatives require labeled human-reviewed data, not runtime guesses.

```sh
cd backend
source .venv/bin/activate
python db/scripts/orchestration_eval.py
python db/scripts/orchestration_eval.py --repeat 200
# Optional: TEST_DATABASE_URL must explicitly select a local loopback *_test DB.
python db/scripts/orchestration_eval.py --run-regressions
python db/scripts/orchestration_eval.py --require-human-review
```

`tests/fixtures/orchestration-golden.json` has 26 synthetic amount/ambiguity/injection,
calendar/reschedule/cancellation/DST, order-estimate/delivery and identifier-matching
cases, including Graph/Google recurring instances, recipient boundaries and order
association. The dataset also maps broader compilation, ambiguity, revocation, conflicting
evidence, worker recovery and model timeout/invalid-output coverage to existing suites.
The optional regression runner executes those suites and reports aggregate JUnit counts
without printing captured request/test output. Review expected results against the
fixture, policy and provider semantics;
record `review_status=human_reviewed` and the real `reviewed_by` only after an actual
review. Critical cases are currently pending. The strict command exits 2 until review;
CI runs the regression command, which cannot claim human acceptance. Reports separately
label synthetic agreement, human-reviewed results, mocked-provider
regressions, live providers and real Bedrock. Unrun/cloud categories remain BLOCKED.
A synthetic PASS never advances those gates. Existing compiler, clarification, deadlines,
investigator and real-SQL worker tests supplement the corpus.

Local results, exact commands and remaining release gates are recorded in the
[orchestration validation record](orchestration-validation.md).

## Operational limits

No schema migration or dependency installation is required for these changes; the
existing Alembic head remains `ac746eb3f145`. New rule fields use the existing JSONB
binding column. Deploy API and provider/monitoring workers from compatible source:
an older worker cannot enforce the new correlation fields. Review backups/rollout
and pass local checks before an explicitly authorized deployment.

Live Gmail/Graph/calendar consent, AWS access/model quality, ASK/Echo, production
worker recovery/metrics/edge limits and actual email receipt remain unverified here.
The earlier release probe found readiness/schema/image drift and expired AWS login;
see [production readiness](production-readiness.md). No production schema/deployment,
external account mutation, real notification send, commit or push was performed.
