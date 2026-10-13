# CountOn Person 1 release acceptance

Status date: **2026-10-13**  
Branch/revision audited: `feature/alexa-mcp` / `d57ecef9411b5ca07123a9ea7ecb91729cc30db5`

This report distinguishes local implementation, live verification, deliberate
simulation, and external blockers. No deployment, production migration, provider
configuration, credential change, commit, or push was performed.

## Release decision

**Local baseline: accepted. Live Alexa hackathon path: blocked.** The repository
has one Supabase user identity, one FastAPI/MCP service layer, six stable MCP tools,
one Bedrock compiler/clarification/investigator stack, one evidence schema, and one
deterministic evaluator. Ring and Bee simulators still use the authenticated backend
and persisted PostgreSQL results. No duplicate integration system was found.

The public deployment is behind this source revision. A read-only probe returned
200 from API/MCP health, but 503 from both readiness endpoints. The deployed API
OpenAPI does not contain `/api/v1/agent/converse`, `/api/v1/alexa`, or the monitoring
route, and deployed `/oauth/consent` returns 404. Real ASK account linking, voice
capture, provider synchronization, and Bedrock inference therefore cannot be
accepted against the current deployment.

## Feature acceptance matrix

| Feature | Status | Acceptance evidence and remaining limit |
|---|---|---|
| Supabase email/password UI and session handling | **Implemented locally** | Native signup, confirmation/resend, password login/recovery, SSR cookie refresh, protected routes, and logout have local UI/SDK tests. No real production signup/email delivery was performed. |
| FastAPI Supabase JWT and owner identity | **Implemented locally** | Issuer, audience, signature, role, expiry, UUID subject, profile bootstrap, RLS/ownership, and cross-user denial pass automated tests. Public missing-auth probe returns 401. No dedicated live user token was used. |
| Login with Amazon | **Blocked** | `custom:amazon` and the bounded UserInfo translator are implemented and fixture-tested. The provider is not live-configured/accepted, and no Amazon authorization produced a valid Supabase session. |
| Alexa ASK HTTPS adapter | **Implemented locally; blocked live** | ASK signature, certificate chain, timestamp, application/user consistency, replay, dialogue, linking failures, and persistence pass local tests. The deployed API lacks the route; ASK Console and Echo were not tested. |
| Alexa account linking | **Implemented locally; blocked live** | Uses Supabase OAuth server and CountOn JWTs, independently of Login with Amazon. Live OAuth server/client/redirect/refresh acceptance is incomplete and deployed consent is 404. |
| MCP Streamable HTTP and six tools | **Implemented locally** | `capture_expectation`, `get_expectation`, `list_expectations`, `compile_expectation`, `continue_expectation_compilation`, and `explain_expectation_mismatch` retain one top-level `request`. Public endpoint rejects missing/invalid auth; authenticated live discovery was not run. |
| Bedrock compiler and clarification | **Implemented locally; blocked live** | Strict schemas, grounding, repair, timeouts/retries, and safe failures pass fixtures. AWS preflight returned `LoginRefreshRequired`; no real invocation was made. |
| Bedrock mismatch explanation | **Implemented locally; blocked live** | Runs only for deterministic MISMATCH, cites allowed evidence IDs, and falls back safely. No live model explanation was accepted. |
| PostgreSQL persistence and deterministic evaluation | **Implemented locally** | Alembic-backed ownership, evidence/evaluation history, monitoring leases, replay controls, MATCH/UNKNOWN/MISMATCH, and notification deduplication pass against isolated PostgreSQL. Deployed readiness is 503. |
| Gmail / Google Calendar | **Implemented locally; blocked live** | OAuth, narrow scopes, encrypted grants, incremental synchronization, correlation, revocation, and safe disconnect are fixture-tested. No authorized live account was synchronized. |
| Outlook / Microsoft Calendar | **Implemented locally; blocked live** | Equivalent Microsoft Graph flows and delta processing are fixture-tested. No live tenant/mailbox/calendar was synchronized. |
| Amazon order evidence | **Implemented locally** | Comes only from authorized Gmail/Outlook messages with sender/order correlation. Login with Amazon grants no order access. No live order email was accepted. |
| Ring evidence | **Simulated** | Authenticated source-bound events persist as `SIMULATED_RING`; positive correlated observations can support evaluation. Missing detection remains UNKNOWN. No Ring account/device integration is claimed. |
| Bee simulator | **Simulated** | Authenticated source-bound events persist as `SIMULATED_BEE`; a promise remains context and does not prove fulfillment. |
| Bee CLI | **Implemented locally; blocked live** | Pairing, minimized staging, explicit import consent, checkpointing, and revocation are fixture-tested. No CLI installation or real Bee account/data access was verified. |
| Notifications | **Implemented locally** | MISMATCH creates one deduplicated in-app notification; MATCH stays silent and UNKNOWN continues monitoring. External email delivery remains opt-in and was not live-tested. |
| Audit History | **Implemented locally** | Owner-scoped PostgreSQL events expose expectation, minimal evidence fact, source, result, action, time, and simulated/live provenance. No full provider payload, transcript, token, prompt, or model response is stored. |
| Next.js dashboard | **Implemented locally** | Auth, expectations, evidence, notifications, integrations, simulators, and Audit History pass tests/build. Public homepage redirects and login loads, but deployed consent is missing and current backend routes are stale. |
| GitHub-hosted CI | **Blocked** | Latest run for this exact revision failed only strict backend Mypy; frontend and secrets passed. The two local `no-untyped-call` annotations now pass strict Mypy but are uncommitted/unpushed, so hosted CI has not rerun green. |

