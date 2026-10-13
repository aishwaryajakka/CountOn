# Minimal Trust Orchestrator acceptance

This is bounded orchestration, not an autonomous monitoring agent. The current
implementation is canonical; the six MCP names and nested `{"request": {...}}`
contracts remain unchanged. No new database tables, evaluator semantics, provider
implementations, worker or scheduler were introduced.

## Architecture and actions

```text
Web /alexa → authenticated Next.js /api/agent → FastAPI /api/v1/agent/converse
Signed ASK /api/v1/alexa → existing linked-token JWT verification
                                  ↓
                       SAME AgentOrchestrator / bounded session store
                                  ↓
                    real MCP SDK / Streamable HTTP / bearer
                                  ↓
               six MCP capabilities → existing services / Bedrock → Supabase
Dashboard → authenticated FastAPI → SAME persistence
```

Actions: LIST_EXPECTATIONS, GET_EXPECTATION, COMPILE_EXPECTATION,
CONTINUE_CLARIFICATION, CAPTURE_EXPECTATION, EXPLAIN_MISMATCH, CANCEL, UNKNOWN.
Only the immutable registry grants a capability. A selected UUID is reauthorized
through MCP; it is not a grant. Compile/continue reuse the canonical clarification
engine; valid signed COMPILED state is required before capture. The existing
persistent compilation ledger prevents replayed capture. Session handles rotate;
they are bounded, user-scoped, server-only context references, not credentials.

## Evidence policy

`backend/app/agent/privacy.py` derives an exact source allowlist from declared
`expectation.evidence_sources` (including tariff/utility_tariff aliasing). Custom
explicit source identifiers must have a bounded identifier shape; their public
label is “Declared source.” When declarations are empty, narrow type/metric/subject
defaults allow utility measurements for an electricity/utility cost expectation,
billing receipts for grocery cost, delivery/Ring for a temporal/event package
expectation, or calendar/Outlook/Bee for a temporal/event appointment. Unrecognized
subjects grant no default sources. An explicit nonempty declaration overrides
these defaults. Unrelated and malformed sources are denied.

Permissions are not availability. Integration-connection metadata is not an
access grant or proof of ingestion, so this policy does not infer data from a
“connected” label. Ring, Outlook and Bee are vocabulary only; their actual ingestion
remains unfinished. Only real, owned evidence rows can be considered. A declaration
or source label never manufactures a row.

The owned investigation service filters sources before delegation, and the pure
normalizer independently enforces the same policy before preparing Bedrock input.
Existing metric relevance, evaluation-time snapshot, latest observation ordering,
confidence, value and citation validation remain in place. The deterministic
evaluator is unchanged: a recorded mismatch can still have insufficient **permitted**
evidence to explain its cause. Missing explanation evidence does not change its verdict.

## Response and provenance

Internal `TrustResponse` contains answer, AgentStatus, recorded evaluator_result,
expectation UUID, source labels, validated evidence UUIDs, bedrock_used,
fallback_used, grounded, safe_to_say and run UUID. Only backend evaluation records
supply MATCH/UNKNOWN/MISMATCH; compiler/model proposals cannot supply a verdict.

Speech safety is a deterministic outcome, not a constant: sensitive credentials,
URLs containing database credentials, hidden-prompt/COT markers, control characters,
incomplete capture claims and invalid/missing mismatch provenance are rejected.
This is a bounded guard rather than a universal secret detector. The normal
compiler/grounding/schema checks and trusted backend rendering remain essential.
Rejected speech becomes a neutral fallback; a confirmed save retains its record
identity so no automatic retry can duplicate it.

`EvidenceProvenance` validates each used ID against an allowed source decision.
The MCP boundary additionally checks IDs/E-labels against normalized real evidence.
Model output is still the restricted `InvestigatorDraft`: it cannot set this receipt,
run identity, safety flag or evaluation. Unsupported factors/citations are rejected.
Bedrock failure yields the existing deterministic fallback; conflicts lower
confidence and never establish a causal conclusion. `bedrock_used` means accepted
AI output was used, not merely that an invocation was attempted. The separate
internal `bedrock_attempted` records an investigator client attempt. Model
grounding is true only for validated accepted output, false for rejected output,
and null when no model response was validated; a safe deterministic fallback may
still be grounded in recorded facts.

