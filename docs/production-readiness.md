# CountOn release acceptance — October 12, 2026

**NOT PRODUCTION-READY.** The local application is connected and testable, but the
public deployment is older than this working tree, readiness fails, real provider/ASK
acceptance is unavailable, and the updated working tree has not run in hosted CI.
No production deployment, migration, commit, push, account consent, or real notification
send was performed. All previous workspace changes were retained.

This is a historical release record for `feature/alexa-mcp`, based on HEAD `e7c74ac`
plus uncommitted changes. HEAD alone does not identify the tested source. See the
[full pending-file manifest](release-change-manifest.md). Earlier counts and deployment
instructions are archived in [historical readiness](production-readiness-history.md).

The subsequent [CI investigation and validation](ci-validation.md) supersedes this
pass's local test counts and dependency-audit finding: 1,207 backend / 168 frontend
tests now pass in clean Linux containers, and both npm audits pass with a tested
local lint dependency security patch. The tables below retain the earlier release
pass's actual results. The pending-file manifest predates the CI changes.

The later [resumed-orchestration validation](orchestration-validation.md) records the
latest working-tree test results, source authorization/correlation fixes and evaluation
gates. It supersedes earlier local counts below. The live observations below are from
the earlier probe; this resume did not deploy or reaccept the public release.

> Current local validation, dependency fixes, migration head and the mandatory live
> database gate are recorded in [the final engineering audit](final-engineering-audit.md).
> All live observations and dependency/test counts below are dated October 12,
> not a statement of current deployment state.

## Architecture and authority

```text
Web /alexa -> Supabase session -> Next.js /api/agent -> FastAPI /api/v1/agent/converse
ASK/Echo -> signed POST /api/v1/alexa -> linked Supabase OAuth JWT
    -> shared bounded orchestrator + encrypted PostgreSQL conversation state
    -> real MCP Streamable HTTP, bearer protected, nested {"request": {...}}
    -> compile / continue / confirmed capture / get / list / explain
    -> existing CountOn services -> same PostgreSQL/Supabase database

Verified provider push (wake hint) or periodic reconciliation
    -> authorized Gmail/Graph/Calendar fetch -> bounded normalized source projection
    -> explicit owned account/source binding -> durable monitoring job wake
    -> deterministic evaluation -> history + evidence references + one inbox exception
    -> optional opt-in email outbox -> idempotent delivery API
Web dashboard -> authenticated FastAPI -> same records/history/notification inbox
Alexa/MCP reads -> same persisted expectation status
```

Bedrock interprets bounded language and explains recorded mismatches; it never decides
MATCH/MISMATCH/UNKNOWN. Missing, stale, contradictory, ungrounded or revoked-source
observations yield UNKNOWN. Reply absence requires continuous authorized mailbox
coverage beginning before expectation creation. Predicted shipping changes are warnings,
not confirmed missed delivery. See [automatic tracking](automatic-tracking.md).

## Final subsystem acceptance matrix

Each row uses one of the requested statuses. “Locally verified” includes actual local
PostgreSQL/HTTP where stated and mocked inference/provider responses; it never means
cloud/device acceptance.

