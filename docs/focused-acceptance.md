# Focused CountOn acceptance — 2026-10-23

This pass used isolated local authenticated fixtures, PostgreSQL, signed ASK
requests, real loopback MCP HTTP and existing CountOn services. JWT keys and ASK
certificate roots were test fixtures. Bedrock transport was mocked or explicitly
disabled for the grounded fallback. It was not a live Amazon, Supabase OAuth or
production browser acceptance run.

## Acceptance matrix

| Area | Status | Evidence |
| --- | --- | --- |
| Shared Alexa/web orchestration | ✅ implemented + locally verified | Signed ASK and `/api/v1/agent/converse` use the same orchestrator, MCP capture and owned API/schema. |
| Linked CountOn identity | ✅ implemented + locally verified | Linked-client JWT `sub` determines ownership; a different CountOn UUID placed in Alexa `userId` cannot change it. Foreign-client and foreign-user continuations fail. |
| Exact Alexa electricity capture | ✅ implemented + locally verified | “My next electricity bill should be below $150.” requires confirmation, saves once, and appears in the normal expectation API with `creation_source=alexa_skill`. |
| List / get / grocery capture | ✅ implemented + locally verified | Actual owned claims are returned; the grocery utterance compiles and saves after approval through the same path. |
| Clarification / cancellation | ✅ implemented + locally verified | Ambiguous bill asks a question; “Never mind.” closes the draft without a new row or another model call. Existing tests cover correction, topic replacement, expiry and replay. |
| Contextual Why | ✅ implemented + locally verified | Selected electricity expectation uses its persisted MISMATCH and evidence. MATCH/UNKNOWN bypass investigation. Grounded fallback does not invent causes. |
| Electricity Demo | ✅ implemented + locally verified | `< $150`, observed $180 → MISMATCH, one in-app notification under default preferences, real audit and grounded explanation. |
| Package Demo | ✅ implemented + locally verified | Positive DEMO delivery plus SIMULATED Ring observation → MATCH, no mismatch notification. No-detection remains insufficient evidence. |
| Bee Commitment Demo | ✅ implemented + locally verified | SIMULATED Bee promise is context only → UNKNOWN / monitoring, no notification or claim of arrival. |
| Complete persisted chain | ✅ implemented + locally verified | Expectation, evidence, evaluation, notification and audit foreign identifiers are checked against each other, including explanation evidence/evaluation references. |
| Frontend contracts/display | ✅ implemented + locally verified | API client, demo cards, standard detail, history, audit activity, provenance and notifications consume backend-shaped fixtures. Actual result overrides instructional expected outcomes. |
| Frontend lint/typecheck/build | ✅ implemented + locally verified | Full lint, typecheck and production build passed. |
| Live OAuth / Alexa Console / Echo | 🟡 requires cloud/account/device verification | Real account-link issuance, refresh/revocation, recognition, device interaction and production latency were not exercised. |
| Real Bedrock invocation | 🟡 requires cloud/account verification | Local parsing/grounding and fallback tested; no genuine AWS invocation in this pass. |
| Deployed authenticated browser flow | 🟡 requires cloud/account verification | Component/API contract tests and production compilation passed; no claim of a signed-in production browser session. |

No missing implementation or runtime code blocker was found within these local
scenarios. Ring and Bee are intentionally simulated for this demo scope.

## Exact persisted lifecycle assertion

`backend/tests/test_frontend_demo_scenarios.py::test_exact_alexa_electricity_capture_full_linked_lifecycle`
creates the expectation through the signed Alexa adapter, confirms and replays
confirmation, reads the ordinary owned API, lists/gets through Alexa, adds the
explicit DEMO $180 bill, evaluates, asks contextual Why, then checks:

- `expectation.user_id` is the CountOn principal.
- Evidence and evaluation belong to that expectation.
- Notification references that expectation and evaluation.
- `EXPECTATION_CONFIRMED` has `ALEXA` / `SIGNED_ASK` provenance.
- `EVIDENCE_INGESTED`, `EVALUATION_COMPLETED`, `NOTIFICATION_CREATED` and
  `EXPLANATION_GENERATED` link the same expectation/evidence IDs.
- Evaluation, notification and explanation audit events retain the evaluation ID;
  notification audit metadata retains the actual notification ID.
