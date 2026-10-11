# CountOn production readiness

## Assessment (2026-10-11)

The core monitoring and intelligence flows are implemented and verified locally.
**Production acceptance is blocked.** Local provider/model mocks validate contracts
and failure handling, not AWS access, provider permissions, Alexa recognition,
account linking, device behavior, cloud logging, or production latency.

Architecture and all six existing MCP tool names/contracts remain compatible:

```text
Web /alexa → authenticated Next.js /api/agent
  → JWT-authenticated FastAPI /api/v1/agent/converse
  → constrained Trust Orchestrator → real MCP Streamable HTTP
ASK / Echo → signed HTTPS /api/v1/alexa → linked Supabase OAuth access token
  → same JWT verification / owned principal / Trust Orchestrator
  → same MCP compile / continue / capture / get / list / explain
MCP → CountOn services → PostgreSQL / Supabase
Evidence provider → owned normalized evidence → durable leased worker
  → deterministic evaluator → evaluation + deduplicated in-app notification
Dashboard → authenticated FastAPI → same database
```

Bedrock interprets or explains bounded supplied facts. Deterministic code alone
sets MATCH / MISMATCH / UNKNOWN; missing, stale, ambiguous/conflicting, unauthorized
or insufficient observations cannot justify success/failure. No proactive Alexa
notifications are implemented. The inbox is the reliable initial channel.

## Deployment investigation follow-up (2026-10-11)

### Evidence and root-cause boundary

**Rollout/schema drift is confirmed; production readiness remains blocked.** The
private configured Supabase URL successfully connected with `sslmode=require` in
read-only checks. Authentication and network/TLS connectivity work from this
machine. Its actual Alembic revision is `6e302a79bd01`; local code requires
`8a524c91df23`. `integration_credentials`, `provider_oauth_states`, and
`conversation_records` are absent. Existing `monitoring_jobs` alone does not prove
that its new leasing/provider columns exist or a worker is running.

Live API lacks `/api/v1/agent/converse`, `/api/v1/alexa`, and
`/api/v1/expectations/{expectation_id}/monitoring`. Authenticated real MCP discovery
finds the three core tools but not `compile_expectation`,
`continue_expectation_compilation`, or `explain_expectation_mismatch`.
Vercel production lacks `/oauth/consent` (404). These are implemented/tested locally;
**do not rebuild them to fix deployment drift**.

The precise failing dependency inside the *currently deployed* readiness check is
not proven: Lightsail environment/image/DB target and internal logs are inaccessible
with expired AWS credentials. The locally configured database is not yet proven to
be the container's database. An older image can reject a database newer than its
own Alembic head; deploying new code alone would also reject the observed old schema.
Do not infer a deployed revision from Git HEAD or fix this by stamping the database.
Local HEAD is `1d4cf93` on `feature/alexa-mcp`, with extensive uncommitted prior work;
HEAD alone does not identify this release's full contents.

Readiness now logs only a fixed failure code, counts of missing tables/columns,
and bounded expected/observed revision identifiers. Public responses remain generic.
Codes distinguish missing tables, revision mismatch, missing columns despite a head
stamp, missing migration files, pool timeout, auth/permission failure, TLS/DNS/
connection/query failure. SQL/driver exception text, hosts, URLs and credentials
are omitted. Settings validates production encryption keys before startup;
`/ready` still checks database/schema, not optional AWS/Graph access or worker activity.
Pool/connect limits remain 5 seconds; readiness statements have a 1-second timeout.

### Fixes in this follow-up

- `app/services/readiness.py`: registered model discovery, actionable internal failure
  classification and required-column checks in addition to exact head/table checks.
- `app/core/logging.py`: allowlisted readiness fields only.
- `db/scripts/check_schema.py`: uses the same inspection and includes **all** metadata
  tables, including backend-only credentials/OAuth state/conversation/compilation tables.
- Ignored `backend/.env.local`: added explicit `sslmode=require` to its existing
  Supabase URL after a successful TLS test; retained credentials, set file mode 0600.
  It is a development config, not a production env snapshot: production conversation
  key/store and service envs still require separate private injection.
- New `db/scripts/aws_preflight.py`: credential resolution, optional bounded STS
  identity check, correct provider-specific refresh advice; never invokes a model,
  prints identities, or returns credentials.
- New `db/scripts/deployment_probe.py`: explicitly remote, read-only health/readiness,
  CORS/auth/API contract and real MCP initialize/six schemas/list/get/shared-row checks.
  No capture/compile/evaluation/delete. Empty lists/missing tokens are BLOCKED, never
  fabricated successes. It does not replace browser/device/worker acceptance.
- New regression tests: `test_deployment_readiness.py`, `test_aws_preflight.py`,
  `test_deployment_probe.py` (35 new cases). No existing tests removed or weakened.

### Actual remote verification

