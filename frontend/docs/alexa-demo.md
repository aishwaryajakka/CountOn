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

## Deterministic routing

`lib/alexa-router.ts` is a separate, replaceable routing/compilation seam:

- List phrases call `list_expectations` with `{request:{limit:50,offset:0}}`.
- Detail phrases list first, match actual claim/metric values, and get the
  matched real UUID. No match produces an honest response. Multiple matches
  require clarification; the demo never chooses an arbitrary ID.
- Grocery capture accepts explicit USD amounts for this week in the supported
  phrase family. Unsupported currencies, extra conditions and unrecognized
  capture requests need clarification. Inputs are checked against the existing
  capture contract before submission.

For “I'm counting on my grocery bill staying under $120 this week”, the generated
tool arguments are exactly:

```json
{
  "request": {
    "claim": "I'm counting on my grocery bill staying under $120 this week",
    "type": "numeric_comparison",
    "metric": "total_cost",
    "comparison": "less_than",
    "target_value": 120,
    "deadline": "<Sunday 23:59:59.999 in the device timezone, serialized as UTC ISO with Z>",
    "evidence_sources": [],
    "materiality_threshold": 0
  }
}
```

The deadline is generated from the current browser clock; it is never a fixed
date. Zero tolerance honors “under” as a strict cap. No baseline, provider,
evidence, or evaluation is invented. The UI explicitly identifies USD and the
device timezone. Capture success links the actual returned ID to the normal
expectation detail page.

The inspected compiler service/API are placeholders; `app/mcp/compiler.py`
declares a future interface only. Bedrock was not reused and no LLM dependency
was added. The demo displays only MCP's current compact fields: claim, type,
status, metric, and creation date. It does not infer evaluation or evidence
details. Lists/searches are limited to the first 50 expectations and disclose
that limit when reached. The transcript is in memory and resets on page reload.

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