The `/alexa` expandable **Why CountOn said this** shows only a bounded expectation
label, recorded result, canonical source display labels, signal count, accepted
Bedrock usage, fallback flag and approved trace labels. It never renders evidence
UUIDs/payloads, evaluation UUIDs, signed state, hidden prompts, raw provider output
or tokens. The run UUID is carried for support correlation, not spoken/rendered.
The Next.js schema is strict; optional provenance supports old API responses while
backend-first deployment is completed. Absence of provenance does not invent it.

## Auditing and operational limits

Authenticated web and traditional Alexa orchestration runs write the existing
`audit_events` table through `services/agent_audit.py`. Resource ID is run UUID;
user and expectation references are internal, ownership-checked fields. Metadata
is an explicit whitelist: action, actually attempted capabilities (including failed
calls), evaluation UUID/result, validated used evidence UUIDs/source labels,
allowed/denied source decisions, Bedrock attempt/accepted output, fallback,
grounding/speech checks, duration and final status. No answer, utterance, transcript,
prompt, clarification token, provider payload, database URL, JWT or credentials is
serialized. A timeout/interrupted run gets a failure receipt rather than fictitious
success. Shared request logging includes safe run ID and audit delivery status.

Audit failure logs `audit_status=failed` without exception text and preserves an
already confirmed action; it never retries a capture. There is no durable outbox:
a database outage or abrupt process termination can lose an audit event. This is
an operational limit, not a claim of guaranteed audit delivery. Lower-level unit
hosts can omit the audit sink; production API hosts install it. No migrations are
required beyond the existing audit_events migration.

The bounded conversation store and ASK reply cache remain single-process. Deploy
one API worker, or provide sticky/shared atomic session storage before scaling.
Traditional Alexa's seven-second budget requires actual deployed latency testing;
a slow inference can return an honest uncertain-result response. Checking the
dashboard before another save is intentional.

## Automated security and end-to-end coverage

| Requirement | Coverage |
| --- | --- |
| 1–3 Arbitrary tool/action/user injection | test_agent.py, test_agent_api.py, agent-route.test.ts; closed strict request/plan schemas |
| 4 Cross-user access | agent/session/API/MCP/Alexa tests; test_trust.py audit owner check |
| 5 No direct frontend Supabase writes | Alexa and agent route/client source inspection; browser sends utterance + opaque handle only |
| 6–7 MATCH/UNKNOWN never invoke investigator | test_agent_api.py, test_mcp_intelligence.py, test_mismatch_investigator.py |
| 8–10 Grounded/known/allowed citations only | test_mismatch_investigator.py and test_trust.py denied contributor / unknown citation / source tests |
| 11–12 No audit/log secrets or COT/transcript | test_trust.py whitelist tests; existing investigator/compiler/adapter logging tests |
| 13 Bedrock failure fallback | test_agent.py, test_agent_api.py, test_mismatch_investigator.py |
| 14 MCP failure no fabricated success | agent and frontend transport failure tests |
| 15–16 Compile before capture, one capture/replay | canonical compilation lifecycle and agent/session/API/ASK tests |
| 17 Expired/tampered state | signed state, session, agent and MCP lifecycle tests |
| 18 ASK attributes no tokens | test_alexa.py strict attributes, original signature/JWT and retry tests |

A–J are covered across `test_agent_api.py`, `test_agent_sessions.py`,
`test_agent.py`, `test_mcp_intelligence.py` and `test_trust.py`: owned list;
one-shot grocery capture; multi-turn electricity clarification; correction only
of the relevant fact; cancellation without persistence; contextual detail→Why
with renewed ownership; grounded MISMATCH; MATCH and UNKNOWN without investigation;
admin-tool injection with no arbitrary capability invocation. PostgreSQL and real
local MCP Streamable HTTP are exercised; AWS inference is controlled in these tests.
Local HTTP/RSA/JWT tests are not Alexa Console/device or live Bedrock acceptance.

