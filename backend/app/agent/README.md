# Controlled CountOn orchestrator

This backend foundation is a bounded traffic controller, not an autonomous agent.
It is wired to `/alexa` through the Next.js `/api/agent` proxy and authenticated
FastAPI `/api/v1/agent/converse` endpoint. MCP registration/Streamable HTTP,
compiler, clarification ledger, investigator,
evaluators and database schemas remain unchanged. The existing signed-state
encoder now canonicalizes JSON ordering so JSONB round trips preserve replay
digests; its state/signature format and decoder remain compatible.

## Audit and canonical boundaries

Intent routing, owned record selection, contextual reads and compile/continue/
capture sequencing live in this package. The former browser router/matching and
Next.js conversation sequencing were removed. The browser sends only text and an
opaque handle; `/api/mcp` is discovery-only and rejects browser-selected tools.

The six existing MCP tools remain the capability source of truth. Compiler and
clarification live in the current AI modules/`compiler_service`; signed state and
capture replay use the canonical `ClarificationState` and `compilation_sessions`.
`investigation_service` handles loaded typed data; `investigator_service` handles
owned DB orchestration. The existing MCP explanation tool owns latest-evaluation
and evidence reads. Only the deterministic evaluator decides outcomes.

## Actions and static registry

| Agent action | Approved capability |
| --- | --- |
| LIST_EXPECTATIONS | `list_expectations` |
| GET_EXPECTATION | `get_expectation` |
| COMPILE_EXPECTATION | `compile_expectation` |
| CONTINUE_CLARIFICATION | `continue_expectation_compilation` |
| CAPTURE_EXPECTATION | `capture_expectation` |
| EXPLAIN_MISMATCH | `explain_expectation_mismatch` |
| CANCEL | `continue_expectation_compilation` with canonical cancellation text; closes active state |
| UNKNOWN | No tool |

The registry is a read-only mapping of enum keys to immutable tool tuples. Plans
must match it exactly. `UNKNOWN` cannot carry executable tools. No model selects
tool names, no tool aliases are added and no arbitrary MCP method is accepted.

## Typed plan and execution

`AgentInput` accepts one bounded utterance, optional expectation UUID and private
signed continuation reference, timezone/locale and a stable compilation UUID.
Identity is separate: the trusted host supplies an `AuthenticatedUser` **after
existing JWT verification**, never from user JSON. An explicit UUID does not prove
ownership. Without a UUID, get/why resolves a specific topic through the existing owned MCP list;
constrained owned text matching/disambiguation is available through `handle`.

`AgentPlan` is strict/frozen and includes action, optional expectation ID,
`requires_evidence`, exact allowed tool enums, signed state, bounded optional
confidence, reason enum and typed metadata containing only a request UUID.
Compile/continue additionally carry one private utterance/context; capture requires
the existing `ExpectationCreate` plus an actual compiled capture ticket. No
SQL, arbitrary JSON metadata, identities or outcome/verdict fields are accepted.
There is no model routing here; confidence is normally absent.

At execution, plans are revalidated. Reasons and tools must match the action exactly; even a hand-crafted compile
plan needs explicit monitoring intent. Signed state is decoded using the existing
user-bound verifier and must have the appropriate canonical lifecycle/expiry.
Capture must match the signed compiled payload exactly. Existing MCP ledger checks
remain authoritative for consumed/replaced/cancelled state and atomic replay safety.

The default `CountOnMcpAdapter` uses the **real Python MCP SDK in-process client**
and existing registration with the host's verified principal. It always sends
`{"request": {...}}`; the registered tools perform owned business-service reads/
writes. The orchestrator has no database session, SQL, provider payload, evaluator
or Bedrock client. Its injectable adapter accepts only six enum/typed request pairs.
The web API uses the request-scoped `StreamableMcpAdapter`, which performs real
SDK connection/discovery/calls to configured `MCP_PUBLIC_URL`, forwarding only the
current validated user's bearer token. It disables redirects and sends nested
`request` arguments. Credentials never enter the long-lived store. The separate
public MCP server and its six registrations remain unchanged.

An explicit capture intent compiles/continues first. Only a complete result with a
valid ticket creates a separately validated capture plan; at most two capabilities
run in one execution. Incomplete/unsupported/failed results never capture. No retries
are introduced; stable compilation IDs and the existing capture ledger protect
replay. Corrections, new topics, unrelated replies, cancellation and max-turn logic
are delegated to the existing engine. List/get/why can interrupt without consuming
active state. `handle_session` retains the reference on the trusted backend;
stateless `handle` callers must still retain it themselves.

Topic resolution uses the existing Alexa claim/metric term-matching behavior,
through approved MCP list calls only. It asks for selection when multiple owned
records match and returns safe not-found when none match. It checks subsequent
pages before selecting a unique result, with a 1,000-row bound; at that bound it
asks for an explicit record instead of guessing. Stateless callers need an explicit ID for pronouns (`it`/`this`/`that`).
Session callers may use the previously selected ID after a fresh MCP ownership check. Candidate lists are capped at ten and may
be partial; hosts should allow narrowing or actual UUID selection. Selection is
not a new persistent state machine; the next request supplies the selected ID and
MCP verifies ownership again.

