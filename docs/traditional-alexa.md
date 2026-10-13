# Traditional Alexa Custom Skill

The local HTTPS adapter and interaction model are implemented. **Developer Console
setup, live OAuth issuance/refresh validation, deployed simulator acceptance and real
Echo testing have not been completed by this change.** This is a traditional ASK
Custom Skill transport, separate from Alexa+ MCP onboarding and the `/alexa` web
simulator. There is no second compiler, clarification engine or investigator.

## Architecture and configuration

```text
Echo / ASK simulator
  → signed HTTPS POST /api/v1/alexa
  → Alexa signature + timestamp + configured application ID
  → context.System.user.accessToken
  → existing Supabase JWT verifier → owned CountOn principal/profile timezone
  → SAME AgentOrchestrator + canonical server conversation state
  → real MCP Streamable HTTP (Bearer token, nested request arguments)
  → existing compiler / clarification / capture / grounded investigator
  → shared Supabase database
  → concise Alexa PlainText response envelope

/alexa web → Next.js /api/agent → FastAPI /api/v1/agent/converse
  → SAME AgentOrchestrator → SAME MCP/services/database
Dashboard → FastAPI → SAME database
```

On the trusted FastAPI service, set:

```env
ALEXA_SKILL_ID=amzn1.ask.skill.<actual-ID-from-Developer-Console>
MCP_PUBLIC_URL=https://<actual-MCP-host>/mcp
```

Keep existing Supabase auth/database settings. Set the same strong
`COUNTON_CLARIFICATION_SIGNING_KEY` on API and MCP; configure Bedrock and AWS
runtime credentials only on the trusted Python services. The Alexa endpoint fails
closed with HTTP 503 when `ALEXA_SKILL_ID` is absent. Never store linked tokens,
AWS credentials or an OAuth client secret in source, session attributes or public
frontend configuration. The consent page uses Supabase's native OAuth server;
production uses encrypted PostgreSQL conversation snapshots and the new security
migration. No MCP tool names changed. See [production setup](production-readiness.md)
and `backend/production.env.sample` before enabling the endpoint.

Local startup:

```sh
docker compose up -d
cd backend
source .venv/bin/activate
python -m pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

In a second backend terminal, activate the same environment and run
`python -m app.mcp`. Use `MCP_PUBLIC_URL=http://localhost:8003/mcp` locally. A
Developer Console endpoint must be public HTTPS; deploy FastAPI or expose it through
a controlled HTTPS tunnel and retain every validation check. An ordinary unsigned
curl/Postman request must fail; no dev signature bypass exists.

## Request verification and privacy

Amazon's `ask-sdk-webservice-support` verifies the original UTF-8 body using
`Signature-256` / RSA SHA-256 and a ±150-second timestamp window. Both context and
session application IDs must equal `ALEXA_SKILL_ID`; their Alexa user references
must agree. Alexa `userId` is a transport reference, **never CountOn identity**.
Only the linked `context.System.user.accessToken` is used for authentication;
spoken slots and `apiAccessToken` cannot authenticate a CountOn user.