- Grocery capture and ambiguous bill/cancel continue through the same adapter;
  cancellation leaves both previously saved rows intact.

The normal detail regression in `frontend/tests/screens.test.tsx` verifies the
Alexa creation label, saved target 150, observed 180, actual attention status,
notification, simulated evidence and expectation-scoped reads. Backend persistence
and frontend rendering are separate automated layers, not a claim of a full
browser-to-cloud run. PostgreSQL tests roll back their isolated fixture data.

## Commands and results

Before backend runs, the test process explicitly selected `ENVIRONMENT=test`,
`DATABASE_TARGET=local`, a valid loopback `LOCAL_DATABASE_URL` and a distinct
`TEST_DATABASE_URL` ending in `_test`; `CONVERSATION_STORE_BACKEND=memory` with a
valid test-only encryption configuration; empty `MCP_PUBLIC_URL` and
`MCP_ALLOWED_ORIGINS=[]`; `BEDROCK_ENABLED=false` and
`AWS_EC2_METADATA_DISABLED=true`. No application/cloud database was migrated.
Credential values are deliberately omitted here.

From `backend`:

```sh
.venv/bin/python -m pytest -q tests/test_alexa_identity_lifecycle.py tests/test_alexa.py tests/test_agent.py tests/test_agent_api.py tests/test_agent_sessions.py tests/test_mcp.py tests/test_mcp_intelligence.py tests/test_mcp_services.py tests/test_mcp_network.py tests/test_compilation_lifecycle.py tests/test_numeric_evaluator.py tests/test_other_evaluators.py tests/test_evaluations.py tests/test_audit_history.py tests/test_lifecycle_audit.py tests/test_frontend_demo_scenarios.py tests/test_simulator_ingestion.py tests/test_simulator_authorization.py tests/test_adapters_and_simulators.py --tb=short
.venv/bin/ruff check tests/test_frontend_demo_scenarios.py
```

Result: **457 passed**, Ruff passed. There were 176 upstream ASK datetime and
certificate deprecation warnings. Verification was not disabled or weakened.

From `frontend`:

```sh
npm test -- tests/alexa.test.tsx tests/agent-route.test.ts tests/oauth-consent.test.tsx tests/mcp.test.ts tests/demo-scenarios.test.tsx tests/simulators.test.ts tests/screens.test.tsx tests/merge-regressions.test.tsx tests/expectation-explanation.test.tsx tests/api.test.ts tests/presentation.test.ts tests/providers.test.tsx tests/resource.test.tsx
npm run lint
npm run typecheck
NEXT_PUBLIC_API_BASE_URL=https://counton-api.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com npm run build
```

Result: **192 passed across 13 suites**, full lint/typecheck/build passed. The build
generated all 20 static pages and the dynamic handlers, including expectation
detail, `/api/agent` and `/api/mcp`. It did not exercise live dependencies.

From the repository root: `git diff --check` passed.

## Changes in this pass

- Added the exact signed-Alexa electricity lifecycle acceptance test to the existing
  backend demo test module.
- Added the corresponding normal frontend detail contract/rendering regression.
- Added this report. No runtime architecture, MCP contracts or evaluator behavior
  changed. Prior uncommitted work was preserved; nothing was committed or pushed.

## Remaining live/manual work

1. Configure the existing Supabase OAuth client, exact ASK callbacks and deployed
   allowlists, then perform real issuance, refresh/revocation and cross-account
   linking acceptance. Use the [exact Alexa Console checklist](traditional-alexa.md).
2. Supply valid private signing/encryption keys and PostgreSQL conversation storage
   in deployment. The existing ignored local backend environment had invalid
   conversation settings; these acceptance runs used valid isolated overrides.
   Correct that local configuration before using unqualified startup/test commands.
3. Deploy the reviewed code/configuration through the normal release process;
   perform genuine Bedrock compiler/investigator calls and verify ASK's response
   budget under deployed latency.
4. Complete ASK Console and real Echo recognition/account-linking tests, then verify
   the captured expectation, notification, evidence and audit records after signing
   into the deployed frontend as the same CountOn user.

Live Ring/Bee hardware is not claimed and is not required by these simulated demo
scenarios. Notification creation continues to honor saved user preferences.