| Subsystem | Status | Evidence and limit |
| --- | --- | --- |
| Bedrock | Implemented and locally verified | Typed compiler, stateful clarification, grounding, investigator, budgets/fallbacks pass offline tests. Harmless real invocation fails before service access with `LoginRefreshRequired`. |
| SQL | Implemented and locally verified | Alembic head `ac746eb3f145`, metadata equality, RLS/ownership, guarded rollback and actual local archive restore. Configured Supabase remains at `6e302a79bd01`. |
| Supabase OAuth | Partially implemented | Live normal Supabase login/JWT API/MCP reads work. Native OAuth consent/client binding is implemented/tested locally; live discovery and consent return 404, issuance/refresh/revocation not accepted. |
| Alexa | Partially implemented | ASK signature/timestamp/application/session/replay checks, clarification, confirmation, durable recovery, status and grounded speech pass locally. ASK console/Echo unavailable; saved-row editing/cancellation is web-only. |
| MCP | Implemented and locally verified | Six registered schemas and real loopback Streamable HTTP, authenticated calls, cross-user denial. Remote initialize/list/get/shared row pass, but remote discovery has only the three core tools. Native resource discovery is not implemented on MCP. |
| Gmail | Implemented and locally verified | OAuth/refresh/scopes, normalization, covered reply deadlines, verified push/reconciliation/worker tests. No real account consent or email delivery acceptance. |
| Outlook | Implemented and locally verified | Graph OAuth/refresh/Inbox synchronization, official-response normalization and connected capture-to-notification test. No real tenant/mailbox acceptance. |
| Google Calendar | Implemented and locally verified | Authorized delta/reconciliation, exact instance matching, cancellation, chronology and freshness tests. No real calendar acceptance. |
| Microsoft Calendar | Implemented and locally verified | Verified callback -> Graph sync -> reschedule/cancellation -> deterministic history/inbox tests. No real calendar acceptance. |
| Amazon evidence | Implemented and locally verified | Authorized email-derived order/estimate/delivery-report path; predicted certainty preserved. No unrestricted consumer API, carrier-independent confirmation or live order acceptance claimed. |
| Background monitoring | Implemented and locally verified | Real PostgreSQL leases/fencing, retries/recovery, source wake-ups, ownership and A–G offline scenarios. No deployed worker activity/log/latency proof. |
| Automatic notifications | Implemented and locally verified | Real deduplicated inbox, acknowledgement/history/preferences; mocked email retry/idempotency/quiet-hour recovery. No actual recipient delivery; proactive Alexa voice is not implemented. |
| Web frontend | Implemented and locally verified | Auth/API/MCP/agent contracts and UI tests; fresh-build verification below. Deployed homepage/login/Alexa respond, but consent/new monitoring release is not accepted live. |
| Production deployment | Blocked by external credentials/approval | Both readiness endpoints 503, schema/image drift, expired AWS login, missing consent config, failing remote CI, absent dedicated provider/device acceptance. |

## Actual live checks

The existing read-only `deployment_probe.py --remote --demo-login` used the configured
normal development/demo Supabase login. Token and owned data stayed in memory; nothing
was captured, compiled, evaluated, deleted, or emailed remotely. This is narrower than a
dedicated two-user/device/provider release acceptance.

| Executed probe | Observed result |
| --- | --- |
| API and MCP `/health` | 200 |
| API and MCP `/ready` | **503** |
| Missing API auth; missing/invalid MCP auth | 401 |
| Approved Vercel CORS / untrusted origin | Exact origin granted / 400 without grant |
| Real Supabase login, authenticated API list | 200 |
| Actual MCP initialize; core list/get; API shared existing row | PASS, no row identity/claim printed |
| Remote six-tool discovery | FAIL: compile, continue and explain absent |
| Remote agent, Alexa and expectation monitoring routes | Absent from deployed OpenAPI |
| Configured Supabase read-only schema check | `6e302a79bd01`; local expected `ac746eb3f145`; nine required tables absent |
| Vercel `/`, `/login`, `/alexa`, `/oauth/consent` | 307 / 200 / 200 / **404** |
| Supabase OAuth server discovery | **404**; no native OAuth flow accepted |
| MCP OAuth resource/authorization discovery | **404**; bearer-only boundary, no native discovery/consent implementation |
| Vercel production env inventory | Four API/Supabase/MCP variables exist; two Alexa OAuth variables absent; values suppressed |
| AWS STS preflight / enabled harmless Bedrock probe | Exit 1, `LoginRefreshRequired`; no AWS service error code, identity, credential or raw response printed |
| Public GitHub Actions inventory | Workflow exists. Latest run on `feature/alexa-mcp`, revision `e7c74ac5db21`, completed/failure Oct 11, 21:16:17 UTC |
| Latest remote CI failed steps | Backend: Initialize containers. Frontend: npm run build. Secrets job succeeded. Full logs require authorization (403); public Docker annotation and independently reproduced failures/fixes are recorded in [CI validation](ci-validation.md). |
| Cloud logs/metrics, edge limits, deployed workers, production latency | BLOCKED by AWS access/metrics credentials; not inferred from /health |
| Actual ASK console / physical Echo / real Google-MS-Resend accounts | NOT RUN; dedicated credentials, consent and device access absent |
| Production backup restore / deployed rollback | NOT RUN; local restore is distinct from production backup/key/role restoration |