## Identity and authorization contract

Supabase Auth is the authentication authority. A verified access-token UUID `sub`
is the CountOn profile/owner ID used by expectations, source connections, evidence,
evaluations, notifications, audit history, MCP, and Alexa. Identity never comes
from an MCP tool payload, spoken slot, simulator event, provider record, or browser
supplied `user_id`.

Email/password and Amazon can see the same CountOn records only after explicit
Supabase identity linking to the same user. Matching email does not merge accounts.
Alexa account linking is separate: ASK obtains a CountOn Supabase access token; an
Amazon identity token is not accepted as a CountOn session. Provider grants remain
separate and owner-scoped.

## Implemented release routes

All backend routes below are under the public API origin and `/api/v1` unless noted:

| Purpose | Route |
|---|---|
| ASK fulfillment | `POST /api/v1/alexa` |
| Web conversational orchestration | `POST /api/v1/agent/converse` |
| Expectations | `POST/GET /api/v1/expectations`; `GET/PATCH/DELETE /api/v1/expectations/{id}` |
| Evidence and evaluation | `POST/GET /api/v1/expectations/{id}/evidence`; `POST /api/v1/expectations/{id}/evaluate`; evaluation history/latest reads |
| Source planning/binding | `POST /api/v1/expectations/{id}/monitoring-plan/preview`; `POST /api/v1/expectations/{id}/monitoring-plan/confirm`; `POST/GET /api/v1/expectations/{id}/sources`; `DELETE /api/v1/expectations/{id}/sources/{binding_id}` |
| Provider connections/sync | `/api/v1/integrations...`, Google/Microsoft OAuth callbacks, sync/disconnect, verified webhook routes |
| Ring/Bee simulators | `POST /api/v1/simulators/ring/expectations/{id}/events`; `POST /api/v1/simulators/bee/expectations/{id}/events` |
| Bee CLI bridge | `/api/v1/integrations/bee-cli/pairings`, `/pair`, `/bridge/candidates`, `/status`, `/candidates`, `/imports`, `/disconnect` |
| Notifications | `GET/PATCH /api/v1/notifications...`; preferences and delivery history routes |
| Audit History | `GET /api/v1/audit-events` with expectation/source/result/time filters |
| Amazon UserInfo translator | `GET /api/v1/auth/amazon/userinfo` |
| Health/readiness | `GET /health`, `GET /ready`; MCP host exposes the same paths and Streamable HTTP at `/mcp` |