| Probe | Result |
| --- | --- |
| API + MCP `/health` | PASS: 200, correlation headers present |
| API + MCP `/ready` | FAIL: 503 |
| Missing API auth; missing/invalid MCP auth | PASS: 401 |
| Real demo Supabase login, authenticated API list | PASS: 200; token remains in memory only |
| MCP Streamable HTTP initialize | PASS: actual SDK/network handshake |
| Core tools/list, nested request schemas, list/get | PASS: real owned data; no claim/ID printed |
| Required six-tool deployment | FAIL: three intelligence tools absent |
| Existing owned row through MCP and API | PASS: ID/claim match internally; nothing created/deleted |
| Approved frontend CORS; untrusted origin rejected | PASS: exact origin allowed; other origin 400/no grant |
| Vercel production alias | `https://counton-frontend.vercel.app`, Ready deployment created Oct 8 |
| Frontend public pages | `/` redirects (307); `/login` and `/alexa` 200; consent 404 |
| Production Vercel env presence | PASS: `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, `COUNTON_MCP_URL` all exist; values not displayed |
| New Alexa OAuth frontend config | FAIL: `NEXT_PUBLIC_ALEXA_OAUTH_CLIENT_ID` and `NEXT_PUBLIC_ALEXA_REDIRECT_URIS` are missing; configure actual registered client/exact ASK callbacks before consent rollout |
| Real browser login/API interaction | NOT RUN: HTTP/CORS checks are not a browser acceptance test |
| Cloud worker/logs/metrics/edge limits | BLOCKED: AWS control-plane access unavailable; no metrics token |
| Database backup restore and staging/live RLS | NOT RUN: no approved restore target/verified backup/key access |

### AWS status and exact refresh

Default profile uses the **login** provider (`login_session`), not SSO. No credential
env override is present. Boto3 resolves that provider but credential refresh raises
`LoginRefreshRequired` before STS/Bedrock invocation. The `lightsail-process` profile
also fails with `CredentialRetrievalError`; inspect its existing process/source login
without printing process output. AWS CLI is 2.37.9 (supports `aws login`).
Region/model permission and model availability are **not verified**, because valid
credentials are a prerequisite; neither AccessDenied nor a model error was returned.

In the user's terminal (interactive browser sign-in required):

```sh
aws login --profile default
cd backend
source .venv/bin/activate
AWS_PROFILE=default python db/scripts/aws_preflight.py --verify-identity
AWS_PROFILE=default BEDROCK_ENABLED=true python db/scripts/bedrock_smoke.py --live
```

Use `aws sso login --profile NAME` only for a configured IAM Identity Center profile.
[AWS login documentation](https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sign-in.html)
explains the temporary local session and provider chain. This is not an unattended
production credential solution. Configure and verify a least-privilege durable
runtime provider separately on Lightsail; do not copy the developer login/cache into
images. No AWS login/config/credential file was modified in this pass.

### Read-only inspection after credential refresh

Inspect each container service; this query outputs env **names**, never values:

```sh
aws lightsail get-container-services --region us-east-2 --service-name counton-api \
  --query 'containerServices[0].{state:state,version:currentDeployment.version,containers:currentDeployment.containers.*.{image:image,envNames:keys(environment)},pendingVersion:nextDeployment.version}'
aws lightsail get-container-services --region us-east-2 --service-name counton-mcp \
  --query 'containerServices[0].{state:state,version:currentDeployment.version,containers:currentDeployment.containers.*.{image:image,envNames:keys(environment)},pendingVersion:nextDeployment.version}'
```

Use [GetContainerLog](https://docs.aws.amazon.com/cli/latest/reference/lightsail/get-container-log.html)
with the actual container name to inspect private service logs. Do not paste raw
logs or container envs into chat. Record only readiness code/revision/counts and
correlation IDs. Privately compare selected database/auth project, TLS, pool/connect
limits, encryption/signing keys, MCP URL, production flags and worker service settings.
Environment presence alone does not establish correct values or a running worker.

Read-only remote probe from `backend`:

```sh
python db/scripts/deployment_probe.py --remote \
  --api-url https://counton-api.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com \
  --mcp-url https://counton-mcp.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com/mcp \
  --frontend-origin https://counton-frontend.vercel.app
```

Inject a dedicated `COUNTON_TEST_ACCESS_TOKEN` privately. Explicit `--demo-login`
uses the existing development/test credential helper and real Supabase auth; no
bypass. The follow-up ran with that flag. Exit 0 means performed read-only checks
passed, 1 means a failure, 2 means blocked coverage; output identifies remote scope.

### Prepared rollout/rollback (NOT EXECUTED)

The SQL-only `alembic upgrade 6e302a79bd01:head --sql` preview was generated successfully
(8,290 bytes) and includes both new revisions/tables/OAuth restrictions. This is an
Alembic-generated review artifact, not a replacement schema script. No SQL was applied.

From `backend`, after staging/backup/access review:

```sh
umask 077
COUNTON_RELEASE_DIR=$(mktemp -d)
alembic heads
python db/scripts/check_schema.py
alembic upgrade 6e302a79bd01:8a524c91df23 --sql > "$COUNTON_RELEASE_DIR/schema-upgrade.sql"
```

A failing schema check is expected before rollout; do not chain it to an automatic
migration. Confirm the actual container DB head first. Privately capture previous
API/MCP deployment JSON (includes secrets; mode 0600, outside Git), image references,
worker command/config and frontend deployment ID. Review full local dirty contents;
prepare a traceable immutable release image and record its digest. Keep credentials
out of build context (`backend/.dockerignore` already excludes env/venv/Git).
A local image preview only, from repo root:

```sh
docker build --label org.opencontainers.image.revision="$(git rev-parse HEAD)" \
  --label org.counton.working-tree=dirty -t counton-release:review backend
