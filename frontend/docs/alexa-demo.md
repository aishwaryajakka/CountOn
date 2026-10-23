# CountOn Alexa+ web simulator

This is CountOn's hackathon web simulator, not an official Amazon simulator or a
completed Echo/traditional Alexa integration. Existing styling, optional browser
speech synthesis, transcript accessibility and saved-expectation links remain.

## Architecture

```text
Browser /alexa
→ Next.js /api/agent (utterance + opaque handle, bearer forwarded)
→ FastAPI /api/v1/agent/converse (existing Supabase JWT verification)
→ controlled Python orchestrator + bounded owned conversation state
→ real MCP Streamable HTTP, exactly {"request": {...}}
→ existing MCP tools / compiler / clarification / investigator / services
→ Supabase

Dashboard → FastAPI → same Supabase
```

The browser does not choose tools, compile claims, match records, decide outcomes,
or mutate Supabase business tables. `/api/mcp` performs real initialization and
six-tool discovery for connection status; browser tool calls and the former
`converse` action are rejected. All CountOn actions use the orchestrator route.

## Conversation

- “What am I counting on?” lists owned current records.
- “Tell me about my electricity bill” resolves owned records through bounded MCP
  list/get. Multiple matches ask for selection; “the second one” is supported.
- A complete claim compiles then captures once. Incomplete claims ask one question
  and retain the existing signed clarification state only on the backend.
- Answers, correction (“Actually make that $150”), cancellation and explicit new
  topics delegate to the canonical clarification engine, preserving grounded facts.
- “Why did it fail?” re-authorizes the selected expectation through MCP get before
  explanation. MATCH/UNKNOWN/no evaluation bypass the investigator; only a real
  deterministic MISMATCH permits grounded Bedrock explanation. Failures use the
  existing deterministic fallback, without invented evidence or causes.

The browser holds only an opaque, rotated handle in memory. It contains no facts,
tokens or signed compiler state. Refresh/user change clears it. The backend store
is fixed-TTL (15 minutes by default), bounded and single-process. Expired/tampered/
cross-user/replayed handles fail safely and ask the user to restate. Sessions are
not generic chat memory. No automatic save retry occurs after a lost response.

Speech displays only approved server answers. Compact recorded expectation cards
and the saved record link remain; provenance/raw JSON is not spoken. Expandable
traces contain closed labels such as `Agent → CONTINUE_CLARIFICATION`,
`MCP → capture_expectation`, and `Bedrock → grounded explanation`. No prompts,
chain of thought, tokens, handles, credentials or raw model output appear there.

## Configuration and startup

Keep the existing frontend public API/Supabase settings. Next.js server discovery:

```env
COUNTON_MCP_URL=https://counton-mcp.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com/mcp
```

On FastAPI, set `MCP_PUBLIC_URL` to that same endpoint. On **both Python services**,
set the same secure `COUNTON_CLARIFICATION_SIGNING_KEY`; never put it in frontend
variables. Development may use memory state; production requires encrypted
PostgreSQL state, current Alembic migrations, and the shared conversation key.
API/frontend redeploys are required; all six MCP tool contracts are preserved.
See [production acceptance](../../docs/production-readiness.md).

For local development, start PostgreSQL and the API as documented in the root
README. In another backend terminal, use the existing MCP startup command:

```sh
python -m app.mcp
```

Configure backend `MCP_PUBLIC_URL=http://localhost:8003/mcp` and frontend
`COUNTON_MCP_URL=http://localhost:8003/mcp`, with the same signing key on both
Python processes. Then run `npm run dev` in `frontend` and sign in normally.
Missing language/profile context may require currency clarification or use UTC;
no missing baseline/target/deadline is invented.

## Acceptance/demo

1. Sign in and open `/alexa`; wait for MCP discovery to connect.
2. Ask what you are counting on; inspect the expandable Agent/MCP labels.
3. Ask about an owned electricity expectation, then “Why did it fail?”
4. Start “I'm counting on my bill being lower.” Answer subject, comparison,
   baseline and timing; try correction before completion.
5. Confirm “Saved to CountOn,” open its existing link, and refresh the dashboard.
6. Try “Never mind” during another draft; verify no expectation is created.
7. Confirm MATCH/UNKNOWN replies use recorded outcomes without an investigator.

```sh
npm run lint
npm run typecheck
npm run test
npm run build
```

Backend agent/API/session tests exercise real loopback MCP HTTP and shared
persistence with signed fixture JWTs and mocked inference. Frontend tests exercise
route validation, safe projection and rendering. The opt-in production probe is
skipped unless private test credentials/configuration are provided; a local pass
does not establish production deployment or real Alexa device readiness.

The [traditional ASK adapter](../../docs/traditional-alexa.md) now reuses this same
Python orchestrator through signed HTTPS fulfillment. It has its own interaction
model/account-linking/console setup; the browser simulator remains visually and
behaviorally separate and is not an official Amazon simulator.

## Safe provenance

Each new backend response includes a run receipt projection. Expand **Why CountOn
said this** to see the expectation label, recorded evaluation, canonical sources,
signal count, accepted Bedrock output/fallback and safe trace labels. Evidence IDs,
provider payloads, tokens and hidden prompts are never rendered. This is backend
provenance, not browser inference. See the
[15-step final acceptance runbook](../../docs/trust-orchestrator.md).

### Owned expectation deep links

The result, resolution and notification links can pass `expectationId` and a
`starter` question to `/alexa`. The authenticated Next.js agent route validates the
UUID and forwards it as optional `expectation_id` to FastAPI. The existing
orchestrator treats it as a selection, then calls the original owned MCP
get/explain path. An ID never grants access or selects a CountOn user. No claim,
evidence or credentials need to appear in the URL. Existing utterance-only clients
remain compatible.