Frontend auth/release routes include `/register`, `/login`, `/forgot-password`,
`/reset-password`, `/auth/callback`, `/oauth/consent`, `/alexa`, `/integrations`,
`/activity`, `/notifications`, and the expectations pages. Supabase, not FastAPI,
hosts Alexa's OAuth authorization and token endpoints.

## Exact configuration still required

### Backend API and MCP

```dotenv
ENVIRONMENT=production
DATABASE_TARGET=supabase
SUPABASE_DATABASE_URL=<private TLS PostgreSQL URL>
SUPABASE_URL=https://ctpvhospspchgtquvalc.supabase.co
SUPABASE_PUBLISHABLE_KEY=<publishable key>
ALLOWED_ORIGINS=["https://counton-frontend.vercel.app"]
MCP_PUBLIC_URL=https://counton-mcp.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com/mcp
COUNTON_CLARIFICATION_SIGNING_KEY=<shared private signing key>
CONVERSATION_STORE_BACKEND=postgres
CONVERSATION_ENCRYPTION_KEY=<shared private AES key>
OAUTH_ALLOWED_CLIENT_IDS=["<registered Supabase Alexa OAuth client id>"]
ALEXA_OAUTH_CLIENT_ID=<same registered client id>
ALEXA_SKILL_ID=amzn1.ask.skill.<actual skill id>
ALEXA_REQUIRE_CONFIRMATION=true
```

### Frontend/Vercel

```dotenv
NEXT_PUBLIC_APP_URL=https://counton-frontend.vercel.app
NEXT_PUBLIC_API_BASE_URL=https://counton-api.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com
NEXT_PUBLIC_SUPABASE_URL=https://ctpvhospspchgtquvalc.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<publishable key>
COUNTON_MCP_URL=https://counton-mcp.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com/mcp
NEXT_PUBLIC_ALEXA_OAUTH_CLIENT_ID=<registered Alexa OAuth client id>
NEXT_PUBLIC_ALEXA_REDIRECT_URIS=<comma-separated exact ASK callback URLs>
NEXT_PUBLIC_AMAZON_AUTH_ENABLED=true
```

Public variables contain origins, project URL, publishable key, and OAuth client ID
only. Database URLs, AWS credentials, OAuth client secrets, provider refresh tokens,
service-role keys, encryption keys, and signing keys stay on trusted services.

### Bedrock

```dotenv
BEDROCK_ENABLED=true
AWS_REGION=us-east-2
BEDROCK_MODEL_ID=openai.gpt-oss-120b-1:0
BEDROCK_MAX_TOKENS=1000
BEDROCK_TEMPERATURE=0.1
BEDROCK_REQUEST_TIMEOUT_SECONDS=30
BEDROCK_OPERATION_TIMEOUT_SECONDS=45
BEDROCK_MAX_RETRIES=2
```

Provide credentials through a supported AWS SDK runtime provider with least-privilege
`bedrock:InvokeModel`; do not copy developer login caches into deployment.

### Provider connectors

Enable only configured providers. Google and Microsoft require their client IDs,
client secrets, exact API callback URLs, the shared integration encryption key,
read-only scopes, and optional verified webhook settings from
`backend/providers.env.sample`. Gmail/Calendar and Graph must each pass real consent,
initial/incremental sync, expiry/revocation, and disconnect acceptance before being
called live.

## Alexa Developer Console configuration

1. Create/open the CountOn **Custom** skill, locale English (US), invocation
   **count on**. Copy the actual skill ID into `ALEXA_SKILL_ID`.
2. Import `backend/app/alexa/interaction-model.en-US.json`, save, build, and resolve
   console NLU errors. Do not add another language compiler.
3. Configure the HTTPS fulfillment endpoint as:

   ```text
   https://counton-api.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com/api/v1/alexa
   ```

   Use it only after the current backend revision is deployed and `/ready` returns
   200. Select the certificate option matching the actual trusted certificate.