Validation on 2026-10-08: full isolated-PostgreSQL pytest, touched-file Ruff, scoped
strict mypy, frontend test/lint/typecheck/build and git diff checks. See the task's
final report for actual counts/results; the opt-in frontend production probe is
not a passing live test.

## Person 1 and Person 2 status

Legend: ✅ manually/live verified; 🟡 implemented/tested but not manually verified;
❌ missing. No item is upgraded solely because automated tests passed.

| Person 1 item | Status |
| --- | --- |
| MCP Streamable HTTP | 🟡 |
| Six MCP tools | 🟡 |
| Authenticated tools | 🟡 |
| /alexa web simulator | 🟡 |
| Minimal Trust Orchestrator | 🟡 |
| Traditional Alexa adapter | 🟡 |
| Request/response path | 🟡 |
| Shared backend persistence | 🟡 |
| No business-logic duplication inside MCP/Alexa | 🟡 |

| Person 2 item | Status |
| --- | --- |
| Live-capable Bedrock client/config | 🟡 |
| Expectation compiler | 🟡 |
| Pydantic structured output | 🟡 |
| Temporal interpretation | 🟡 |
| Stateful clarification | 🟡 |
| Correction | 🟡 |
| Cancellation | 🟡 |
| Grounded mismatch investigator | 🟡 |
| Evidence grounding | 🟡 |
| Why explanation | 🟡 |
| Deterministic evaluator authority | 🟡 |

Real linked-account OAuth setup/consent, ASK simulator acceptance and Echo acceptance
are ❌ as completed integrations. The adapter is implemented; those prerequisites
and verification are separate. No public rollout or manual live inference is claimed.

## Exact human acceptance order

Use a dedicated test account; keep credentials private and clear only exact test
rows through owned API tooling. API and MCP must use the same database, Supabase
JWT settings and strong clarification signing key. Backend settings live in
`backend/.env.local`; public frontend settings and server-only `COUNTON_MCP_URL`
live in `frontend/.env.local`. For local API set `MCP_PUBLIC_URL=http://localhost:8003/mcp`.
For local web startup use `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` and
server-only `COUNTON_MCP_URL=http://localhost:8003/mcp`, with existing Supabase public
URL/key and `ENVIRONMENT=development` on local Python services. Retain existing JWT
verification; there is no authentication bypass. Production must use actual HTTPS
endpoints.