```

No image build/push or deployment was executed here; the dirty label makes clear
that the commit label alone is not the tested source manifest.

**Only after explicit production authorization**, restored staging backup acceptance,
worker drain and private production config review:

```sh
# Trusted backend migration environment, private migration-role DB credentials:
alembic current
alembic upgrade 8a524c91df23
python db/scripts/check_schema.py
# Reviewed private JSON includes serviceName, containers and publicEndpoint:
aws lightsail create-container-service-deployment --region us-east-2 \
  --cli-input-json "file://$COUNTON_RELEASE_DIR/api.release.json" > "$COUNTON_RELEASE_DIR/api.result.json"
aws lightsail create-container-service-deployment --region us-east-2 \
  --cli-input-json "file://$COUNTON_RELEASE_DIR/mcp.release.json" > "$COUNTON_RELEASE_DIR/mcp.result.json"
# From repo root, approved frontend deployment after matching backend is ready:
vercel --prod --cwd frontend
```

JSON payloads must be prepared from the **actual** current inventory, retaining
container names/ports/endpoint settings and injecting reviewed new env privately;
no invented payload is ready for approval until access is restored. Start/supervise
worker only after matching schema/services pass, then rerun the remote probe and
full browser/OAuth/worker/provider/device scenarios. `/ready` must be 200 on both
services before eligibility for live acceptance.

Prefer image rollback while retaining the expanded compatible schema, after staging
compatibility verification. Restore saved API/MCP deployment payloads with the same
`create-container-service-deployment --cli-input-json file://...` commands and restore
the recorded Vercel deployment via its dashboard. A destructive database rollback
requires separate approval and backup: disable/revoke linked OAuth clients first;
`alembic downgrade 6e302a79bd01` removes new monitoring/provider/conversation data and
OAuth SQL restrictions. Never downgrade an active worker or retain linked clients
without those policies. Re-upgrade cannot recover deleted records; use a tested
backup restore and separate encryption/signing key backups. Restored staging must
keep workers/provider delivery disabled, then verify row/history counts, schema,
RLS/roles and decryptability before enabling any outbound operation.

### CI and follow-up checks

Public GitHub Actions inventory returned 200: `.github/workflows/ci.yml` is absent
remotely. It is still untracked locally. CI has **not** run for this release;
publication requires separately authorized commit/push/PR. No `gh` CLI is installed.
The existing workflow runs on push/PR, not workflow_dispatch; do not claim a manual
workflow trigger was performed.

Actual follow-up commands: backend suite **1044 passed, zero skips**, Ruff,
normal mypy (125 files), new smoke-script mypy (2 files), strict mypy (37 files),
Bandit medium/high gate, pip-audit, npm production audit, all four local production
smoke groups, frontend lint/typecheck/test/build and source/history Gitleaks passed.
Frontend retains **123 passed, one credential-gated live test skipped**.
Offline Alembic preview passed; real migration/rollback/metadata tests ran in the
isolated local suite. Live probe exited 1 for readiness/deployment drift; AWS preflight
and harmless model probe exited 1 for LoginRefreshRequired, no AWS error code returned.
No cloud migration, deployment, commit, push, AWS sign-in, provider/device acceptance
or backup restore was performed.

New Alexa consent deployment additionally requires Vercel production
`NEXT_PUBLIC_ALEXA_OAUTH_CLIENT_ID` and `NEXT_PUBLIC_ALEXA_REDIRECT_URIS` (currently
missing), followed by an approved frontend rebuild/deploy. They are public client ID
and exact callback URLs; confidential client secret belongs only in Supabase/ASK.

Eligibility remains **BLOCKED** until deployed readiness, matching image/schema/config,
and required service dependencies are confirmed healthy. Remaining P1 external
checks are native OAuth/refresh/revocation/Echo, real AWS/IAM/inference/voice latency,
live worker/Graph, staging RLS/backup restore, shared edge limits and telemetry.

## Implemented security boundaries

- All six tools accept exactly one top-level `request`; no caller `user_id`.
  Owned reads precede investigation. Foreign IDs and missing IDs fail identically.
  Unknown tools and schema failures do not echo rejected content.
- Existing Supabase JWT verification is reused. Anonymous users and OAuth clients
  not in `OAUTH_ALLOWED_CLIENT_IDS` are rejected. ASK additionally requires its
  configured `ALEXA_OAUTH_CLIENT_ID`; a normal web JWT is not a linked Alexa token.
- OAuth clients may read owned expectations and use the constrained agent route;
  Raw evidence/evaluation API reads, deletion, provider management and evidence
  mutation are denied; explanations expose only the existing grounded MCP contract. Supabase restrictive
  RLS policies prevent linked OAuth clients bypassing services through direct SQL.
  Existing normal web owner policies remain in force. No service-role frontend key.
