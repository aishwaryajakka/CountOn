> Current implementation: [Bedrock integration](../../docs/bedrock-integration.md).
> Capture now compiles through MCP/Bedrock and then captures separately. Earlier
> regex-only demo notes below are historical; they do not describe production capture.

# CountOn Alexa+ MCP Demo

`/alexa` is an authenticated CountOn hackathon conversation, not Amazon's
internal or official simulator. It uses the existing Supabase AuthProvider and
the current user's first name. A sidebar link opens the standalone conversation;
it does not mount the dashboard's FastAPI-backed board provider.

Every tool operation uses `requestMcp(session.access_token, action)` →
`POST /api/mcp` → official MCP Streamable HTTP client → deployed CountOn MCP.
The transport is unchanged. The connection badge requires successful real
initialization, discovery, and availability of the three required tools.
Successful calls expose only safe protocol metadata in expandable traces.

## Constrained conversational routing

`lib/alexa-router.ts` selects intent only; it never compiles an expectation or
creates evidence. List/get use existing MCP tools and real owned records. Capture
uses trusted Next.js orchestration, the existing compiler and clarification, then
`capture_expectation` only after COMPILED. Calendar reasoning uses a trusted
backend clock, never an invented browser deadline.

“Why did my electricity expectation fail?” and “Why was my bill higher?” list
owned records and match actual claims/metrics. Multiple matches ask for a more
specific claim and retain those candidates for the reply. No match is reported
honestly. “Why did it fail?” / “Why didn't this match?” refer only to the most
recent explicitly viewed/captured expectation; without one, CountOn asks which
expectation. Search covers the first 50 records and discloses that limit.

`explain_expectation_mismatch` loads the latest deterministic evaluation. MATCH
says it matched, UNKNOWN says CountOn is still watching, and no evaluation says
it is waiting. None invokes the investigator. Only confirmed MISMATCH loads
bounded relevant evidence and runs the existing grounded investigator. Bad
citations, unavailable Bedrock or missing evidence return safe fallbacks.

Speech uses only the server's concise `message`. Structured provenance contains
`expectation_id`, `evaluation_id`, bounded real `evidence_ids`, `bedrock_used`, and
`fallback_used`; IDs/raw metadata are not spoken. Possible rate contribution is
not proof that a rate change outweighed usage: observations do not establish a
net effect, causality or matching billing periods. No external market facts,
evidence or evaluation state are invented.

Transcript/context reset on reload or user change. This is a CountOn web
simulator, not a completed Alexa/Echo integration.

## Voice and accessibility

Text input is always available; Enter sends and Shift+Enter adds a newline.
Speech-to-text is not implemented. Optional browser `speechSynthesis` is
feature-detected, off by default, and toggleable via “Read replies”. Speech
failure does not block text. Status announcements, an accessible transcript,
labelled controls, mobile layout and reduced-motion support follow CountOn styles.

## Setup and verification

Set this server-side variable in `frontend/.env.local` and Vercel Production:

```env
COUNTON_MCP_URL=https://counton-mcp.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com/mcp
```

Keep the existing three `NEXT_PUBLIC_*` API/Supabase variables. No static token,
cookie-based auth, browser-to-MCP CORS entry or backend change is needed.
Build and redeploy the frontend to publish `/alexa` and `/api/mcp`:

```sh
cd frontend
npm run lint
npm run typecheck
npm run test
npm run build
vercel --prod
```

Manual judge flow:

1. Sign in normally and open `/alexa`.
2. Wait for “Connected to CountOn MCP”.
3. Ask “What am I counting on?” and inspect `MCP → list_expectations`.
4. Ask “Tell me about my electricity bill” and inspect both list/get traces.
5. Ask the grocery phrase above; inspect `MCP → capture_expectation`.
6. Click “View in CountOn”, verify the row, then refresh to verify persistence.
7. Expand “How this works” and optionally enable read-aloud.

