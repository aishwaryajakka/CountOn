# COUNTOn ALEXA+ HACKATHON ACCEPTANCE

This checklist describes the **current six-tool implementation** and repeatable
acceptance. Earlier three-tool production demos do not certify the current
compiler, clarification ledger or investigator deployment. No new live rollout
or real Alexa/Echo integration is claimed by this cleanup. Current local command
results are recorded in the cleanup report; production checks must be run separately.

## Acceptance scope

| Category | Current implementation / verification |
| --- | --- |
| Streamable HTTP | Official Python MCP server and TypeScript client; test real initialize/discovery/calls, not REST substitutes. |
| Authentication | Existing Supabase JWT verifier, owned services and auth-gated `/alexa`; test missing/invalid/expired bearer and cross-user access. |
| Tools | Discover `capture_expectation`, `get_expectation`, `list_expectations`, `compile_expectation`, `continue_expectation_compilation`, `explain_expectation_mismatch`; all use exactly one nested `request`. |
| List/get | Actual current-user records; no match is honest, multiple matches require clarification. Search currently covers the first 50 records. |
| Capture | Compile/clarify first; persist only COMPILED through MCP capture, with its verified ticket and durable replay receipt. |
| Clarification | Existing canonical state handles correction, cancellation, replacement, expiration and max turns; no incomplete expectation is saved. |
| Why? | Latest owned evaluation gates investigation. MATCH, UNKNOWN and no evaluation skip it; MISMATCH uses bounded historical real evidence. |
| Shared persistence | MCP-created row must appear via normal FastAPI-backed detail/dashboard and survive refresh. |
| Agent Skill | Inspect `.agents/skills/counton/`; maps the actual six tools and evidence/outcome boundaries. |
| Security | No browser AWS/database/admin secrets, token logging, raw prompts/output in UI or client-supplied ownership. |
| Frontend | Run tests, lint, typecheck and production build against the current checkout. |
| Backend | Run full isolated-PostgreSQL suite, including MCP/intelligence/auth tests; do not count skipped tests as live acceptance. |

`tests/test_mcp_intelligence.py` covers real MCP compile → clarification → capture
→ PostgreSQL → deterministic MISMATCH → grounded explanation, followed by a newer
MATCH that skips investigation. Inference is mocked: this tests integration and
grounding, not live Bedrock quality. The evaluator remains the only outcome authority.

## Error and safety checklist

- Expired/missing/rejected auth: safe session/sign-in message, no tool write.
- Unreachable MCP/protocol error: safe unavailable message, no fabricated result.
- Unknown tool/flattened or malformed arguments: reject with safe typed errors.
- Missing/inaccessible expectation: no record enumeration or fabricated UUID.
- Empty/no matching list: honest response; multiple matches ask for specificity.
- Compiler disabled/unavailable/invalid output: no guessed capture payload.
- Cancelled/replaced/expired/consumed state: cannot replay to duplicate capture.
- MATCH/UNKNOWN/no evaluation: no investigator/evidence explanation call.
- No useful evidence, conflicting evidence, invalid citation or Bedrock failure:
  deterministic summary/fallback, explicit uncertainty, no unsupported cause.

Inspect safe traces only. Tokens must never be printed, returned or placed in
artifacts. The browser forwards its current bearer to `/api/mcp`; the Node route
forwards it to the real MCP server. No service-role key or parallel JWT verifier
is part of this flow.

## A. Remaining production prerequisites

Apply the existing migrations (including `compilation_sessions`), deploy the
current MCP/frontend code, configure backend Bedrock/model access and a private
shared clarification signing key, then discover all six tools and run live
intelligence acceptance. Repository code does not prove these steps were completed.
Real Alexa+/Echo onboarding, compatible OAuth discovery/account linking and native
device integration remain separate work. Speech-to-text, live provider ingestion,
scheduling workers and notification delivery are not claimed.

## B. Vercel Production variables

Verify these are configured; this document does not assert a live environment audit:

```env
NEXT_PUBLIC_API_BASE_URL=https://counton-api.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com
NEXT_PUBLIC_SUPABASE_URL=<existing Supabase project URL>
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<existing public publishable key>
COUNTON_MCP_URL=https://counton-mcp.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com/mcp
```

`COUNTON_MCP_URL` is server-only. Never add AWS credentials, database secrets,
service-role keys, signing secrets or shared test tokens to Vercel. Changes to
public build values require a rebuild. Backend rollout settings and exact smoke
commands are in [Bedrock integration](bedrock-integration.md).

## C. Manual production test

Use the configured `https://counton-frontend.vercel.app/alexa` address after rollout:

1. Signed out, verify the login gate; sign in with an existing dedicated test user.
2. Initialize/discover MCP. Confirm all six tools, not merely the core-tool badge.
3. Ask “What am I counting on?”; verify actual claims/statuses and safe list trace.
4. Ask “Tell me about my electricity bill”; use a real returned ID or honest no-match.
5. Ask “I'm counting on my bill being lower.” Answer “My electricity bill”,
   “My last bill was $142.10”, then “When my next bill arrives”. Check that no
   expectation appears before completion; verify separate compile/continue/capture traces.
6. Follow “View in CountOn”, refresh and verify the same persisted claim/criteria.
   Bill arrival is wording in the claim, not a fabricated deadline or scheduler.