Local Google/MS integration, synchronization, monitoring, Bedrock and email flags are
false; provider secrets, encryption key, Alexa skill/client IDs and email key are absent.
Dedicated process `COUNTON_TEST_ACCESS_TOKEN` and browser E2E email/password are absent.
No local configuration was enabled permanently or secrets added.

## Changes made in this acceptance pass

- Alexa owned detail speech now includes the actual persisted lifecycle status, so
  users hear monitoring/fulfilled/contradicted/unknown/resolved/cancelled. It is scoped
  to GET only; mismatch speech and capture confirmation stay unchanged.
- The manual web create form links to existing conversational `/alexa` setup and
  describes available source/deadline/tracking configuration accurately. It retains
  review/explicit save and does not infer missing values or write to Supabase directly.
- Inter and Space Grotesk are self-hosted with original OFL licenses and fixed upstream
  provenance. `next/font/local` retains font families, weight ranges, variables and
  swap display. Fresh builds no longer depend on Google Fonts fetches.
- New release journey tests use real signed fixture JWTs, MCP Streamable HTTP,
  canonical compiler/clarification and durable restarted voice stores, actual services
  and PostgreSQL. Provider/inference responses alone are mocked. They prove no save
  before confirmation, exactly one replay-safe capture, Google/MS source ingestion,
  deterministic MISMATCH/inbox, grounded fallback, shared web/voice state, web editing
  and cancellation, repeat suppression, and foreign API/MCP denial.
- New guarded backup/restore smoke uses only a separate loopback `*_test` DB. It
  archives/restores to a generated database, verifies schema and linked history, and
  removes only its own fixture/database. Credentials never appear in argv/output;
  temporary archives are private and removed. Unsafe-target guard tests were added.
- Offline production smoke now has a fifth connected-provider/recovery group.
- CI additionally audits frontend development/build dependencies at high severity;
  the known advisory is surfaced rather than ignored or hidden by a runtime-only scan.
  Its build step supplies the required API origin using `https://api.counton.invalid`
  for a validation artifact only. The prior env-less build failed closed as designed;
  this does not configure or deploy Vercel.
- Current acceptance replaces mixed historical readiness instructions; history and
  all pre-existing implementation work are retained.

No compiler/evaluator/database schema/MCP tool contract was replaced in this pass.
No dependency downgrade or forced audit fix was applied.

## Local validation and reproduction

Use the supported backend `.venv` and frontend lockfile. This machine has Python 3.14.6
and PostgreSQL 17 clients/server; CI/Docker select Python 3.12 and CI PostgreSQL 16.
Local success does not establish a successful Linux CI run.

Privately set `TEST_DATABASE_URL` to a distinct loopback database ending `_test`.
The local temporary wrapper selects `counton_test` from ignored local DB configuration
and redacts credentials; standard equivalent commands are:

```sh
# backend, after activating .venv; never use production for tests
python -m pytest -q --tb=short
ruff check app db/scripts tests alembic ../scripts
mypy app --ignore-missing-imports
mypy --strict --follow-imports=silent --ignore-missing-imports app/ai app/agent app/alexa app/mcp/compiler.py app/mcp/intelligence.py app/mcp/conversation_state.py app/mcp/schemas.py app/api/v1/agent.py app/api/v1/alexa.py app/schemas/compiler.py app/schemas/clarification.py app/schemas/investigation.py app/schemas/trust.py app/services/compiler_service.py app/services/investigation_service.py app/services/agent_audit.py db/scripts/bedrock_smoke.py
bandit -q -r app -ll
pip check
pip-audit --progress-spinner off
python db/scripts/production_smoke.py
# Run against a quiescent isolated test DB with pg_dump/pg_restore and CREATEDB:
python db/scripts/backup_restore_smoke.py --local-test

# frontend
npm ci
npm run lint
npm run typecheck
npm run test
npm run build
npm audit --omit=dev
npm audit --audit-level=high

# root
python3 scripts/secret_scan.py
git diff --check
```