`EXPLAIN_MISMATCH` delegates relevant evidence reads to the existing explanation
tool; its name/`requires_evidence` flag does not assert a mismatch. The latest real
MATCH, UNKNOWN or absent evaluation skips investigation. MISMATCH alone permits
the existing grounded investigator/fallback. `AgentResult` exposes typed actual
records/provenance and a concise message; it never generates a verdict. Its
`answer` aliases the conversational message, `clarification_required` includes
record disambiguation, and `captured` is true only after a successful capture.
`compiled_expectation` retains the canonical final payload internally.
`expectation_id`, `evaluator_status`, `bedrock_used`, and `fallback_used` preserve
actual capability metadata. `trace_events` contains only approved action/tool
labels. `safe_to_say` approves only the message/answer for speech, never the full
internal result. Capture failures retain known compiler-use metadata and ask the
user to check their records before retrying; no automatic write retries occur.

## Host usage

From a trusted backend host, after existing authentication:

```python
from app.agent.models import AgentInput
from app.agent.orchestrator import AgentOrchestrator

agent = AgentOrchestrator()
request = AgentInput(text="What am I counting on?")
plan = agent.plan(verified_user, request)
result = await agent.execute(verified_user, plan)
```

For capture, keep the same `AgentInput.compilation_id` when reconciling a retry.
For continuation, use the actual returned secret reference. Plans/results are
internal contracts: `SecretStr` masks references in normal serialization/repr.
A later transport must deliberately pass only an active handle through its private
session mechanism, retain capture tickets server-side and speak `result.message`.
Do not serialize raw plans, full chat history or internal provenance into speech.

## Security, audit and limitations

Strict models reject user/owner IDs, verdict injection, unknown actions/tools,
wrong tool/action pairs and arbitrary methods/DB operations. A conservative text
guard rejects requests to call hidden/admin tools, change identities or force an
evaluation. This guard is not a universal prompt-injection detector: closed
capabilities, existing compiler grounding, signed state and ownership enforce the
actual execution boundary even when novel wording is not recognized.

Operational events reuse the existing structured formatter/correlation context:
user ID, approved tool, result status and duration. No utterance, state, token,
AWS credentials, private provider payload, chain of thought or exception content
is logged. No new audit table/event writes are introduced; real MCP mutations keep
existing transactionally recorded business audits. Metadata does not authorize or
select capabilities.

No new providers, workers, frontend features, unrestricted planning or database
redesign is included. Local tests use mocked inference and isolated PostgreSQL;
this package does not establish live production intelligence/Alexa readiness.

## Verification

From `backend`, activate the existing `.venv` and privately configure a separate
loopback `TEST_DATABASE_URL` ending in `_test` for persistence/ownership cases:

```sh
pytest -q tests/test_agent.py tests/test_agent_sessions.py tests/test_mcp.py tests/test_mcp_intelligence.py \
  tests/test_compilation_lifecycle.py tests/test_mcp_services.py
ruff check app/agent tests/test_agent.py tests/test_agent_sessions.py
ruff format --check app/agent tests/test_agent.py tests/test_agent_sessions.py
mypy --strict --follow-imports=silent --ignore-missing-imports app/agent
```

Without the isolated database configuration, DB tests skip. The tests cover closed
policy/injection, state integrity/expiry/owner binding, capture gating, exact replay,
real MCP owned reads/ambiguity/pagination, shared FastAPI persistence, multi-turn
clarification/correction/cancellation, unavailable/malformed inference, and
deterministic explanation gates/fallback provenance.
See [MCP docs](../../../docs/mcp.md) and
[existing Bedrock orchestration](../../../docs/bedrock-integration.md).


## Minimal trusted conversation state

`AgentSessionState` is strict/frozen and server-only. It contains exactly version
(`v1`), session UUID, selected expectation UUID, private canonical clarification
reference, last approved action, up to ten pending UUIDs, created/expiry timestamps,
and a READY/COMPLETED/CANCELLED draft marker. It stores no transcript, utterances,
JWT/auth tokens, AWS credentials, prompts, model outputs, provider payloads or
chain of thought. Authentication identity lives separately in the private store
entry and is never accepted from user JSON. The clarification reference points to
the existing signed compiler state/ledger; this does not change what that canonical
clarification subsystem retains or introduce another copy of its facts/history.

`handle_session` returns `AgentSessionResult`: the typed result plus a private
opaque handle. Browser JSON cannot set selected IDs, owners, tools, lifecycle or
compiler state. The authenticated web route returns only the opaque
session handle with the approved conversational response. The handle is a random
256-bit lookup key; only its SHA-256 digest is stored, bound to verified identity.
It is not a bearer authentication token and reveals no state. There is no new
client-side JSON state/signature format. The internal clarification reference
continues to use the existing user-bound signature/version/expiry verification.