On 2026-10-08, lint/typecheck/build and 89 standard tests passed. The optional
read-only MCP integration test remains gated by its explicit endpoint/token
variables. Chromium also verified normal Supabase login, live connection, list,
detail, capture, returned-ID handoff to the deployed normal CountOn UI, refresh,
persisted payload, and 390px layout. No direct FastAPI requests occurred on
`/alexa`. The one test-created row was deleted by its exact captured ID afterward.
Desktop/mobile screenshots are in ignored `test-results/alexa/`.

To repeat the opt-in browser acceptance, explicitly set `COUNTON_ALEXA_BASE_URL`,
`COUNTON_E2E_API_BASE_URL`, `COUNTON_E2E_EMAIL`, and `COUNTON_E2E_PASSWORD` in the
test process environment, then run `node tests/alexa-live.mjs`. Use a dedicated
test account with an electricity expectation. For local simulator testing
against remote MCP, set `COUNTON_E2E_HANDOFF_URL` to the public Vercel frontend
so normal dashboard access uses its allowed production origin; the script signs
into that origin independently. The script creates one row via MCP and uses
FastAPI only for an independent persistence cross-check and deletion of that
exact test-created row, never as the simulator tool path. No tokens or passwords
are printed or saved to artifacts.

## Conversational expectation capture

The browser sends one message (and an opaque continuation handle) to the authenticated
Next.js `/api/mcp` `converse` action. The route calls the existing Python MCP
`compile_expectation` or `continue_expectation_compilation` over Streamable HTTP.
Those tools delegate to the existing compiler and `ClarificationEngine`; no browser
parser, second clarification format, or full transcript is supplied to Bedrock.
Only a COMPILED result causes one nested `capture_expectation` call. The resulting
expectation uses ordinary CountOn services and is visible through the dashboard API.

Example: “I'm counting on my bill being lower” → subject question → “My electricity
bill” → comparison question → “My last bill was $142.10” → timing question → “When my
next bill arrives” → saved confirmation. That last phrase is a grounded
**evidence-arrival condition in the claim**, not an invented calendar deadline or
an automatic scheduling feature. Calendar dates still use the existing temporal
reasoning. Conversational numeric captures also ask for missing timing.

Corrections, cancellation, unrelated answers, new topics, expiration and turn
limits use the existing engine. “Actually make that $150” changes the relevant
amount only. List/detail queries can be made without discarding active clarification.
Refreshing starts a new browser conversation; signing out/changing users clears it.
The transcript shows questions/replies and safe Bedrock/MCP labels, never prompts,
model drafts, capture tickets or bearer tokens.

### Deployment and replay safety

Apply the new Alembic migration before deploying the updated MCP server:

```sh
cd backend
source .venv/bin/activate
alembic upgrade head
```

Keep `BEDROCK_ENABLED=true` and the existing AWS model/region configuration on the
trusted backend. Production requires a dedicated `COUNTON_CLARIFICATION_SIGNING_KEY`
(at least 32 random bytes) on that backend, never a `NEXT_PUBLIC_*` variable.
`COUNTON_MCP_URL` remains a server-only Vercel variable. No AWS credentials move to
Vercel or the browser. The DB role needs access to `compilation_sessions`; that
ledger has RLS enabled with no browser policies (use the existing trusted DB role).

The ledger stores the existing canonical `ClarificationState`, owner and latest
handle digest. Each continuation consumes its previous handle. Completed,
cancelled, failed, replaced and expired conversations cannot reuse an old active
handle. Compiled capture verifies the exact trusted payload and atomically commits
its expectation ID with normal expectation creation. Replayed capture returns the
same owned expectation, including across workers/restarts; it never creates another
row. Initial requests have a stable compilation ID for request replay protection.
A deleted captured expectation is not silently recreated.

Clarification TTL and max-turn settings remain authoritative. The turn limit now
defaults to six to allow corrections alongside the three subject/baseline/timing
answers. Existing `CLARIFICATION_MAX_TURNS` overrides still apply; use six on the
backend for this demo. Expired ledger records are
inert; no automatic retention job is added in this pass. Any future cleanup must
retain records until after their signed state expires.