| Step | Action | Expected | Failure means |
| --- | --- | --- | --- |
| 1 Backend | Root: `docker compose up -d`; backend: `source .venv/bin/activate`, `python -m pip install -r requirements.txt`, `alembic upgrade head`, `uvicorn app.main:app --reload`. Open `/health` and `/docs`. | Health ok; migrations at head. | DB/config/dependencies/auth rollout requires attention; do not move on. |
| 2 MCP | Second backend terminal: activate venv; `python -m app.mcp`. | Streamable HTTP at `http://localhost:8003/mcp`; protected requests require bearer. | MCP process/config/port/signing setup is wrong. |
| 3 Discovery | Privately supply current test-account `COUNTON_TEST_ACCESS_TOKEN`; run `python db/scripts/intelligence_smoke.py --mcp-url http://localhost:8003/mcp`. | Real initialize, all six tools/list, authenticated list PASS. | Token, transport, missing deployed capabilities or endpoint mismatch. |
| 4 Real compile | Enable backend/MCP `BEDROCK_ENABLED=true`, `AWS_REGION=us-east-2`, configured model ID; use runtime AWS provider chain. Run same script with `--compile`. | Valid typed compiled expectation; no expectation capture; actual paid inference. | AWS IAM/model/region/network/output/grounding issue. No live Bedrock PASS yet. |
| 5 Clarification | In an authenticated MCP inspector call compile_expectation with `{"request":{"text":"I'm counting on my bill being lower.","conversational":true,"timezone":"America/Chicago"}}`. Continue with returned state and “My electricity bill”, “My last bill was $142.10”, “When my next bill arrives”, one nested request each. | One question per missing fact; established facts preserved; final COMPILED, not prematurely captured. | Compiler, temporal, continuation/signing or ledger defect. Never disclose the returned signed state. |
| 6 Web | Third terminal frontend: `npm install`, `npm run dev`; sign in and open `http://localhost:3000/alexa`. | Auth gate, six-tool discovery and connected badge. | Next/API/MCP URL, Supabase session, CORS or deployed-version mismatch. |
| 7 List | Say “What am I counting on?” | Actual owned rows or honest empty response; approved trace. | Routing/auth/ownership/API-to-MCP path issue. |
| 8 Capture | Say “I'm counting on my grocery bill staying under $120 this week.” Complete any material clarification once. Repeat the bill conversation and test “Actually make that $150”, then a separate draft with “Never mind”. | Exactly one saved complete record; correction preserves other facts; cancellation saves nothing. | Compile/capture/session lifecycle failure; do not repeatedly retry uncertain saves. |
| 9 Dashboard | Open linked saved expectation and regular `/expectations`; refresh. | Same UUID/claim persists through normal FastAPI source. | API/MCP databases differ, auth differs, or persistence failed. |
| 10 Mismatch | Use a clearly marked test electricity expectation with baseline 142.10 and explicit sources utility_bill, utility_usage, utility_tariff. Through authenticated Swagger add test measurements: total_cost 162 USD, usage change -18 percent, rate change 22 percent, using current UTC observation time. Evaluate. | Deterministic MISMATCH, contradicted status. These are labelled test inputs, not claims of provider ingestion. | Test evidence/metric/timing/comparison or evaluator issue. Bedrock must not produce the verdict. |
| 11 Why | In /alexa select the electricity expectation; ask “Why did it fail?” Then choose separate 130 USD MATCH and missing-total-cost UNKNOWN examples and ask Why. | Grounded, cautious explanation using supplied evidence for MISMATCH; MATCH/UNKNOWN do not invoke investigator. | Routing, ownership, source policy, grounding, Bedrock config or evaluation snapshot issue. |
| 12 Provenance | Expand “Why CountOn said this”; inspect owned orchestration audit through trusted DB tooling. | Recorded result, Utility source, actual signal count, accepted AI/fallback and safe trace. Audit has run/capability/source decisions without transcript or secrets. | API/frontend version mismatch, receipt validation or audit delivery problem. |
| 13 Console | Follow [Traditional Alexa setup](traditional-alexa.md): create en-US custom skill, import `backend/app/alexa/interaction-model.en-US.json`, set matching ALEXA_SKILL_ID and public HTTPS `/api/v1/alexa`; configure an actually working OAuth authorization-code account link that supplies CountOn-verifiable Supabase JWTs. | Console model builds; linked test account; signed endpoint works. | Missing OAuth provider/consent/client setup, skill ID, HTTPS/cert or account-linking architecture prerequisite. No token substitution/signature bypass. |
| 14 ASK simulator | Enable development testing; launch CountOn, list, detail, capture/clarify/correct/cancel and Why with linked account. Measure real latency. | Same orchestrator semantics within ASK deadline; session attributes contain only opaque reference. | Model/slot elicitation/OAuth/verification/latency mismatch. Fix before device testing. |
| 15 Echo | Use a real Echo on the same developer test account; repeat list→capture→dashboard and detail→Why. | Actual voice transport, linked identity, shared records and grounded response. | Device/locale/account/voice timing issue; real Alexa integration remains unverified. |

## Deployment and console blockers

Roll out the current API, MCP and frontend together (backend first), using existing
migrations. Check HTTPS routes, exact frontend CORS origin, six-tool discovery,
matching JWT/signing configuration, trusted-runtime AWS credentials/model access,
audit delivery and one-worker session behavior. Production latency, Bedrock model
quality, account linking, ASK simulator and Echo still require the ordered manual
acceptance above. There is no completed OAuth authorization/consent provider in
this repository; merely importing the interaction model is insufficient.