### Executed final validation

All results below were observed on October 12, 2026. Temporary wrappers only select
the separate local test DB from ignored configuration and redact credentials; they
do not alter application code or weaken test guards.

| Working directory / exact command | Result |
| --- | --- |
| backend: `.venv/bin/python /tmp/counton_test_suite.py -q --tb=short` (runs pytest) | PASS — **1,166 passed**, 104 upstream ASK deprecation warnings, 41.87s; no skips |
| backend: `.venv/bin/ruff check app db/scripts tests alembic ../scripts` | PASS |
| backend: `.venv/bin/mypy app --ignore-missing-imports` | PASS — 140 source files |
| backend: strict mypy command listed above, using `.venv/bin/mypy` | PASS — 37 source files |
| backend: `.venv/bin/bandit -q -r app -ll` | PASS |
| backend: `.venv/bin/python -m pip check` | PASS — no broken requirements |
| backend: `.venv/bin/pip-audit --progress-spinner off` | PASS — no known vulnerabilities |
| backend: `.venv/bin/python /tmp/counton_operations_smoke.py` (runs production_smoke.py) | PASS — all five groups; external cloud/device acceptance NOT RUN |
| backend: `.venv/bin/python /tmp/counton_backup_smoke.py` (runs backup_restore_smoke.py --local-test) | PASS — actual local archive restore and exact fixture/database cleanup |
| backend: `.venv/bin/alembic upgrade 6e302a79bd01:head --sql > /tmp/counton-release-upgrade.sql` | PASS — 392-line offline SQL preview; not applied anywhere |
| frontend: `npm run lint` | PASS |
| frontend: `npm run typecheck` | PASS |
| frontend: `npm run test` | PASS — **142 passed**, one pre-existing credential-gated live MCP skip, 13 files |
| frontend: `npm run build` | PASS — all routes including /alexa, /api/agent, /api/mcp and /oauth/consent built |
| clean `/tmp/counton-release-clean-frontend`: `npm ci --cache /tmp/counton-release-npm-cache` | PASS — actual fresh lockfile install, 466 packages |
| clean copy, no `.env*`: `NEXT_PUBLIC_API_BASE_URL=https://api.counton.invalid npm run build` | PASS — self-hosted fonts, no live dependency credentials or Google Fonts fetch required |
| frontend: `npm audit --omit=dev` | PASS — zero vulnerabilities |
| frontend: `npm audit --audit-level=high` | **FAIL, exit 1** — five high entries; see advisory below |
| root: `python3 scripts/secret_scan.py` | PASS — Gitleaks git and directory scans report no leaks |
| root: `git check-ignore backend/.env.local frontend/.env.local backend/.env frontend/.env` | PASS — all four paths ignored; tracked sample templates retained |
| root: `git diff --check` | PASS |

Final focused recheck: `.venv/bin/ruff check db/scripts/backup_restore_smoke.py
db/scripts/production_smoke.py tests/test_backup_restore_smoke.py
tests/test_release_journey.py app/alexa/adapter.py tests/test_alexa.py` passed;
`.venv/bin/python -m pytest -q tests/test_backup_restore_smoke.py` passed all eight
guard cases. Docker/PostgreSQL checks required local sandbox access. The final
secret-scan attempt without Docker access reported infrastructure unavailable;
rerunning the same command with permitted Docker access passed both scans with
zero findings. No scan finding was suppressed.

Alembic upgrade/downgrade, metadata equality, RLS and revision guards also run inside
the full backend suite against isolated databases. No production schema rollback
was attempted. A fresh build without the required API origin intentionally failed;
supplying the CI validation origin resolved that configuration failure without a
localhost production fallback.