- ASK retains SDK SHA-256 body verification, canonical Amazon certificate URL,
  bounded certificate loading, maintained PKIX validation, configured application
  ID, matching session identity and ±150-second timestamp validation. Test CA roots
  occur only in tests. There is no unsigned or development authentication bypass.
- Production conversation records use AES-GCM, owner-bound associated data, fixed
  TTL, opaque rotated handles, short PostgreSQL leases and fencing. The existing
  AgentSessionState/canonical clarification format is reused. No bearer token or
  full transcript is persisted. Capacity is 1,024 records total across core/ASK
  transport; expired idle records are pruned on admission.
- A core handle is consumed durably **before** remote actions. Crashes cannot replay
  an old handle into a fresh compile/capture. Successful turns issue a new handle;
  uncertain responses require checking records and starting a new conversation.
  Exact ASK retries return durable safe replies/tombstones; changed-body retries
  and cross-user session reuse fail closed. The compilation ledger atomically
  deduplicates captures. Raw structured capture without a compiler receipt remains
  non-idempotent by contract; clients must not automatically retry it.
- Linked Alexa creation asks for explicit confirmation after compilation and
  before capture. Yes saves once; No/Cancel never saves. Active draft corrections,
  new topics, cancellation and expiry use the existing engine. After the final
  confirmation prompt, corrections require cancelling/restating rather than
  silently editing a completed draft. No high-impact external actions are exposed.
- External evidence is data, never an instruction source. Investigator citations,
  source permissions and rendered explanations are checked deterministically;
  models cannot assign outcomes or execute tools. Existing malicious-input tests
  cover policy overrides, secret-shaped input and invalid citations.

## Secure deployment configuration

Use ignored `backend/.env.local` locally, or privately injected runtime variables.
`backend/production.env.sample` and `backend/monitoring.env.sample` are guides;
Pydantic Settings remains the only loader. Never commit credentials or echo secrets.

| Trusted Python services | Action |
| --- | --- |
| `ENVIRONMENT` | `production` |
| `DATABASE_TARGET`, `SUPABASE_DATABASE_URL` | `supabase`; private psycopg PostgreSQL URL with TLS (`sslmode=require` or certificate verification) |
| `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY` | Existing project, same issuer/JWKS as frontend |
| `ALLOWED_ORIGINS` | JSON array of exact deployed frontend HTTPS origins, no slash/wildcard |
| `MCP_PUBLIC_URL` | Canonical public HTTPS `/mcp`; configure API and MCP consistently |
| `MCP_ALLOWED_ORIGINS` | JSON array, default `[]`; server-to-server callers need no browser CORS grant |
| `COUNTON_CLARIFICATION_SIGNING_KEY` | Strong secret shared by API/MCP; rotate with active-draft invalidation |
| `CONVERSATION_STORE_BACKEND` | `postgres` required in production |
| `CONVERSATION_ENCRYPTION_KEY` | Privately generated base64url 32-byte random key shared by API replicas |
| `ALEXA_SKILL_ID`, `ALEXA_OAUTH_CLIENT_ID` | Actual ASK skill and registered Supabase confidential client IDs |
| `OAUTH_ALLOWED_CLIENT_IDS` | JSON array of explicitly approved OAuth client IDs (including Alexa) |
| `ALEXA_REQUIRE_CONFIRMATION` | `true`; required for enabled production Alexa |
| `BEDROCK_ENABLED`, `AWS_REGION`, `BEDROCK_MODEL_ID` | Enable only after live smoke; `us-east-2`, `openai.gpt-oss-120b-1:0` unless deliberately overridden |
| `BEDROCK_REQUEST_TIMEOUT_SECONDS`, `BEDROCK_OPERATION_TIMEOUT_SECONDS`, `BEDROCK_MAX_RETRIES` | Defaults 30s / 45s / 2 additional attempts; tune with live measurements |
| `AGENT_EXECUTION_TIMEOUT_SECONDS`, `MAX_REQUEST_BYTES` | Defaults 45s / 131072 bytes; ASK additionally limits body to 32768 and response to 7s |
| `OPERATIONS_METRICS_TOKEN` | Private random >=43-character bearer token for API `/metrics` |
| `MONITORING_ENABLED` | `true` on worker service; see recurrence/leases/retry/Graph setup in monitoring docs |

AES conversation and provider-token keys are separate. Generate secrets directly
into a private secret manager/ignored file with mode 0600; don't print them. Keep
production signing/encryption keys stable across replicas/restarts. Rotating the
conversation key invalidates existing records; drain/expire sessions first. Back up
keys separately from encrypted database backups. SQL and provider token logs must
remain disabled, including reverse proxy/access logging of headers and bodies.

Frontend/Vercel public variables (never AWS/client secrets):

```text
NEXT_PUBLIC_API_BASE_URL=https://counton-api.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com
NEXT_PUBLIC_SUPABASE_URL=<existing-project-origin>
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<existing-publishable-key>
NEXT_PUBLIC_ALEXA_OAUTH_CLIENT_ID=<registered-confidential-client-ID>
NEXT_PUBLIC_ALEXA_REDIRECT_URIS=<comma-separated-exact-ASK-console-callback-URLs>
```