Certificate URLs are restricted to canonical HTTPS `s3.amazonaws.com/echo.api/*.pem`
on port 443 without credentials/query/redirects. Certificate download, body size and
cache are bounded. SDK SAN, expiry and body-signature checks are retained. The SDK's
legacy `certvalidator` depends on platform `oscrypto`; CountOn's maintained
`pyhanko-certvalidator` performs PKIX chain/digital-signature validation against
the Mozilla CA bundle; requester-supplied certificates cannot become trust roots.
The SDK still imports `oscrypto` before selecting this validator. Runtime requirements
pin the official, SHA-verified OpenSSL version-parser fix; CI imports both FFI paths
before collecting tests. See [Alexa CI compatibility](alexa-ci-compatibility.md).
No network fetching is permitted during chain building. Verification failures
return HTTP 400 without input or exception text. See Amazon's
[HTTPS verification requirements](https://developer.amazon.com/en-US/docs/alexa/custom-skills/host-a-custom-skill-as-a-web-service.html).

ASK bodies are limited to 32 KiB and language slots to 1,800 characters. Unknown
slots and unexpected session attributes are rejected. Responses expose speech and
an opaque reference only, without traces, raw model output or investigation
metadata. Existing operational logs record route/status/duration and verified user
ID; they do not record request bodies, Authorization, linked tokens or slots.

## Supported intents and speech

Import [the en-US JSON model](../backend/app/alexa/interaction-model.en-US.json).
Invocation name: **count on**. Each language intent has at most one broad
`AMAZON.SearchQuery` slot (`text`). No bill-specific price/type/baseline slots are
created; the existing compiler interprets language.

| Request | Translation into existing orchestration |
| --- | --- |
| LaunchRequest | “Welcome to CountOn. What are you counting on?”; no business action. |
| ListExpectationsIntent | Canonical list utterance → LIST_EXPECTATIONS → MCP list. Speech reads up to three actual claims. |
| GetExpectationIntent | Topic slot → GET_EXPECTATION; existing owned lookup/disambiguation. |
| CaptureExpectationIntent | Expectation language → COMPILE_EXPECTATION; pending replies/corrections → CONTINUE_CLARIFICATION; complete → MCP capture once per turn. |
| WhyExpectationIntent | Specified/current owned expectation → existing explanation tool. Only recorded MISMATCH runs investigator. MATCH/UNKNOWN/no evaluation skip it. |
| AMAZON.HelpIntent / FallbackIntent | Concise help, no arbitrary capability execution. |
| AMAZON.CancelIntent / StopIntent | Canonical cancellation, revoke conversation reference, close session. |
| SessionEndedRequest | Same termination; no outputSpeech. |

The adapter translates known ASK intents into language, not trusted plans or tool
calls. The orchestrator still selects and authorizes capabilities. Captures say
“Got it. I'll track that.” Explanations come from the existing approved response;
they cannot manufacture evidence or a verdict. Missing/expired linking returns a
LinkAccount card; other failures use safe speech without automatically retrying writes.

### Recognition and clarification

The model covers these examples via phrase slots:

- List: “what am I counting on”, “what are my expectations”, “what am I tracking”,
  “show my expectations”, “tell me what I'm counting on”.
- Get: “tell me about my electricity bill”, “check my electricity bill”, “tell me
  about my package”, “what is happening with my refund”, “check my appointment”.
- Capture: “I'm counting on my electricity bill being lower”, “I'm expecting my
  package Friday”, “I'm counting on my refund arriving this week”, “keep track of
  my next bill”, “I expect the plumber Tuesday”. Unsupported compilation is safe,
  not a promise of new evaluator support.
- Why: “why did it fail”, “why didn't that match”, “why was my bill higher”,
  “why did this expectation fail”, “explain what happened”.

Each SearchQuery sample has a carrier phrase as required by
[Amazon's slot documentation](https://developer.amazon.com/en-US/docs/alexa/custom-skills/slot-type-reference.html#amazonsearchquery).
During clarification/disambiguation, `Dialog.ElicitSlot` resets only the ASK text
slot and asks the **existing compiler's question**; the next bare reply is forwarded
unaltered. This supports “My electricity bill”, “My last bill was $142.10”,
“Actually make that $150”, “When my next bill arrives”, and selecting “first”.
If recognition misses a bare reply, say “my answer is …”. Corrections/new topics
still belong to the canonical clarification engine. Test actual NLU in the console;
local JSON tests cannot establish recognition accuracy.

## Session and replay boundary

The sole returned session attribute is `counton_session`, a rotated opaque
43-character reference. Trusted compiler state stays in the existing
`AgentSessionStore`. A bounded transport cache binds that handle to the signed
Alexa application/session/user references and **previously JWT-verified CountOn
owner**. No token or full chat history is stored. Exact retries return the cached
safe envelope; changed bodies with the same request ID and cross-user use are
rejected. Old handles cannot start a new draft. Transport entries retain retry
tombstones beyond the timestamp window; capacity/64-turn limits fail safely.

Initial compilation IDs are deterministically derived from the verified owner,
Alexa session and request ID. The existing MCP PostgreSQL compilation ledger
therefore also prevents first-turn retry duplication after API process restart.
With production PostgreSQL conversation storage, continuation context and retry
envelopes survive restarts. Development memory storage still loses context.
Cancel/Stop consumes an active draft through existing cancellation when reachable
and always revokes its local reference. If linking is absent on SessionEnded, no
private state is accessed and remaining state expires under its fixed TTL.

Owned expectation detail speech includes the persisted lifecycle status, rather
than inventing an evaluation. Edit or cancel an already saved expectation through
the web application and reread it through Alexa/MCP. Voice editing and saved-row
cancellation are not implemented; Cancel/Stop terminates the conversation/draft.

Production requires `CONVERSATION_STORE_BACKEND=postgres` and a shared private
`CONVERSATION_ENCRYPTION_KEY`. The existing AgentSessionState is encrypted at rest;
owner-bound, fenced leases serialize concurrent turns. A core handle is consumed
before tool execution, so a crash cannot replay a write from that handle. Exact ASK
request retries return durable cached replies or uncertain-save speech. No bearer
token or transcript is stored. Memory storage remains a development option only.

The endpoint has a seven-second total deadline with no automatic retries. ASK has
an [eight-second response budget](https://developer.amazon.com/en-US/docs/alexa/custom-skills/progressive-response-api-reference.html).
If inference/network work is slow, the user receives safe uncertain-save speech
and is directed to check CountOn before retrying. A cancelled remote call may
already have persisted; its ledger prevents replays from making a second row.
Live Bedrock/MCP latency within the ASK budget is a deployment acceptance blocker,
not solved by a progressive response or by the long web simulator timeout.

## Account linking: implementation status and manual configuration

**Implemented:** native Supabase OAuth consent at `/oauth/consent`, strict callback
and client/user validation, existing JWT verification with allowlisted OAuth
`client_id`, Alexa client binding and MCP bearer forwarding. Supabase owns codes,
PKCE, token issuance and refresh; CountOn does not implement a competing OAuth server.
The production migration restricts linked clients from direct Supabase SQL access.

**Manual:** enable the existing project's [OAuth server](https://supabase.com/docs/guides/auth/oauth-server/getting-started),
register a confidential Alexa client (`client_secret_basic`, PKCE S256), set Site URL
and Authorization Path `/oauth/consent`, and register every exact redirect URI shown
in your ASK console. Set frontend `NEXT_PUBLIC_ALEXA_OAUTH_CLIENT_ID` and
`NEXT_PUBLIC_ALEXA_REDIRECT_URIS` (comma-separated exact callbacks). Set backend
`OAUTH_ALLOWED_CLIENT_IDS` (JSON array), `ALEXA_OAUTH_CLIENT_ID`,
`ALEXA_REQUIRE_CONFIRMATION=true` and durable store configuration. Never expose the
client secret publicly. Live issuance, refresh/revocation, consent and Alexa
recognition/device behavior still require external acceptance; see the
[production runbook](production-readiness.md).

Provider URLs (replace only with the existing project origin):

```text
Authorization URI: https://<project-ref>.supabase.co/auth/v1/oauth/authorize
Access Token URI: https://<project-ref>.supabase.co/auth/v1/oauth/token
```

Use Authorization Code Grant; client ID/secret from registration; HTTP Basic token
authentication; PKCE S256; approved `openid` scope (plus only needed/approved
additional scopes). Configure real privacy-policy/domain details and an access-token
lifetime matching the provider; verify refresh grant actually works. These values
require provider setup, not just copying console fields.

Before enabling business actions, verify the **access token**, not ID token, has
the existing verifier's expected issuer, `aud=authenticated`, `role=authenticated`,
UUID `sub`, expiry/issued-at claims and supported signature/JWKS. Supabase OAuth
client audience/token claims can require provider configuration. Do not weaken
CountOn JWT verification to accept incompatible tokens; live account linking
remains blocked until issuance and refresh satisfy this contract.

## Exact Developer Console checklist (manual)

1. Open [Alexa Developer Console](https://developer.amazon.com/alexa/console/ask).
2. Open the **CountOn Custom Skill** (create a Custom skill with your own HTTPS
   hosting only if it does not exist). Select English (US).
3. Build → Invocation: confirm `count on`. Copy its Skill ID into backend
   `ALEXA_SKILL_ID`; redeploy the API with the dependencies above.
4. Build → Interaction Model → JSON Editor: import the model linked above. Verify
   List/Get/Capture/Why and Yes/No/Help/Cancel/Stop/Fallback intents and broad `text` slots.
5. Verify the sample utterances and Capture dialog slot/prompt. Keep skill-controlled
   elicitation; do not add another Alexa domain compiler.
6. Click **Save Model**.
7. Click **Build Model** and resolve any console validation/recognition issues.
8. Build → Endpoint: choose **HTTPS**, default endpoint
   `https://counton-api.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com/api/v1/alexa`
   **only after deploying this code there**. Select the certificate option matching
   the actual AWS-hosted certificate (trusted CA wildcard if that is what is served).
   Do not use the `/mcp` endpoint or a Vercel page as ASK fulfillment.
9. Build → Account Linking: enable it, choose Authorization Code Grant, populate
   the provider URLs/client credentials above, HTTP Basic, scope/PKCE/domain details,
   and register the exact displayed redirect URLs with the provider. Require linking
   to enable the skill; verify the consent and refresh flows in the Alexa app. The
   adapter still independently fails closed without a valid link.
10. Test → enable **Development**. Use the same Amazon account for the linked skill
    and simulator; confirm the skill is enabled and account linked.
11. Run the checklist below in the ASK simulator; inspect only safe response fields.
12. Test on a real Echo **after** simulator, signature/auth, shared persistence and
    latency acceptance passes. Certification/publication is a separate manual process.

## Simulator checklist

1. “open count on” → welcome; unlinked users receive a LinkAccount card.
2. “what am I counting on” → owned real records (or honest empty list).
3. “tell me about my electricity bill” → owned record; duplicates disambiguate.
4. “I'm counting on my bill being lower” → one clarification question; then
   “My electricity bill”, “My last bill was $142.10”, “When my next bill arrives”.
5. Answer any additional currency/timing question, then say “yes” to the grounded
   confirmation. Confirm no incomplete/unconfirmed row, then one saved row in the dashboard after
   refresh. Test correction before completion and cancellation of a separate draft.
6. Ask “why did it fail” after selecting a prepared owned MISMATCH with real evidence.
   Test MATCH/UNKNOWN too; neither may invoke the investigator. Do not fabricate
   evidence/evaluations to imitate an explanation.
7. Test Cancel, Stop, Help, fallback, relinking, expired state and unavailable MCP/
   Bedrock; responses stay concise and reveal no credentials/state internals.
8. Verify response latency under eight seconds with the deployed model/network.

## Tests

From backend (isolated local PostgreSQL `TEST_DATABASE_URL` ending in `_test`):

```sh
pytest tests/test_alexa.py tests/test_agent.py tests/test_agent_sessions.py tests/test_agent_api.py
ruff check app/alexa app/api/v1/alexa.py app/agent/session.py tests/test_alexa.py
mypy --strict --follow-imports=silent --ignore-missing-imports app/alexa app/api/v1/alexa.py app/agent/session.py
```

Tests validate RSA SHA-256 request signatures, certificate chains under a **test-only
CA**, timestamp/skill identity, auth/link failures, session privacy/isolation/replay,
canonical compiler/clarification/cancellation, deterministic investigation gates,
and real loopback Streamable HTTP → database → dashboard with a signed fixture JWT.
AWS inference is mocked. Test roots/auth overrides exist only in tests. Local passes
do not certify live Alexa NLU, OAuth/account linking, ASK/Echo access or production
latency. The upstream ASK SDK currently emits certificate datetime deprecation
warnings; request validation remains enabled.

## Trust receipts and audit

The same orchestrator used by /alexa now produces deterministic TrustResponse
receipts and writes whitelisted runs to existing audit_events. ASK speech carries
only the approved answer; session attributes still contain no receipt, model
prompt, evidence payload or token. Audit failure never retries a completed capture.
See [final trust acceptance](trust-orchestrator.md) for source permissions, audit
delivery limits and ordered Console/simulator/Echo checks.