The user's 1,009 backend / 123 frontend comparison is an older baseline; this pass
started at 1,150 backend / 140 frontend plus one existing live skip. The final increase
is 16 backend and two frontend tests. No tests were deleted, weakened or newly skipped.

### Security scanner finding

During the earlier release pass: runtime npm audit had zero vulnerabilities; full npm audit had **five high-severity entries**
for the dev-only Next ESLint -> fast-glob -> micromatch -> braces dependency chain,
root advisory [GHSA-vfj7-8cjw-p6xm](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm).
The advisory lists no patched version; registry `braces` latest is 3.0.3. Suggested
force-fix downgrades eslint-config-next to 14.2.35, which is not a compatible patch for
this Next 16 application. The subsequent CI pass installs an explicitly documented,
MIT-licensed private fork with parser/AST depth guards using npm's supported override
reference. Dedicated tests verify the installed dependency, malicious nesting/cycles
and normal upstream behavior. Full and runtime audits now pass. No advisory or lint
rule is disabled. [CI validation](ci-validation.md) records the patch, its limitations
and removal procedure when an upstream fix becomes available.

## Environment and deployment requirements

Runtime credentials stay only on trusted backend services; retain `.env.local` ignore
rules and tracked sample guides. Do not print env contents, tokens or raw cloud logs.

| Service | Required configuration |
| --- | --- |
| All trusted Python services | `ENVIRONMENT=production`, `DATABASE_TARGET=supabase`, private TLS `SUPABASE_DATABASE_URL`, same `SUPABASE_URL` / publishable key and encryption/signing keys |
| API + MCP | `MCP_PUBLIC_URL=https://counton-mcp.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com/mcp`; production MCP origin/host configuration; shared `COUNTON_CLARIFICATION_SIGNING_KEY` |
| API | `ALLOWED_ORIGINS=["https://counton-frontend.vercel.app"]`, encrypted PostgreSQL conversation store/key, Alexa skill and registered client IDs, exact OAuth client allowlist |
| Bedrock MCP backend | `BEDROCK_ENABLED=true`, `AWS_REGION=us-east-2`, `BEDROCK_MODEL_ID=openai.gpt-oss-120b-1:0`; securely supported runtime AWS provider with least-privilege `bedrock:InvokeModel`; bounded existing settings |
| Provider API + sync worker | `PROVIDER_SYNC_ENABLED=true`, enabled provider flags, real client IDs/secrets/exact callbacks, same `INTEGRATION_TOKEN_ENCRYPTION_KEY`; optional verified push identities/topic/webhook settings from `backend/providers.env.sample` |
| Monitoring worker | `MONITORING_ENABLED=true`; same DB, source encryption and configured bounded leases/poll/retry settings from `backend/monitoring.env.sample` |
| Optional email worker | `NOTIFICATION_EMAIL_ENABLED=true`, private sending-only key, verified-domain from address, HTTPS `FRONTEND_PUBLIC_URL`; same integration key; user confirmed-address opt-in required |
| Vercel public build variables | `NEXT_PUBLIC_API_BASE_URL=https://counton-api.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` |
| Vercel server variable | `COUNTON_MCP_URL=https://counton-mcp.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com/mcp` |
| Vercel native Alexa consent | `NEXT_PUBLIC_ALEXA_OAUTH_CLIENT_ID`, `NEXT_PUBLIC_ALEXA_REDIRECT_URIS` with actual registered client and exact ASK HTTPS callbacks, then rebuild/deploy |
| Operations | Private metrics token, supervised worker restart/health checks, backup/key recovery, shared edge budgets; process-local limits/metrics alone are insufficient for multiple replicas |

Use sample files as guides, not a competing settings loader. Provider OAuth is distinct
from Supabase user authentication. Never put AWS/client secrets/database URLs in public
frontend variables or give frontend a service-role key. Native OAuth JWTs must retain
this verifier's `aud=authenticated`, same issuer, valid role/subject/expiry and approved
`client_id`; do not change audience hooks merely to bypass validation.

### Rollout gates — instructions only, not executed

