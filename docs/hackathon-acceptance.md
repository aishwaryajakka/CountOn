# COUNTOn ALEXA+ HACKATHON ACCEPTANCE

Verified 2026-10-08 against **https://counton-frontend.vercel.app/alexa** and
the deployed Lightsail MCP/API services. The previously missing production
MCP variable and frontend routes were fixed by configuring Vercel and deploying
the existing frontend. No backend or MCP transport code was changed.

## Results

| Category | Result | Evidence |
| --- | --- | --- |
| Streamable HTTP | PASS | Existing Python SDK transport; official TypeScript client; public HTTPS MCP protected by bearer auth. |
| Authentication | PASS | Real Supabase sign-in, production missing/invalid bearer rejection, 35 auth tests. |
| Initialize | PASS | Actual SDK handshake through production Next.js route and direct SDK probe. |
| tools/list | PASS | Production discovery returned exactly the three required tools. |
| tools/call | PASS | Actual production tool calls, not REST substitutes. |
| list_expectations | PASS | Nested request; five existing owned records before temporary capture. |
| get_expectation | PASS | Electricity claim matched from real list and fetched using its returned UUID. |
| capture_expectation | PASS | Real production MCP capture with a uniquely tagged temporary claim. |
| /alexa UI | PASS | Production sign-in gate, connection badge, transcript, traces, 390px layout; explicit non-Amazon-demo disclosure. |
| Shared persistence | PASS | MCP-created row visible in normal FastAPI-backed detail UI after refresh; API confirmed target/comparison. |
| Agent Skill | PASS | Official skills-ref validator passed; existing artifact accurately describes current tools and limits. |
| Security | PASS | Source/local-ref history scan, ignored env files, public browser key, no admin credentials in Vercel frontend config, safe response/log checks. |
| Frontend build | PASS | Lint, typecheck, 89 standard tests, production build, and Vercel build all ran successfully; live MCP test passed separately. |
| Backend tests | PASS | All 38 relevant MCP tests passed with the existing isolated counton_test database; 35 auth tests also passed. |

The full browser script created one uniquely tagged acceptance expectation,
verified its exact returned ID and tag before cleanup, deleted only that row,
and confirmed GET returned 404 afterward. It made no direct FastAPI requests
while on `/alexa`. FastAPI was used only by the normal handoff UI and the test
harness's independent persistence/cleanup checks.

## Error coverage and limits

| Error | Verification |
| --- | --- |
| Expired Supabase session | Signed expiry validation in backend auth tests; simulator expiry UI tests. No wait for a real production session to expire. |
| Missing auth | Production POST /api/mcp: 401 AUTH_REQUIRED; signed-out browser redirected to login. |
| Invalid bearer token | Production POST /api/mcp: 401 AUTH_EXPIRED; public unauthenticated /mcp: 401. |
| MCP unreachable | Existing transport rejection and simulator unavailable tests; production service was not intentionally disabled. |
| Unknown tool | Production route: 404 TOOL_NOT_FOUND. |
| Invalid/flattened input | Production route: 400 TOOL_VALIDATION_ERROR; numeric validation covered by existing tests. |
| Nonexistent ID | Production MCP call: 422 TOOL_EXECUTION_ERROR. |
| Empty list | Existing simulator test with an empty returned list; no production records deleted to manufacture this case. |
| No detail match | Existing simulator test; no fabricated ID or get call. |

All production tool arguments are exactly `{ "request": {...} }`; flattened
arguments appear only as intentional negative test cases. The simulator uses
the user's current Supabase token solely through `/api/mcp` for tool access.
No service-role key or second auth implementation was added. Current compact MCP
responses expose stored status, not evidence/evaluation history or causal proof.

## A. Remaining blockers

No blockers for the deployed browser hackathon demo. Actual Alexa+ device/account
linking, Amazon certification and native MCP App UI integration are outside this
acceptance; this is explicitly a CountOn web simulator. Bedrock, voice input and
new evidence/explanation tools remain unimplemented and are not claimed.
Automatic GitHub deployments still need the Vercel GitHub login connection;
CLI production deployment is working. No user or secret configuration action
is required for the tested canonical production URL.

## B. Exact Vercel Production variables

All four are configured and privately verified. Retain the existing team's
Supabase public values; do not substitute a secret/service-role key.

```env
NEXT_PUBLIC_API_BASE_URL=https://counton-api.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com
NEXT_PUBLIC_SUPABASE_URL=<existing Supabase project URL>
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<existing public publishable/anon key>
COUNTON_MCP_URL=https://counton-mcp.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com/mcp
```

`COUNTON_MCP_URL` is server-side. Never add a shared test access token to Vercel.
Production browser bundles contain neither the server MCP URL nor localhost API
dependencies. Changes to NEXT_PUBLIC values require a rebuild.

## C. Exact manual production test

1. In a signed-out browser, open the production `/alexa`; verify login redirect.
2. Sign in with an existing CountOn account through Supabase. Return to `/alexa`.
3. Wait for “Connected to CountOn MCP”; do not accept a merely loading badge.
4. Ask “What am I counting on?” Verify real claims/statuses and the list trace.
5. Expand trace details: Streamable HTTP, initialize success, tools discovered yes.
6. Ask “Tell me about my electricity bill”. Verify list/get traces and a real row.
   Use an account with an electricity expectation; an honest no-match otherwise is correct.