7. In a separate incomplete draft, test “Actually make that $150”, “Never mind”,
   and a new package topic. Old bill facts must not leak into a replacement.
8. Ask why an owned electricity expectation with real evidence and a recorded
   MISMATCH failed. Compare the concise explanation against those supplied facts.
   No market/surcharge/causation claim without evidence is acceptable.
9. Repeat for MATCH, UNKNOWN and no evaluation: no mismatch investigator invocation.
10. Test ambiguity, no match, expired state and another user; verify no duplicate
    capture on replay and no access across owners. Keep technical provenance out of speech.
11. In DevTools, tool requests must go to `/api/mcp`, not direct browser MCP or
    FastAPI CRUD. Inspect header presence only, never copy the bearer value.
12. Confirm mobile layout/text and optional read-aloud. Deliberate user saves are
    real records; automated acceptance should use tagged data and exact-ID cleanup.

Safe unauthenticated endpoint probe:

```sh
curl -i -X POST https://counton-frontend.vercel.app/api/mcp \
  -H 'Content-Type: application/json' -d '{"action":"list_tools"}'
```

Expected `401/AUTH_REQUIRED`. Do not paste real credentials into shell history.

## D. 60-second judge script

Prepare a signed-in, validated deployment and an owned evidence-backed mismatch.

| Time | Action and spoken line |
| --- | --- |
| 0–10s | Open /alexa. “CountOn separates expectations from evidence. This is our web demo for the Alexa+ track.” |
| 10–20s | List expectations and expand trace. “These are my actual owned records through real MCP.” |
| 20–40s | Capture the grocery $120-this-week expectation. “Bedrock interprets; a separate MCP capture saves the complete criteria.” |
| 40–50s | View in CountOn and refresh. “The dashboard reads the same persisted row through FastAPI.” |
| 50–60s | Ask why the prepared mismatch failed. “Only the recorded deterministic mismatch permits grounded explanation; AI does not decide the result.” |

## E. Two-minute judge script

| Time | Action and spoken line |
| --- | --- |
| 0–20s | List/detail and show MCP trace. “Expectation → evidence → evaluation → exception. Missing evidence is not proof.” |
| 20–55s | Start an ambiguous bill, answer subject/baseline/timing. “One question at a time, preserving established facts; nothing is saved while incomplete.” |
| 55–75s | Show capture and refresh its normal detail view. “MCP acts through existing owned services; both paths share Supabase.” |
| 75–95s | Correct then cancel a separate incomplete draft. “Corrections retain facts; cancellation writes no expectation. Replay cannot duplicate compiled capture.” |
| 95–110s | Explain a prepared MISMATCH; contrast MATCH/UNKNOWN. “Bedrock uses only grounded evidence; successful or unknown outcomes skip investigation.” |
| 110–120s | Show SKILL.md. “Compatible hosts get the same six-tool contract. Silence is success. Real Alexa/Echo linking is still separate.” |

## F. Architecture

```text
Supabase Auth → browser session.access_token
Browser /alexa --Bearer--> Next.js POST /api/mcp (Node)
                           official MCP client
                           initialize → tools/list → tools/call
                           Streamable HTTP + same Bearer
                             ↓
                       CountOn Python MCP /mcp
                       existing JWT + ownership
                         ├─ compile / continue → Bedrock + canonical clarification
                         │                      ↔ durable compilation_sessions ledger
                         ├─ capture / get / list → existing CountOn services
                         └─ explain → latest evaluation → MISMATCH only → grounded AI
                             ↓
                       shared PostgreSQL / Supabase
                             ↑
Browser dashboard --Bearer--> FastAPI → same owned services
Real evidence → deterministic evaluator → persisted MATCH / UNKNOWN / MISMATCH
Agent Skill → host instructions for these six tools; no extra transport or App UI
```

## Repeating automated acceptance

From `frontend`: `npm run test`, `npm run lint`, `npm run typecheck`, `npm run build`.
From `backend`: `pytest` with a private loopback `TEST_DATABASE_URL` ending in
`_test`; see [database testing](../backend/db/README.md#local-workflow).
Without it database tests skip; never point that fixture at application data.

The read-only `tests/mcp-live.test.ts` requires explicit `COUNTON_MCP_URL` and
`COUNTON_MCP_TEST_ACCESS_TOKEN` in the process environment. It validates core reads;
use [intelligence smoke](bedrock-integration.md#exact-production-checks) for the
six-tool/live inference path. Neither a core badge nor mock output certifies AWS access.

`node tests/alexa-live.mjs` requires private `COUNTON_E2E_EMAIL` /
`COUNTON_E2E_PASSWORD`, plus `COUNTON_ALEXA_BASE_URL` and `COUNTON_E2E_API_BASE_URL`.
It compiles a tagged utterance, checks capture/normal API persistence, and cleans
only its exact test row. Artifacts are ignored under `frontend/test-results/alexa/`.
Use a dedicated account and review cleanup failures; never leave junk intentionally.

## Security review boundary

Verify ignored env/linkage files and scan tracked source for real credentials before
publishing. Synthetic test fixtures and documented loopback development values are
not production credentials. Safe response/log tests cover token/body redaction;
source inspection and local tests do not certify all cloud logs or remote Git refs.
No production secret/environment audit is claimed by this documentation cleanup.