`COUNTON_MCP_URL=<public-HTTPS-MCP-endpoint>/mcp` is server-only Next.js discovery
configuration; actual orchestration calls originate in FastAPI via MCP_PUBLIC_URL.
Public Next.js variables require rebuilding/redeploying after changes. The consent
page has no-store, no-referrer and frame-ancestor protections, plus strict callback
validation. Login preserves only a valid consent return path, never a general
caller-selected redirect.

AWS credentials come only from the SDK provider chain. Prefer a supported workload
role/short-lived credential provider. Lightsail must be configured explicitly;
no implicit IAM role is assumed. Local SSO is for developer testing, not an unattended
production worker. Scope non-streaming Converse permissions to `bedrock:InvokeModel`
on the selected foundation model ARN (`arn:aws:bedrock:us-east-2::foundation-model/openai.gpt-oss-120b-1:0`)
or the actually configured inference profile and its required destination models.
See [AWS invocation/IAM requirements](https://docs.aws.amazon.com/bedrock/latest/userguide/inference.html).
Enable account/model/provider access and confirm denial of unrelated models. No
AWS keys or `SUPABASE_SECRET_KEY` are needed by the browser. Database runtime roles
must have required CountOn table access; use a separate migration role where practical.

## Native Supabase account linking

CountOn uses Supabase's existing [OAuth server](https://supabase.com/docs/guides/auth/oauth-server/getting-started),
not a new authorization/token implementation. See [native OAuth flows](https://supabase.com/docs/guides/auth/oauth-server/oauth-flows)
and [token/RLS security](https://supabase.com/docs/guides/auth/oauth-server/token-security).

1. Enable OAuth Server on the existing project. Set Site URL to the deployed CountOn
   frontend and Authorization Path `/oauth/consent`.
2. Register a **confidential** Alexa client with exact redirect URIs shown by ASK.
   Store client secret only in Supabase/ASK secure settings. No secret in frontend.
3. In ASK Account Linking: Authorization Code Grant, HTTP Basic client authentication,
   PKCE SHA-256 enabled, scopes `openid` plus only required `email`/`profile`.
   Auth URL: `https://<project-ref>.supabase.co/auth/v1/oauth/authorize`;
   token URL: `https://<project-ref>.supabase.co/auth/v1/oauth/token`.
   Use [Amazon's console requirements](https://developer.amazon.com/en-US/docs/alexa/account-linking/configure-authorization-code-grant.html).
4. Configure the public frontend client/callback IDs and backend allowlist/binding;
   deploy migrations first. The consent page verifies current Supabase identity,
   request owner/client/scopes/redirect, requires Allow/Deny, and re-verifies identity
   before approving. Supabase owns state, auth codes, PKCE, issuance and refresh.
5. Import the en-US interaction model. Verify List/Get/Capture/Why, Yes/No and
   Help/Cancel/Stop/Fallback intents, broad `text` slot and dialog elicitation.
6. Link a dedicated account. Verify the **access** JWT's issuer, UUID sub,
   `aud=authenticated`, `role=authenticated`, expiry and exact approved `client_id`.
   Never log or paste it. Test refresh and wrong-client/expired JWT rejection.
7. Test denial, cancelled login, revoked grant, disabled account, expiry and relink.
   Revocation prevents refresh; locally verified JWTs can remain valid until expiry.
   Set an appropriate short access-token TTL and test this window. Instant grant
   revocation is not claimed by offline JWT verification.

Console registration/model build, callback/domain/privacy policy configuration,
refresh/revocation behavior and real device recognition remain manual acceptance.
Do not replace a linked access token with an ID token, shared demo token, Amazon
apiAccessToken or service-role key.

## Startup, readiness and operations

Local: `docker compose up -d`, then from `backend`:

```sh
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt -r requirements-security.txt
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Separate backend terminals, same private config:

```sh
python -m app.mcp
python -m app.monitoring.worker
```

Frontend: `cd frontend`, `npm ci`, `npm run dev`. Set real shared local auth/MCP
settings as documented in component docs. Do not run background polling in API
reload startup. In production supervise/restart API, MCP and worker independently,
terminate TLS at the trusted platform/edge, bind only necessary ports, and gracefully
stop workers. HTTPS endpoints are API `/api/v1/alexa` and MCP `/mcp`.

`/health` checks process liveness; `/ready` checks required schema/table membership
and **exact Alembic head**, returning 503 on dependency/schema failures. It does not
certify optional Bedrock/Graph authorization. Safe X-Request-ID/route/status/duration
logs and counters omit payloads/headers/tokens. Uvicorn access records use a safe
formatter that never interpolates URLs/query strings (including OAuth codes).
SDK diagnostics are sanitized; third-party MCP/ASK verbose logs are suppressed. Private API `/metrics` exports
aggregate HTTP/Bedrock counters (calls, success/failure, latency sum and tokens).
Worker attempt/duration counters and stable run-key correlation are recorded locally;
collect worker logs or configure its metric sink separately from API scraping.
The default metric sink is process-local and resets at restart; scrape each API
replica and collect MCP/worker structured logs or install a shared metrics sink.

Alert on readiness failures, provider auth-needed/dead-letter jobs, failed captures,
Bedrock failures, latency and evidence freshness. Job lease/retry/outbox details and
read-only SQL inspection tools are in [monitoring operations](monitoring.md).

Local API/MCP rate limits are bounded per-process IP budgets (default 300 requests,
100 writes/60s). MCP GET/POST are limited before JWT network work. Proxy headers are
not trusted. **An edge/shared rate limit and load testing are required for multiple
replicas/NAT/proxy traffic**; durable sessions do not make these budgets distributed.
Request size limits include chunked bodies and pathological Content-Length; duplicate
Authorization headers fail. SDK transport and provider timeouts are bounded. Bedrock
budget checks stop retries/repairs and discard late results, but cannot kill an
in-flight synchronous SDK call. Configure read/connect bounds and measure actual
ASK latency within seven seconds; web's longer budget does not solve voice latency.

## Schema deployment and rollback

1. Back up database, verify restore and private key availability. Stop/drain worker
   polling and active conversations. Use staging first; review `alembic current`,
   `alembic heads`, then `alembic upgrade head` with the private migration role.
2. Required new revisions: `7f413b80ce12` (durable monitoring) and `8a524c91df23`
   (conversation encryption/leases and OAuth SQL restrictions). Run
   `python db/scripts/check_schema.py`; verify API/MCP `/ready` become 200.
3. Deploy matching API/MCP/worker config, then frontend. Restart polling after
   schema/health/auth checks. Do not auto-run migrations in every replica.
4. Local tests perform upgrade→downgrade→upgrade, ownership-backfill guard and real
   restrictive RLS behavior using an isolated database/test JWT function. This is
   not live Supabase policy acceptance. Test actual SQL/REST roles in staging.
5. Rollback requires backup and drain. To revert conversation code, disable/revoke
   Alexa OAuth clients first: `alembic downgrade 7f413b80ce12` deletes encrypted
   conversations and **removes OAuth SQL restrictions**. Never leave linked clients
   active after that security downgrade. Re-upgrading restores policy/schema but
   not deleted conversation records. Earlier monitoring downgrade drops durable
   job/provider fields and history semantics; restore backups if those data matter.

## Automated validation performed

Executed locally with Python 3.14 / Node 24, dedicated loopback PostgreSQL test
DB and disposable migration/worker databases. Credentials were loaded privately
without printing the DSN. Local unit/model tests never require AWS credentials.
CI uses Python 3.12 and PostgreSQL 16; CI itself has not run remotely (no push).

| Command | Actual result |
| --- | --- |
| `python -m pytest -q --tb=short` (private `TEST_DATABASE_URL`) | PASS: 1044 tests, no skips; 104 upstream ASK certificate/datetime deprecation warnings |
| `ruff check app db/scripts tests alembic` | PASS |
| `mypy app --ignore-missing-imports` | PASS: 125 source files |
| Strict intelligence/agent/ASK mypy command below | PASS: 37 files |
| `python db/scripts/production_smoke.py` (private test DB) | PASS: startup/six contracts, real loopback MCP/ownership, signed ASK fixtures, durable conversations and worker persistence |
| `npm run lint` | PASS |
| `npm run typecheck` | PASS |
| `npm run test -- --reporter=dot` | PASS: 123 tests; 1 credential-gated live test skipped |
| `npm run build` | PASS, includes `/oauth/consent` |
| `bandit -q -r app -ll` | PASS: no medium/high findings; low assertion/blank revocation-marker findings reviewed, no auth bypass suppression |
| `pip-audit --cache-dir /tmp/counton-audit-cache --progress-spinner off -f json -o /tmp/counton-pip-audit-final.json` | PASS: no known installed Python dependency vulnerabilities |
| `npm audit --omit=dev --json` | PASS: no production dependency vulnerabilities |
| `python3 scripts/secret_scan.py` | PASS: history and current non-ignored source, zero findings after two exact protocol/test-constant exclusions |
| `git diff --check` | PASS |

```sh
# From backend, same CI command:
mypy --strict --follow-imports=silent --ignore-missing-imports app/ai app/agent app/alexa app/mcp/compiler.py app/mcp/intelligence.py app/mcp/conversation_state.py app/mcp/schemas.py app/api/v1/agent.py app/api/v1/alexa.py app/schemas/compiler.py app/schemas/clarification.py app/schemas/investigation.py app/schemas/trust.py app/services/compiler_service.py app/services/investigation_service.py app/services/agent_audit.py db/scripts/bedrock_smoke.py
```

CI checks all backend tests, normal/strict typing, Ruff, Bandit, pip-audit, frontend
lint/types/tests/build/npm audit and history/source Gitleaks. Official actions and
scanner image are pinned. Scanner output prints filenames/rules only; default rules
remain enabled. Narrow AND exclusions cover public `Signature-256` and the fixed
offline HS256 fixture only. No credentials were found/removed and no tests weakened.

## End-to-end scenarios and blockers

| Scenario | Local verification | External acceptance |
| --- | --- | --- |
| A web compile→capture→evidence→worker→visible result | Real compiler/grounding with mock AWS, MCP service adapter, PostgreSQL evidence/evaluation/inbox; frontend/API contracts tested separately | Full deployed browser/provider path NOT RUN |
| B ASK clarify→confirm→web persistence | Multi-turn canonical engine, encrypted restart-safe stores, confirmation/No, injection, exact replay, same owned rows; signed ASK + actual loopback MCP verified | Native OAuth, console NLU and Echo NOT RUN |
| C mismatch notification once after retries | Real PostgreSQL lease/retry/crash/idempotency/dedup tests PASS | Deployed restart/load/real provider NOT RUN |
| D unauthorized/foreign MCP client denied | Real HTTP/JWT owned isolation and clean errors PASS | Live missing/invalid auth rejected; real owned list/get cross-checked; authenticated foreign-user cloud probe NOT RUN |
| E missing/stale/contradictory evidence→UNKNOWN | Real deterministic worker/evaluator quality tests PASS | Live provider timestamps/permissions/freshness NOT RUN |

| Severity | Outstanding blocker |
| --- | --- |
| P0 rollout | API/MCP readiness remains **503**. Configured Supabase is at `6e302a79bd01`, missing three new tables; live API/MCP/frontend are older than local capabilities. Exact deployed image/head and failing check require Lightsail access. No production migration/deploy performed. |
| P1 cloud inference | `BEDROCK_ENABLED` is false locally. A one-process enabled harmless probe failed with SDK **LoginRefreshRequired**, no AWS error code returned. Authenticate locally and configure a durable supported deployment credential provider/IAM/model access. |
| P1 acceptance | Dedicated environment test tokens/E2E browser credentials are absent. Existing development demo credentials enabled real read-only API/MCP initialize/list/get/shared-row verification; full browser/capture/provider/device acceptance remains unverified. |
| P1 account linking | Register/enable native OAuth server/client, deploy consent, verify access JWT/PKCE/refresh/revocation, import/build ASK model, run console then Echo tests. |
| P1 operational | Edge/shared rate limits, traffic/latency measurements, key/DB backup restore, logs/metrics collection, staging Supabase RLS and deployed migration/rollback acceptance remain required. |
| P1 evidence source | Microsoft Graph permissions, real OAuth refresh/revocation and receipt normalization require actual provider acceptance; mocked connector tests are not live proof. |
| P2 maintenance | Upstream ASK deprecation warnings; process-local metric/rate sinks; finite conversation capacity; explicit restatement after crash or postcompile correction. |

## Exact real-world acceptance procedure

1. Resolve readiness 503 and record deployed revision/image, DB head and `/ready`
   results; use staging/dedicated test accounts. Confirm TLS/CORS and required env
   presence without printing values. Do not bypass checks to make a probe pass.
2. Local AWS: this machine needs `aws login --profile default`; use `aws sso login` only for an actual IAM Identity Center profile. Trusted
   backend: `python db/scripts/bedrock_smoke.py --live` with BEDROCK_ENABLED=true.
   Require validated harmless JSON; then run existing intelligence smoke as described
   in [Bedrock integration](bedrock-integration.md#exact-production-checks).
3. Keep a valid dedicated access token in private `COUNTON_TEST_ACCESS_TOKEN`.
   Read-only MCP probe: `python db/scripts/mcp_remote_smoke.py --mcp-url https://<actual-host>/mcp`.
   This requires initialize→six tools/list→owned list. For capture/get/API cross-check,
   supply `--api-url https://<actual-api-host>` with a normal dedicated web-user token
   and review exact-tag cleanup. Restricted Alexa-client tokens cannot perform deletion.
4. Web scenario: sign in, create a clearly tagged electricity expectation via `/alexa`
   or create form; answer missing currency/baseline/timing honestly. Confirm normal
   expectation list after refresh. Ingest real tagged evidence through owned API/provider,
   schedule the job, run `python -m app.monitoring.worker --once`, and check recorded
   deterministic result/inbox. Repeat/restart; require exactly one evaluation/notification
   per run key. Missing/stale/conflicting variants must produce UNKNOWN.
5. Run dedicated browser acceptance using private COUNTON_E2E_EMAIL/PASSWORD,
   COUNTON_ALEXA_BASE_URL and COUNTON_E2E_API_BASE_URL:
   `cd frontend && node tests/alexa-live.mjs`. Verify cleanup succeeded; artifacts stay ignored.
6. ASK simulator then Echo: link the dedicated account; say “open count on”, list,
   “I'm counting on my bill being lower”, electricity, real baseline, USD if asked,
   “when my next bill arrives”, then **yes**. No row before confirmation; one row
   visible through normal web dashboard after refresh. Cancel a second draft.
   Select a genuine recorded mismatch and ask why; require supplied-evidence-only
   speech. MATCH/UNKNOWN must skip investigation. Test duplicates/disambiguation,
   expired grant/session, wrong-client token, malformed signature/timestamp and failures.
7. Retry exact signed requests in staging/restart API; require cached safe replies,
   no duplicate save, and foreign-user handle/expectation rejection. Do not forge
   platform requests or weaken signature validation on public deployment.
8. Connect the approved Graph test mailbox via PKCE; prove minimal permissions,
   refresh/revocation, normalized evidence provenance and freshness. Review inbox
   deduplication after worker restart. No Alexa proactive delivery claim.
9. Remove only exact tagged test records with a normal owned API token. Confirm their
   cascades and inspect cleanup failures. Record redacted acceptance evidence, latency,
   deployment IDs and dates; never archive tokens, email bodies or private prompts.

No commit, push, migration of production data, or deployment was performed in this pass.

## Release checklist

- [x] Core monitoring, typed intelligence and six compatible MCP contracts implemented.
- [x] Local auth/ownership/injection/replay/security boundaries pass automated tests.
- [x] Local migrations/rollback, worker retry/dedup and conservative UNKNOWN handling pass.
- [x] Frontend tests, lint, types, production build and local security scans pass.
- [x] CI workflow and credential-free deployment examples prepared.
- [ ] Resolve deployed API/MCP readiness 503; verify actual deployed revision/schema.
- [ ] Run remote CI on the committed change (not performed; no push).
- [ ] Deploy native OAuth consent/client config; verify issuance/refresh/revocation.
- [ ] Run authenticated remote MCP, full browser and actual provider acceptance.
- [ ] Verify real AWS credentials/IAM/model inference and ASK latency.
- [ ] Build ASK model, run console scenarios, then real Echo tests.
- [ ] Verify shared edge limits, monitoring alerts, keys/backup restore and cloud log redaction.

Release remains blocked until the external acceptance items are recorded.

## Files in this pass

The workspace already contained the earlier stabilization/monitoring changes.
This pass added/changed the following production integration files; it did not
replace the compiler/evaluator/MCP server or remove existing functionality.

| Area | Added or modified files |
| --- | --- |
| Configuration/auth | `backend/app/core/config.py`, `backend/app/core/auth.py`, `backend/app/core/logging.py`, `backend/app/api/dependencies.py`, `backend/production.env.sample`, `backend/requirements-security.txt` |
| Durable state | `backend/app/conversations/__init__.py`, `persistence.py`, `stores.py`; `backend/app/db/models/conversation.py`, `models/__init__.py`; migration `backend/alembic/versions/8a524c91df23_conversation_security.py` |
| Orchestration/ASK | `backend/app/agent/models.py`, `session.py`, `orchestrator.py`; `backend/app/alexa/adapter.py`, `interaction-model.en-US.json`; `backend/app/api/v1/alexa.py` |
| MCP/HTTP/telemetry | `backend/app/mcp/server.py`, `backend/app/api/budgets.py`, `metrics.py`, `backend/app/main.py`; `backend/app/ai/bedrock_client.py`, `expectation_compiler.py`, `telemetry.py`; `backend/app/monitoring/worker.py` |
| Frontend consent | `frontend/app/oauth/consent/page.tsx`, `frontend/lib/oauth-consent.ts`, `frontend/app/login/page.tsx`, `frontend/next.config.ts` |
| Tests/smoke | `backend/tests/test_production_conversations.py`, `test_production_security.py`, `test_alexa.py`, `test_operations.py`, `test_mcp_remote.py`; `backend/db/scripts/production_smoke.py`; `frontend/tests/oauth-consent.test.tsx` |
| CI/security | `.github/workflows/ci.yml`, `.gitleaks.toml`, `scripts/secret_scan.py` |
| Docs | This runbook, root `README.md`, `docs/traditional-alexa.md`, `docs/hackathon-acceptance.md`, `backend/app/agent/README.md`, `backend/app/ai/README.md`, `backend/db/README.md`, `frontend/README.md`, `frontend/docs/alexa-demo.md`, `frontend/docs/mcp-client.md` |

On `feature/alexa-mcp`; working tree contains both prior and current changes.
No commit/push/deployment was performed. No real secret was discovered by the
history/source scan; no credential value or cloud user data is included in this report.

Receipt subjects and approved sender addresses are constrained, but Outlook
metadata parsing does not prove cryptographic sender/invoice authenticity
(`sender_authenticated: false`). This is a documented provider trust limit, not
proof of a verified utility feed; validate the chosen evidence source before rollout.

## Follow-up change manifest

This deployment investigation changed only:

- `backend/app/services/readiness.py`
- `backend/app/core/logging.py`
- `backend/db/scripts/check_schema.py`
- Added `backend/db/scripts/aws_preflight.py`, `backend/db/scripts/deployment_probe.py`
- Added `backend/tests/test_deployment_readiness.py`, `backend/tests/test_aws_preflight.py`, `backend/tests/test_deployment_probe.py`
- `docs/production-readiness.md`, `docs/bedrock-integration.md`
- `backend/db/README.md`, `backend/app/ai/README.md`
- Ignored private `backend/.env.local` (explicit TLS only; credentials preserved)

Other dirty files belong to prior work and were retained. Final working tree on
`feature/alexa-mcp`: 124 modified tracked files and 37 untracked entries (directory
entries are not a file count). No commit/push or production write was performed.