4. Enable Account Linking with Authorization Code Grant and HTTP Basic client
   authentication. Register a confidential Alexa client in Supabase OAuth server,
   enable PKCE S256, and use:

   ```text
   Authorization URL: https://ctpvhospspchgtquvalc.supabase.co/auth/v1/oauth/authorize
   Token URL:         https://ctpvhospspchgtquvalc.supabase.co/auth/v1/oauth/token
   ```

5. Configure Supabase Authorization Path `/oauth/consent`. Copy every callback URL
   displayed by the Alexa console exactly into the Supabase client and
   `NEXT_PUBLIC_ALEXA_REDIRECT_URIS`. No callback value is recorded in this repo, so
   inventing one would be unsafe.
6. Request `openid`; add only approved `email` and `profile` scopes if the configured
   consent/account display requires them. The consent page rejects any other scope.
7. Put the confidential client secret only in Alexa/Supabase configuration. Put the
   client ID in the backend allowlist and frontend public client-ID variable.
8. Enable Development testing. Verify unlinked launch shows a LinkAccount card,
   complete consent in the Alexa app, then verify the issued **access token** has the
   expected Supabase issuer, `aud=authenticated`, `role=authenticated`, UUID `sub`,
   approved `client_id`, and valid expiry.
9. Test launch, list, detail, capture, multi-turn clarification, correction,
   confirmation, replay, mismatch explanation, Cancel/Stop, and expired linking in
   the ASK simulator. Confirm the saved row appears in the normal dashboard.
10. Test a physical Echo only after simulator requests pass signature/authentication,
    shared persistence, and the seven-second backend response budget.

No ASK signature bypass exists. Native Alexa+ MCP onboarding is outside this demo.

## Bedrock live invocation status

The backend selects `openai.gpt-oss-120b-1:0` in `us-east-2` and uses Bedrock Runtime
`Converse` through the normal AWS SDK provider chain. Offline tests validate strict
compiler/clarification/investigator schemas, one repair, bounded retry/timeouts,
token/concurrency budgets, grounded citations, and deterministic fallback.

The 2026-10-13 safe STS preflight failed with `LoginRefreshRequired`; identity values
were suppressed. Region/model/IAM access and real compiler/investigator quality are
therefore **blocked**, and no billed model request was attempted. After interactive
credential refresh, run:

```bash
cd backend
AWS_EC2_METADATA_DISABLED=true .venv/bin/python db/scripts/aws_preflight.py --verify-identity
AWS_EC2_METADATA_DISABLED=true BEDROCK_ENABLED=true .venv/bin/python db/scripts/bedrock_smoke.py --live
```

Then perform one real structured compilation, one clarification continuation, and
one grounded explanation using test evidence. Record latency and AWS request status,
without recording prompts, evidence contents, model output, identity, or credentials.

## Source and simulation acceptance

Gmail, Outlook, Google Calendar, and Microsoft Calendar use owner-bound OAuth grants,
encrypted tokens/checkpoints, narrow read scopes, stable provider IDs, incremental
sync, replay suppression, and revocation fencing. Amazon order facts are extracted
only from authorized email. These paths are local/fixture verified and still require
real test accounts.

Ring and Bee demo endpoints require an authenticated owner and an explicit allowed
source on the selected expectation. Simulation identity is server-authored and
persists with the evidence. Ring non-detection has no positive outcome value and
remains UNKNOWN. A Bee statement that the plumber will arrive records a commitment,
not arrival; it remains UNKNOWN without fulfillment evidence.

The optional Bee CLI bridge is independent of Supabase/Amazon login. It keeps Bee
authentication local, pairs using a single-use code, stages minimized records, and
requires browser consent before import. It is fixture-tested only.

## Audit History contract and examples

`GET /api/v1/audit-events` reloads owner-scoped PostgreSQL history. The `/activity`
page renders event time, expectation, minimal evidence values, source, deterministic
result, and actual action. Relevant event types include:

| Demo action | Audit event and safe links |
|---|---|
| User confirms capture | `EXPECTATION_CONFIRMED`, expectation ID, user/voice channel |
| User authorizes a source | `SOURCE_AUTHORIZED`, owned connection/binding reference |
| Provider/simulator fact arrives | `EVIDENCE_INGESTED` and, when applicable, `EVIDENCE_CORRELATED`, evidence ID, provider, provenance |
| Evaluator runs | `EVALUATION_COMPLETED`, evaluation ID, linked evidence ID, MATCH/UNKNOWN/MISMATCH |
| Confirmed contradiction | `MISMATCH_DETECTED` and one `NOTIFICATION_CREATED` |
| User requests explanation | `EXPLANATION_GENERATED`, evaluation/evidence IDs, grounding/Bedrock/fallback flags |
| Delivery worker succeeds | `NOTIFICATION_SENT` with notification reference |

Audit metadata is allowlisted. It excludes bearer/refresh tokens, OAuth codes,
passwords, full emails, raw calendar records, Bee transcripts/audio, ASK bodies,
model prompts, complete model responses, and database URLs. Simulator provenance is
shown as `SIMULATED_RING` or `SIMULATED_BEE`; authorized Bee CLI imports use
`LIVE_BEE_CLI` only after actual connector import.

## Demo scenario acceptance

### A. Electricity bill

Local automated acceptance proves a below-$150 expectation plus a $180 bill fact
produces deterministic MISMATCH, contradicted status, one notification, and linked
audit history. The Alexa dialogue, explicit confirmation, persisted shared row, and
grounded explanation/fallback paths are also tested. A real ASK request, live bill
email, and real Bedrock explanation remain blocked by deployment/account/AWS setup.

### B. Package delivery

Local acceptance proves authorized delivery facts plus an explicitly simulated Ring
observation are correlated only to the approved expectation. A supporting positive
observation can yield MATCH; non-detection yields UNKNOWN and no fabricated missed
delivery. Audit retains `SIMULATED_RING`.

### C. Bee commitment

Local acceptance proves the simulated landlord/plumber statement persists as
`SIMULATED_BEE` context after source approval. The promise alone yields UNKNOWN,
does not trigger a mismatch notification, and appears in owner-scoped Audit History.

## Local validation results

| Check | Result |
|---|---|
| Complete backend suite | **PASS — 1,312 tests**, 104 upstream ASK SDK deprecation warnings |
| Focused Alexa/electricity/Ring/Bee/audit/release journeys | **PASS — 76 tests**, same upstream warnings |
| Ruff | PASS |
| Mypy application scope | PASS — 158 source files |
| Strict orchestration Mypy scope | PASS — 37 source files after the two local audit-call annotations |
| Production smoke | PASS — API, six MCP tools, Streamable HTTP, signed Alexa, durable state, capture, provider tracking, notifications, source planning, correlation, and budgets |
| Synthetic orchestration evaluation | PASS — 26/26; zero Bedrock calls; live/model/human-review categories remain blocked |
| Frontend lint / typecheck | PASS / PASS |
| Frontend tests | PASS — 238; one credential-gated test skipped |
| Next.js production build | PASS |
| Bandit / pip-audit / npm audit | PASS / no known vulnerabilities / zero vulnerabilities |
| Pinned Gitleaks history and source scans | PASS — zero findings |
| `git diff --check` | PASS |

The first complete backend attempt lost its local PostgreSQL container and ended in
connection-refused setup errors. After restarting and verifying the container healthy,
the clean full rerun passed all 1,312 tests.

## Hosted and live status