A turn is serialized under the session lock and then rotates its handle. Concurrent
or repeated requests carrying an old handle fail closed with the same safe response
as unknown, cross-user, tampered or expired handles. The existing MCP database
ledger still owns durable capture idempotency and consumed clarification checks.
A completed/cancelled draft clears its reference; its current session can start a
new request, but terminal answers cannot replay the old draft. Keep stable initial
compilation IDs when reconciling retries; do not blindly retry saves.

`it`, `this`, `that`, `that expectation`, `why did it fail`,
`what happened with that`, and `check it again` resolve only one selected record.
Reuse always performs an owned MCP get first. An explanation then calls the
existing explanation tool, which rechecks ownership/evaluation. Missing/stale
selection asks which expectation or fails safely; it never chooses the newest row.
An ambiguous result clears selection and retains at most ten candidate UUIDs.
The next request may provide a listed UUID or an exact ordinal such as
`the second one`. Both are re-authorized via MCP. Candidate lists can be partial;
users can also restate a more specific topic. No fuzzy guess or unbounded search
is introduced.

Active drafts automatically delegate answers, corrections and explicit topic
changes to the existing continuation engine. Reads/list may interrupt without
losing the active reference. Cancellation closes active canonical state, clears
selection/pending/draft context and leaves the session usable. Policy rejection
retains the draft without executing tools. `reset_session` explicitly cancels an
active draft before discarding its record and creates a fresh session ID; if
cancellation is unavailable, it preserves the draft for a safe reset retry.

The in-memory store defaults to 1,024 live sessions and uses the existing
`clarification_ttl_seconds` as a fixed maximum session lifetime (15 minutes by
default). The compiler's own expiry is checked as well. Expiry is not extended by
activity. Expired entries are pruned; live entries are never silently evicted.
Restart drops context safely. **This store is single-process/event-loop only**;
reuse one orchestrator/store per backend host. Multiple workers or replicas need a
shared atomic store or explicit sticky routing before deployment; no distributed
storage, database migration or generic chat memory is added here.

Trusted-host example, after existing JWT verification:

```python
# Keep this instance/store alive across requests in one backend process.
agent = AgentOrchestrator()
turn = await agent.handle_session(
    verified_user, AgentInput(text="Tell me about my electricity bill")
)
turn = await agent.handle_session(
    verified_user, AgentInput(text="Why did it fail?"), turn.session_reference
)
reset = await agent.reset_session(verified_user, turn.session_reference)
```

## Web integration and deployment

```text
/alexa → Next.js /api/agent → FastAPI /api/v1/agent/converse
→ JWT-verified principal → session/orchestrator
→ real MCP Streamable HTTP → existing tools/services → Supabase
```

The narrow request schema accepts only `text` and opaque `session_reference`.
FastAPI reuses existing Supabase JWT verification/profile ownership. Locale comes
from the validated Accept-Language header; timezone uses the authenticated saved
profile, defaulting to UTC if none is configured. No browser plan, tool, user ID,
evaluator status, expectation UUID or raw compiler state is accepted at this route.
Responses explicitly project safe speech, compact owned rows, capture link,
rotated opaque handle and closed trace labels. No compiler payload/ticket,
evidence/evaluation provenance, raw model output or credentials are returned.

Frontend configuration stays `NEXT_PUBLIC_API_BASE_URL` and the existing Supabase
public variables. `COUNTON_MCP_URL` on Next.js is used for discovery only. Set API
`MCP_PUBLIC_URL` to the same MCP endpoint. Configure the **same strong
COUNTON_CLARIFICATION_SIGNING_KEY on FastAPI and MCP**, including separate local
processes; process-random development keys cannot verify each other's tokens.
Keep AWS credentials only in the MCP/backend runtime provider chain. Deploy the
API change before enabling the updated frontend. No database migration is needed.

The API lifespan owns one bounded session store. Sessions remain single-worker,
in-memory; restart/refresh/user switch requires restating context. Multiple workers
need shared atomic storage or sticky routing before rollout. SDK/proxy timeouts
never automatically retry writes; lost save responses instruct users to check the
dashboard. Local signed-JWT/HTTP/persistence tests are not production deployment
validation or completed Alexa/Echo integration.

## Traditional Alexa transport

`POST /api/v1/alexa` verifies original signed ASK requests and the configured
skill ID, then authenticates the linked token through the existing Supabase JWT
verifier. The transport adapter translates ASK intents into inputs for this same
orchestrator. It retains only a bound opaque handle and safe retry responses;
canonical compiler/clarification/evaluation/investigation semantics stay here and
in existing MCP/services. Initial compilation IDs reuse the durable ledger to
avoid duplicate rows on request retry after restart. `AgentSessionStore.discard`
revokes terminal transport context without creating a replacement session.

See [Traditional Alexa setup](../../../docs/traditional-alexa.md) for the model,
account-linking gap, request verification, single-worker/deadline limits and manual
console acceptance. Local adapter tests do not claim Alexa/Echo deployment.

## Minimal trust boundary

Source policy, typed TrustResponse, per-run audit_events and safe web provenance
are implemented. The evaluator stays authoritative; Bedrock cannot choose a verdict.
See [Trust Orchestrator acceptance](../../../docs/trust-orchestrator.md) for policy
semantics, delivery limits, security coverage and exact human acceptance order.