1. Refresh developer AWS login (`aws login --profile default`) interactively, rerun
   `python db/scripts/aws_preflight.py --verify-identity` and harmless enabled Bedrock
   smoke. Do not copy local login caches to Lightsail; verify a supported runtime
   credential provider separately.
2. Privately inventory actual API/MCP images, env names, database target, worker
   service/commands and logs using safe readiness codes/correlation IDs. The configured
   local Supabase connection has not been proven to be the deployed containers' DB.
3. Archive a reviewed immutable source/image manifest. Run CI on that exact source;
   fix the remote initialization/build failures and the full dependency audit gate.
4. Obtain a verified database/key backup and restore it in approved isolated staging
   with outbound workers/email disabled. Verify head, ownership/RLS/roles, encrypted
   conversation/provider data and row/history counts. Local synthetic restore does
   not substitute for this.
5. Prepare/review Alembic SQL from the **actual** deployed head to `ac746eb3f145`.
   After explicit production authorization, drain old workers, apply `alembic upgrade
   head` from the matching release, check schema, deploy matching API/MCP and frontend,
   and supervise the existing provider, monitoring and optional email workers. Never
   stamp a head to conceal missing schema or bypass /ready.
6. Require both /ready endpoints to return 200, six-tool remote discovery, owned API
   cross-checks, OAuth consent/refresh/revocation and all real acceptance below.