The latest public GitHub Actions run for revision `d57ecef` is
[`38431260479`](https://github.com/aishwaryajakka/CountOn/actions/runs/38431260479),
completed **failure**. Frontend and secrets passed; backend failed the strict Mypy
step. The two required annotations pass locally but are not committed or pushed, so
hosted CI must remain reported as failed until an authorized rerun on the resulting
revision completes green. GitHub CLI is not installed; status was read from GitHub's
public Actions API.

Read-only public checks on 2026-10-13:

| Probe | Result |
|---|---|
| API `/health`; MCP `/health` | 200 / 200 |
| API `/ready`; MCP `/ready` | **503 / 503** |
| API protected route without token | 401 |
| MCP missing/invalid bearer | 401 / 401 |
| Vercel CORS / untrusted origin | exact grant / rejected |
| Deployed API current Alexa/agent/monitoring routes | **Missing** |
| Frontend `/`, `/login`, `/oauth/consent` | 307 / 200 / **404** |
| Authenticated remote API/MCP | BLOCKED — no dedicated access token; no login attempted |
| ASK simulator/Echo, provider accounts, live Bedrock, worker activity | NOT RUN |

## Three-minute hackathon script

This primary script requires every release blocker below to be cleared first.

1. **0:00–0:20 — Trust model.** Show the dashboard and say: “CountOn records what I
   expect, watches approved evidence, and only deterministic code decides the result.”
2. **0:20–1:10 — Alexa electricity capture.** Say: “Alexa, open Count On,” then
   “My next electricity bill should be below one hundred fifty dollars.” Confirm the
   structured expectation. Refresh the dashboard and show the same persisted row.
3. **1:10–1:45 — Evidence and result.** Trigger the authorized demo bill record for
   $180. Show persisted evidence, deterministic MISMATCH, one notification, and Audit
   History links. Ask Alexa why; show the concise evidence-grounded Bedrock response.
4. **1:45–2:25 — Package/Ring.** Open the package expectation, submit a clearly
   labeled simulated Ring observation, and show MATCH or UNKNOWN from persisted facts.
   Mention that no observation never becomes a fabricated nondelivery.
5. **2:25–2:50 — Bee.** Submit the simulated landlord/plumber commitment. Approve the
   proposed context and show UNKNOWN because a promise is not completion.
6. **2:50–3:00 — Audit.** Show expectation, evidence, source/provenance, result,
   notification action, and timestamps. Point out the explicit simulated labels.

## Backup demo plan

If ASK, OAuth, provider, or Bedrock acceptance is unavailable, state that clearly and
use only local authenticated interfaces:

1. Use `/alexa` web conversation to demonstrate the same coordinator, MCP tools,
   clarification, confirmation, PostgreSQL row, and dashboard refresh.
2. Use clearly tagged manual electricity evidence and the deterministic fallback
   explanation if Bedrock is unavailable.
3. Use the authenticated Ring and Bee simulator pages, keeping simulated labels
   visible. Demonstrate Ring non-detection and Bee promise as UNKNOWN.
4. Show the notification inbox and `/activity` Audit History after reload.
5. Do not call this an Echo, live provider, live Bedrock, Ring device, Bee wearable,
   or production acceptance demonstration.

## Remaining blockers, in priority order

1. **P0 — Deploy current API/MCP/frontend and migrations to an approved environment.**
   Require API/MCP `/ready` 200 and current Alexa/agent/monitoring routes plus frontend
   `/oauth/consent` before configuring ASK.
2. **P0 — Configure and accept Supabase OAuth server + Alexa confidential client.**
   Verify consent, authorization code, token, refresh, revoke, exact callbacks, linked
   Supabase UUID, and cross-user isolation.
3. **P0 — Run ASK Console and physical Echo acceptance.** Verify actual signed traffic,
   NLU, clarification, confirmation, shared persistence, replay, and latency.
4. **P0 — Refresh AWS credentials and accept real Bedrock.** Verify STS, region/model
   access, compiler, clarification, grounded explanation, latency, and safe failure.
5. **P1 — Run live Gmail/Outlook/calendar consent and synchronization** with dedicated
   test accounts; verify minimal evidence, cursors, revocation, and disconnect.
6. **P1 — Rerun GitHub Actions on the local Mypy fix** and require backend, frontend,
   and secrets green on the exact release revision.
7. **P2 — Optionally accept Bee CLI** with an authorized real account. This is not
   required for the simulator-based hackathon demo.

The success criterion is locally implemented and test-covered, but it is not yet
met live because the deployed release is stale/unready and Alexa/Bedrock/provider
credentials have not completed acceptance.