7. Ask “I'm counting on my grocery bill staying under $120 this week”.
8. Verify capture trace and “Saved to CountOn”, then click “View in CountOn”.
9. Confirm the new claim in the normal CountOn detail page; refresh and confirm it persists.
10. Verify mobile at 390px; optionally toggle “Read replies”. Text remains available.
11. In DevTools, `/alexa` tool requests target `/api/mcp`, not FastAPI CRUD.
    Inspect only header presence; never copy or share its bearer value.
12. For automated tests, run the tagged script below, which cleans up its own row.
    A deliberately saved user's demo expectation is a real record, not a mock.

Unauthenticated safe endpoint probe (no credentials):

```sh
curl -i -X POST https://counton-frontend.vercel.app/api/mcp \
  -H 'Content-Type: application/json' -d '{"action":"list_tools"}'
```

Expected: `401`, `AUTH_REQUIRED`. Do not paste a real token into shell history.

## D. Exact 60-second judge script

Prepare a signed-in tab with the seeded electricity expectation before the clock starts.

| Time | Action and spoken line |
| --- | --- |
| 0–8s | Open /alexa. “CountOn keeps everyday expectations separate from evidence. This is our Alexa+ MCP web demo.” |
| 8–20s | Ask the list starter. “These are my real records. This trace shows live initialization and MCP discovery.” Expand its trace. |
| 20–35s | Ask the electricity starter. “It lists, matches a real ID, then gets its recorded status. It does not invent why a bill changed.” |
| 35–50s | Ask the grocery starter. “This saves a strict $120 expectation through capture_expectation.” Point to the capture trace. |
| 50–60s | Click View in CountOn and refresh. “The normal FastAPI UI reads the same persisted Supabase record. Quiet success, attention only to verified exceptions.” |

## E. Exact two-minute judge script

| Time | Action and spoken line |
| --- | --- |
| 0–15s | Show /alexa and live badge. “Expectation → evidence → evaluation → exception. Silence is success, but missing evidence is never proof.” |
| 15–35s | List expectations and expand trace. “Browser → authenticated Next.js route → official MCP Streamable HTTP. These are my actual owned rows.” |
| 35–55s | Electricity detail. “List identifies the claim; get uses its returned UUID. Current MCP gives recorded status, not a fabricated explanation.” |
| 55–75s | Type “I'm counting on my bill being lower.” “It asks which bill and what reference amount. We do not invent a baseline.” |
| 75–95s | Use grocery capture starter. “Explicit USD, strict less-than target, a real timezone-aware deadline, no invented evidence.” Show Saved and trace. |
| 95–110s | View in CountOn and refresh. “MCP and FastAPI share services and Supabase persistence. The row survives navigation and refresh.” |
| 110–120s | Show SKILL.md in the repository. “Compatible agent hosts get the same tool mappings and safety boundaries. This is our demo, not Amazon's official simulator.” |

## F. Architecture

```text
Supabase Auth -> browser session.access_token
                         |
Browser /alexa --Bearer--> Next.js POST /api/mcp (Node)
                              |
                         official MCP client
                         initialize -> tools/list -> tools/call
                              |
                    Streamable HTTP + same Bearer
                              |
                    Lightsail CountOn MCP /mcp
                              |
                       JWT + owned services --------+
                                                   |
Browser dashboard --Bearer--> Lightsail FastAPI ----+--> same Supabase PostgreSQL

Agent Skill -> host instructions for the same three tools (no extra transport)
```

## Repeating automated acceptance

Frontend: `npm run lint`, `npm run typecheck`, `npm run test`, `npm run build`.
Backend: run `pytest tests/test_mcp.py tests/test_mcp_network.py tests/test_mcp_services.py`
with a separately configured loopback `TEST_DATABASE_URL` ending in `_test`;
also run `pytest tests/test_auth.py`. Never point that fixture at application data.
The read-only `tests/mcp-live.test.ts` requires explicit `COUNTON_MCP_URL` and
`COUNTON_MCP_TEST_ACCESS_TOKEN`, supplied through the process environment.

`node tests/alexa-live.mjs` requires `COUNTON_ALEXA_BASE_URL`,
`COUNTON_E2E_API_BASE_URL`, `COUNTON_E2E_EMAIL`, `COUNTON_E2E_PASSWORD`.
Use the production frontend/API URLs and a dedicated test account, with secrets
provided securely. It tags only its test capture, checks ID/tag ownership before
cleanup, and confirms the row is absent. Artifacts are ignored screenshots in
`frontend/test-results/alexa/`. The product parser/transport is not modified.

## Security audit scope

Scanned current tracked/untracked source text and committed history of all local
Git refs for JWTs, private keys, database URLs and known ignored secrets. Candidate
files were README.md, backend/db/README.md, backend/tests/test_demo_identity.py,
and frontend/tests/mcp.test.ts. Generic credential-assignment review additionally
checked backend/tests/test_config.py, frontend/tests/alexa.test.tsx,
frontend/tests/auth.test.tsx, and frontend/tests/screens.test.tsx; their hits were
synthetic test values or a Markdown fence after an empty credential field.
The reviewed files contain documented local-development values,
placeholder URLs or deliberate synthetic fixtures; no real production credential
was identified and no credential remediation was needed. Ignored env/linkage
files were verified. Frontend production configuration contains no backend
database/admin credential. Safe responses and logging are covered by source
review, tests, and a bounded recent runtime-log inspection; this is not a claim
to have audited remote Git refs or all historical cloud logs.
The Vercel sample contained 50 entries with no private credential/header matches.
Lightsail's container-log API returned no MCP events, so MCP log safety is
supported by source review and the passing capture/redaction tests rather than
an observed cloud-log sample.