Exact local/worker commands and retry/dead-letter recovery are in
[automatic tracking](automatic-tracking.md#setup-and-operation), provider push/scope
configuration in [integrations acceptance](integrations-acceptance.md), and Bedrock
[IAM/invocation checks](bedrock-integration.md#exact-production-checks).

Rollback must be staged and separately approved. Retaining an expanded schema while
rolling images back is safe only if that image's exact readiness and contracts accept
it. For `alembic downgrade 9b635da2e034`, the latest migration refuses evaluation-free
warnings until explicitly exported/archived. Other downgrades remove durable state,
credentials/permissions support and histories; re-upgrade cannot restore deleted rows.
Restore roles/RLS and encryption keys with the tested backup; do not run active workers
or linked OAuth clients against a schema missing their protections.

## Exact real-world acceptance procedure

1. Use two dedicated consenting accounts and tagged fixtures. Confirm release gates,
   both /ready=200, six tools, native OAuth discovery/consent and exact callbacks first.
2. Web: log in; use `/alexa` for existing Bedrock conversation or the manual form's
   preview/save; answer real subject/baseline/currency/timing questions. Confirm the
   same row via refresh, MCP get and owned API. The manual form never claims AI parsing.
3. ASK console: import/build `backend/app/alexa/interaction-model.en-US.json`, en-US
   invocation **count on**; set HTTPS endpoint to the actual API `/api/v1/alexa`.
   Configure native Supabase authorization-code account linking, registered client
   authentication/exact ASK redirects; keep client secret only in ASK/Supabase.
   Verify actual issuance, PKCE/client compatibility, audience, refresh, expiry and
   revocation; enable Development testing and link the dedicated Amazon account.
   Follow [Amazon linking steps](https://developer.amazon.com/docs/alexaplus/account-linking/steps-to-implement-account-linking.html)
   and [Supabase native OAuth setup](https://supabase.com/docs/guides/auth/oauth-server/getting-started).
4. Say “open count on”; list; “I'm counting on my electricity bill being lower than
   my last bill”; supply actual baseline/currency/timing; say **yes**. No row before
   confirmation, one afterward. Retry/restart safely; cancelled drafts never save.
   On an Echo signed into that linked development account, repeat the console sequence.
5. Connect dedicated Gmail and Outlook accounts using read-only consent. Bind exact
   account/thread/sender/recipient/message IDs to saved expectations. While offline,
   send a controlled permitted bill/reply; verify automatic evidence, evaluation and
   one inbox alert. For absent reply tests, establish continuous sync before capture
   and cover the deadline. Cursor loss/deleted/moved mail must abstain appropriately.
6. Connect Google and Microsoft calendars. Bind a test instance, reschedule/cancel it,
   verify verified push/poll -> sync -> current source fact -> evaluation/inbox. Repeat
   callbacks and restart workers; no repeated mismatch-episode notifications.
7. With a legitimate permitted order email, revise explicit arrival date after the
   deadline. Require predicted warning and UNKNOWN actual outcome until a supported
   occurrence timestamp arrives. Do not fabricate Amazon orders or claim a consumer API.
8. Ask Alexa about the expectation and why. Spoken lifecycle must match web/MCP/SQL.
   Why on MATCH/UNKNOWN skips the investigator; MISMATCH explanation cites supplied
   facts only. No invoice sender authenticity or causality claim beyond the evidence.
9. Edit conditions/cancel the saved expectation from web; reread via Alexa/MCP. Saved
   editing/cancellation through voice is **not implemented**: Cancel/Stop terminates
   a draft/conversation, not a persisted row. Do not interpret it as account-wide deletion.
10. Disconnect/revoke source and expire token/session. Require UNKNOWN/impaired tracking
    and safe relinking; test foreign user/token/client/handle, injection, malformed signed
    body, stale timestamp and replay denial without relaxing platform verification.
11. Opt into email for the confirmed dedicated address only; verify provider acceptance
    and receipt, DST quiet hours, opt-out, repeated processing and ambiguous-send recovery.
    Actual Alexa proactive delivery remains outside the implemented channel set.
12. Use `node tests/alexa-live.mjs` from frontend only with explicit dedicated URLs and
    private `COUNTON_E2E_EMAIL`/`COUNTON_E2E_PASSWORD`. Its save/delete work is a separate
    opt-in live write test; it was not run here. Clean only exact tagged fixtures with a
    normal owned web token, not a restricted Alexa OAuth token.
13. Capture redacted dates/revisions/latency/results, verify deployed worker/log/metrics
    and shared edge rate/size enforcement, then require all release gates green.

## Remaining blockers

| Severity | Blocker / next action |
| --- | --- |
| P0 | Deployed readiness/schema/image drift. Obtain trusted Lightsail inventory, staged backup and explicit rollout approval; deploy matching schema and all services. |
| P1 | Real AWS invocation/IAM and voice latency unverified; refresh expired login and configure supported runtime credentials. |
| P1 | Native OAuth discovery/consent absent and Alexa Vercel variables missing; register/configure, deploy and validate refresh/revocation/ASK/Echo. |
| P1 | Provider/mail/calendar/order/email acceptance absent; scoped credentials, verified callbacks/push authorities, consenting test accounts and sender are required. |
| P1 | This dirty release has not run remotely. Clean Linux CI commands pass after focused fixes; full hosted logs remain unavailable. Observe a successful hosted run after review/publication. |
| P1 | Deployed worker recovery, logs/metrics, edge limits, production latency, key-aware backup restore and rollback remain unverified. |
| P2 / feature limit | Saved-row Alexa editing/cancellation, proactive Alexa delivery, universal mailbox absence, carrier-independent order API, RRULE expansion and email bounce tracking are not implemented. |
| P2 / maintenance | Upstream ASK deprecation warnings and unsupported ESLint 9 notice; process-local observability/rate limits and finite conversation capacity need deployment review. |

## Release checklist

- [x] Preserve six tools, deterministic evaluator, canonical intelligence and auth.
- [x] Demonstrate local confirmed capture -> authorized source -> worker -> one inbox -> shared status.
- [x] Execute real isolated archive restore and exact tagged cleanup.
- [x] Complete final regression command record, including the failing full audit gate.
- [ ] Resolve full dependency audit and pass remote CI for this exact source.
- [ ] Match deployed schema/images/config and achieve both /ready=200.
- [ ] Accept actual OAuth/provider/Bedrock/browser/ASK/Echo/email flows.
- [ ] Verify production operations, edge limits, backup/key/RLS restore and rollback.

<a id="deployment-investigation-follow-up-2026-10-11"></a>
Earlier linked deployment evidence is retained in the [dated historical snapshot](production-readiness-history.md#deployment-investigation-follow-up-2026-10-11).
