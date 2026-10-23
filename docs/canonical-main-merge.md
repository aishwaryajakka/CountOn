# Canonical → main merge validation

This report records the local merge resolution, not a production acceptance certificate.
Source: `integration/counton-canonical` at `cc1e58758db0e7e208121d58d81a2b93d845aeee`.
Target parent: current fetched `origin/main` at `1af8aefd8fb3a1c122fd4f118654503737979c13`.
The final merge hash is supplied in the execution receipt; inspect it with
`git log -1 --format='%H %P %s' main`. No push/deployment/production migration is authorized or performed.

## Safety and history

Initial canonical checkout was clean and already committed. Original local main
`a04ad68768c7cec89ed79cddbd242c99fbea88c4` was 47 commits behind remote, with no
local-only commits. It fast-forwarded before the merge. Fetched main again before
final validation; the remote target remained unchanged.

Local safety refs:

- `backup/canonical-before-main-merge` → `cc1e587`
- `backup/main-before-canonical-merge` → `a04ad68`
- `backup/origin-main-before-canonical-merge` → `1af8aef`
- Existing `backup/pre-consolidation-2026-10-23` → `8d4b72f` retained.

Commands executed: `git fetch origin`, `git checkout main`,
`git pull --ff-only origin main`, then
`git merge --no-ff --no-commit integration/counton-canonical`.
No blanket ours/theirs checkout, reset or history rewrite was used.

## Individual conflict decisions

All 23 conflicted paths were inspected individually. The following explains each
resolution; complementary main capabilities are listed below rather than restoring
the older duplicate architecture.

| Conflicted file | Resolution and preserved behavior |
| --- | --- |
| `backend/.gitignore` | Root canonical ignore supersedes nested ignore and protects all credentials/build artifacts. |
| `backend/alembic/env.py` | One canonical settings/metadata graph; reject legacy credential model registration. |
| `backend/app/api/operations.py` | Retain canonical logging, exact CORS and budgets, avoiding duplicated middleware. |
| `backend/app/api/v1/integrations.py` | Retain canonical owned CRUD; separately port compatible manual-event/calendar/read/sync surfaces through canonical authority. |
| `backend/app/api/v1/notifications.py` | Retain owned preferences/inbox serialization; dashboard API uses this response model. |
| `backend/app/api/v1/router.py` | One route registration, canonical six-tool/ASK/provider/agent stack; add reviewed main routes separately. |
| `backend/app/core/config.py` | Canonical validated settings, no duplicate fields/session authority; port SMTP options separately. |
| `backend/app/db/models/__init__.py` | Canonical metadata only, not alternate OAuth/calendar/delivery schemas. |
| `backend/app/db/models/integration.py` | Current encrypted credential/lifecycle model; sync health is canonical ProviderSyncState. |
| `backend/app/db/models/operations.py` | Current owned mandatory monitoring, fenced leases and single outbox contract. |
| `backend/app/integrations/bee/__init__.py` | Retain simulated/context boundary; add manual numeric compatibility adapter with explicit simulated provenance. |
| `backend/app/integrations/ring/__init__.py` | Retain simulation boundary; port manual event compatibility adapter without claiming live Ring. |
| `backend/app/main.py` | Canonical single app/lifespan with durable conversations and separately supervised workers, no insecure duplicate startup loops. |
| `backend/app/repositories/integration.py` | Canonical owned queries and lifecycle invalidation. |
| `backend/app/repositories/notification.py` | Current deduplicated owner/evaluation/expectation constraints. |
| `backend/app/schemas/integration.py` | Canonical public safe credential-state response, no token fields. |
| `backend/app/services/evidence_service.py` | Current minimized provenance, replay conflict checking, audits and monitoring wake. |
| `backend/app/services/monitoring_service.py` | Canonical durable leases/scheduling/source permissions replace unsafe in-API polling. |
| `backend/app/services/notification_service.py` | Canonical inbox/preferences/episode dedupe; preserve SMTP through same outbox separately. |
| `backend/requirements.txt` | Current security-patched SDK/crypto constraints, both MCP HTTPX2 and provider HTTPX. |
| `backend/tests/test_operational_data.py` | Retain stronger canonical persisted history/ownership expectations. |
| `frontend/components/integration.tsx` | Retain complete canonical source/consent/CLI/status controls; main OAuth helper calls map to current provider UI. |
| `frontend/lib/api.ts` | Canonical authenticated client, safe public HTTPS config and real simulator APIs; preserve dashboard helpers separately. |

## Main functionality retained through canonical services

- Owned dashboard summary and unresolved-mismatch reads remain at
  `GET /api/v1/dashboard/summary` and `/dashboard/unresolved-mismatches`.
- `GET /api/v1/calendar/connections/{connection_id}/events` returns bounded
  projections from the selected owned canonical calendar stream, without another
  calendar table, token store or raw-event sync loop.
- Compatibility OAuth starts under `/api/v1/oauth/` preserve Google calendar/Gmail
  and Microsoft email/calendar entry points. They require the current Supabase bearer,
  validate an optional owned `connection_id`, reject ambiguous selection, and delegate
  state/PKCE/credentials to `integrations/accounts.py`. Google callbacks delegate
  single-use state validation. Microsoft callbacks use POST `form_post`, matching the
  canonical security contract, rather than exposing authorization codes through GET.
- Canonical provider callback URLs remain
  `/api/v1/integrations/oauth/google/callback` (GET) and
  `/api/v1/oauth/microsoft/callback` (POST). Configured `GOOGLE_REDIRECT_URI` and
  `MICROSOFT_REDIRECT_URI` must match registered URLs. No provider registration was
  changed. Old per-service redirect/secret environment names are not a second config
  authority. Deployments using those names need deliberate canonical configuration.
- Compatibility Outlook/calendar sync endpoints queue an existing owned selected
  stream. Their response explicitly says `queued: true`; zero processed counters
  mean work is deferred, never a claimed provider import. Gmail message reads return
  existing minimal projections, not arbitrary inbox contents. Requests without an
  authorized selection fail instead of auto-enrolling data or granting scopes.
- Authenticated manual `/api/v1/integrations/{expectation_id}/events/{ring|bee|email}`
  adapters check expectation ownership and explicit source opt-in, then reuse canonical
  evidence persistence and deterministic evaluation. Stable event IDs retain replay
  suppression. Ring/Bee are forcibly simulated, not hardware verification. Numeric
  Bee manual input is an explicitly supplied simulated measurement; it never upgrades
  a recorded promise to a fulfilled appointment. Email manual facts are user-submitted,
  not verified provider imports; real provider imports still use confirmed bindings.
- Main's bounded retry helper and verified Supabase admin-email lookup remain available
  for compatibility; neither creates another worker or authentication authority.
- Optional SMTP uses the canonical confirmed-recipient encrypted outbox; Resend remains
  default. Runtime credentials never enter source. SMTP requires TLS and a 10-second
  timeout. Because SMTP has no remote deduplication key, errors/uncertain restart sends
  fail safely without automatic retry (`DELIVERY_UNCERTAIN` on recovery). Resend's
  idempotent bounded retries remain unchanged. See `backend/notifications.env.sample`.
- Main's `/quality` route is retained and protected. Previously it called absent
  review/benchmark/recommendation APIs; it now displays actual owned audit/explanation
  activity. The screen explicitly discloses that a persisted review queue, cloud
  benchmark API and general recommendation inbox do not exist. No fake metrics or
  frontend-only persisted state are represented as functioning features.

## Obsolete parallel code retired, not lost user capabilities

The machine-readable [manifest](canonical-main-merge-manifest.json) records every
incoming path/function, all conflict decisions, and every superseded file with its
replacement and test coverage. No canonical file was deleted.

43 main-only obsolete/redundant files were retired: one nested ignore, nine conflicting
migrations, parallel OAuth/calendar/delivery storage and services, and 11 tests coupled
to those obsolete internal contracts. **Those 11 old implementation-specific test
files were not executed or counted as passing.** They were replaced by canonical
provider/monitoring/auth/RLS/security coverage and retained/adapted main tests against
canonical interfaces. No canonical test was deleted, weakened or newly skipped.
Both original versions remain accessible through merge parents and safety refs.
The added backend tests are 80 cases above canonical's 1,332, not a reduced test-count
target; frontend adds two Quality Hub cases to the canonical 257 passing cases.

Main contained syntax-invalid implementations in OAuth/integration routers, app startup,
OAuth state model, Bee adapter and event ingestion (recorded in the manifest). These
were not copied over the validated canonical architecture. Main tests with duplicate
function definitions were inventoried rather than treated as multiple executed tests.

## Features and recent fixes preserved

Core FastAPI/PostgreSQL models, Supabase identity/ownership/RLS, CRUD, evidence,
deterministic evaluation, audit and health/readiness remain canonical. MCP retains
Streamable HTTP, bearer propagation, all six tools, nested `request` schemas,
initialize/list/call, budgets and ownership. Compiler, temporal interpretation,
clarification/corrections/cancellation, typed grounding and fallback are retained.
The trust orchestrator remains constrained; investigator_service owns DB/ownership/gating
and investigation_service owns the grounded model boundary. MATCH/UNKNOWN bypass
mismatch investigation. Bedrock/agents/UI never decide outcomes.

ASK adapter, signature/timestamp/replay validation, linking and durable dialogue;
web `/alexa`; Google/Gmail/calendar and Microsoft/Outlook/calendar encrypted grants,
refresh/revoke/reconnect/checkpoints; email-derived Amazon facts; confirmed source
planning/correlation; separate Ring/Bee simulators and Bee CLI consent; monitoring
leases/deadlines/recovery; notification inbox/delivery preferences/dedupe; and the full
canonical dashboard/detail/creation/edit/resolution/evidence/history/integrations/
notifications/activity/settings interfaces are retained.

The following recent-fix implementations and tests are unchanged from canonical and
pass the merged full suites:

- Provenance spoofing: `backend/app/api/v1/evidence.py`, `tests/test_evidence.py`.
- Bee expiry/correlation/promise boundaries: `services/bee_connector_service.py`,
  `tests/test_bee_cli_bridge.py`, correlation/authorization suites.
- Historical result snapshots: frontend `presentation.ts`, reality decision card,
  resolution panel and their tests.
- Local-date preset deadlines: expectations/new page and creation tests.
- Six-tool smoke contracts: `backend/db/scripts/mcp_smoke.py`,
  `tests/test_mcp_remote.py`, frontend opt-in discovery test.

## Migration status and deployment gate

Exactly **13** canonical revisions in one linear chain, head **`d6a71c9e24f0`**.
All canonical migration files are unchanged from the source branch. No duplicate
OAuth/delivery tables, alternate graph or stamp was introduced. Full tests exercise
upgrade, guarded downgrade/re-upgrade, metadata/constraints and RLS using disposable
local test databases. The nine incompatible main migration files remain excluded.

**A deployed database on a rejected main-only revision cannot simply run this graph.**
Before production migration, inspect its actual revision/schema, back up and restore
into staging, design/review a data-preserving reconciliation and test rollback. This
merge does not claim or execute that deployment procedure. Live DB revision is unknown.

## Exact local validation

Local Python **3.14.6**, Node **24.19.0**, npm **11.17.0**. CI/Docker still target Python
3.12; no hosted Python 3.12 or remote CI success is claimed. Backend database checks use
only `TEST_DATABASE_URL` targeting loopback `counton_test`, never the application env
URL. Test fixtures reject nonlocal/application-identical/non-test targets; isolated
migration/concurrency databases are created and removed locally.

From `backend/`:

```sh
PYTHONPYCACHEPREFIX=/tmp/counton-main-merge/pycache .venv/bin/python -m compileall -q app alembic db/scripts
.venv/bin/python db/scripts/alexa_import_smoke.py
.venv/bin/alembic heads
.venv/bin/alembic history
.venv/bin/pytest -q --tb=short
.venv/bin/ruff check app db/scripts tests alembic ../scripts
.venv/bin/mypy app --ignore-missing-imports
.venv/bin/mypy --strict --follow-imports=silent --ignore-missing-imports app/ai app/agent app/alexa app/mcp/compiler.py app/mcp/intelligence.py app/mcp/conversation_state.py app/mcp/schemas.py app/api/v1/agent.py app/api/v1/alexa.py app/schemas/compiler.py app/schemas/clarification.py app/schemas/investigation.py app/schemas/trust.py app/services/compiler_service.py app/services/investigation_service.py app/services/investigator_service.py app/services/agent_audit.py db/scripts/bedrock_smoke.py
.venv/bin/bandit -q -r app -ll
.venv/bin/pip-audit --progress-spinner off
.venv/bin/python db/scripts/orchestration_eval.py
.venv/bin/python db/scripts/production_smoke.py
```

From `frontend/`:

```sh
npm test
npm run lint
npm run typecheck
NEXT_PUBLIC_API_BASE_URL=https://api.counton.invalid npm run build
npm audit --omit=dev
npm audit --audit-level=high
```

From root:

```sh
python3 scripts/secret_scan.py
git diff --check
git diff --cached --check
git ls-files -u
git diff --name-only --diff-filter=D integration/counton-canonical
```

| Check | Actual merged result |
| --- | --- |
| Backend full suite, final rerun | **1,412 passed, 0 failed, 0 skipped; 104 upstream ASK cryptography deprecation warnings; 65.14 seconds** |
| Frontend suite | **259 passed, 0 failed, 1 existing credential-gated live MCP test skipped** |
| Compileall / Alexa imports | PASS; both default and ctypes native crypto imports |
| Migration graph | PASS, one head, 13 revisions; full-suite local upgrade/downgrade tests |
| MCP | PASS full-suite network/contracts/ownership and offline smoke initialize/list/call; no public probe |
| Bedrock | PASS isolated compiler/clarification/investigator tests; no AWS call |
| Agent/trust | PASS full-suite routing/state/provenance/budgets/injection/isolation tests |
| Alexa | PASS signed local request/dialogue/dependency tests; no ASK console/Echo interaction |
| Providers | PASS fixtures/owned grants/callback/source planning/correlation + main compatibility tests; no live consent |
| Monitoring/notifications | PASS leases/recovery/dedupe/inbox/outbox + SMTP uncertainty regression |
| Ruff | PASS |
| Mypy | PASS, 167 source files |
| Strict Mypy | PASS, 38 source files |
| Bandit | PASS existing medium/high gate |
| pip-audit | PASS, no known vulnerabilities |
| npm audits | PASS runtime and full dependency scopes, zero vulnerabilities |
| Gitleaks/history/source | PASS, zero findings with the documented public-key exception below |
| Synthetic orchestration | PASS **26/26**, zero Bedrock calls; human review/live gates remain blocked |
| Offline production smoke | PASS all six groups: startup/six tools, HTTP/ownership, signed Alexa, durable conversations, tracking/notification recovery, source/correlation/budgets |
| Frontend lint/typecheck/build | PASS; production validation build uses credential-free invalid API origin, not a deployment artifact |
| Conflict markers / unmerged index | None |
| Canonical file deletions | None |
| Working/index whitespace checks | PASS after normalizing the pre-existing whitespace described below |

The first history scan found a real **public** `sb_publishable_` value in historical
`frontend/.env.example`, not an AWS/Supabase secret or service-role key. Current source
has placeholders. Supabase documents publishable keys as safe to expose:
https://supabase.com/docs/guides/getting-started/api-keys . The new exception is scoped
to the `generic-api-key` rule, exact frontend template path and public-key assignment
prefix. All other detector rules remain enabled. Synthetic controls confirmed that a
secret key in the same template and a key in a different path are still detected.
No key values were printed or newly copied to source. An initial global-allowlist
attempt failed the synthetic boundary control and was replaced with the verified
rule-scoped form before final scanning; that unsafe attempt is not the final config.
Gitleaks v8.30.1 runs via the pinned network-disabled Docker scanner; no separate
standalone CLI is installed or claimed. Scan findings are reported without values.

## Every meaningful difference from canonical

The following groups cover the complete remaining path delta. The manifest contains
additional file/function detail. There are no canonical deletions.

- `.gitleaks.toml`: Narrow rule-scoped public Supabase key false-positive correction; controls preserve secret detection.
- `README.md`: Link this merge validation receipt; component architecture remains canonical.
- `backend/app/api/v1/calendar.py`: Owned, bounded calendar compatibility read over canonical projections.
- `backend/app/api/v1/dashboard.py`: Retain main-owned summary and unresolved-mismatch API; import cleanup only beyond main.
- `backend/app/api/v1/manual_events.py`: Retain main manual-event/sync/read URL capabilities through existing ownership, sources, evidence and worker authority.
- `backend/app/api/v1/oauth.py`: Retain main OAuth start/callback entry points over canonical grants; Microsoft form_post enforced.
- `backend/app/api/v1/router.py`: Register reviewed dashboard/calendar/OAuth/manual compatibility routes once.
- `backend/app/core/config.py`: Add optional typed SMTP settings and provider selection; canonical defaults/validation retained.
- `backend/app/integrations/bee/__init__.py`: Preserve explicit manual simulation/email normalization; force safe provenance and validate minimal facts.
- `backend/app/integrations/email/__init__.py`: Preserve explicit manual simulation/email normalization; force safe provenance and validate minimal facts.
- `backend/app/integrations/ring/__init__.py`: Preserve explicit manual simulation/email normalization; force safe provenance and validate minimal facts.
- `backend/app/notifications/delivery.py`: Optional SMTP channel on canonical delivery worker/outbox with no uncertain replay; Resend remains default.
- `backend/app/notifications/worker.py`: Optional SMTP channel on canonical delivery worker/outbox with no uncertain replay; Resend remains default.
- `backend/app/services/email_delivery.py`: Retain bounded TLS SMTP adapter; no private claim/evidence payload leakage.
- `backend/app/services/integration_event_service.py`: Thin main compatibility ingestion adapter through canonical source approval/persistence/evaluation.
- `backend/app/services/integration_retry.py`: Retain main bounded retry helper without replacing durable workers.
- `backend/app/services/supabase_user_service.py`: Retain trusted-backend verified email lookup using existing Supabase authority.
- `backend/notifications.env.sample`: Document explicit opt-in SMTP on the existing outbox, required TLS and uncertainty handling.
- `backend/tests/test_bee_integration.py`: Retain/adapt main capability tests or add merge-specific ownership, callback, route and SMTP regressions.
- `backend/tests/test_calendar_api.py`: Retain/adapt main capability tests or add merge-specific ownership, callback, route and SMTP regressions.
- `backend/tests/test_dashboard.py`: Retain/adapt main capability tests or add merge-specific ownership, callback, route and SMTP regressions.
- `backend/tests/test_email_delivery.py`: Retain/adapt main capability tests or add merge-specific ownership, callback, route and SMTP regressions.
- `backend/tests/test_integration_event_ingestion.py`: Retain/adapt main capability tests or add merge-specific ownership, callback, route and SMTP regressions.
- `backend/tests/test_integration_retry.py`: Retain/adapt main capability tests or add merge-specific ownership, callback, route and SMTP regressions.
- `backend/tests/test_main_merge_compatibility.py`: Retain/adapt main capability tests or add merge-specific ownership, callback, route and SMTP regressions.
- `backend/tests/test_supabase_user_service.py`: Retain/adapt main capability tests or add merge-specific ownership, callback, route and SMTP regressions.
- `docs/canonical-main-merge-manifest.json`: Machine-readable per-file/function conflict, supersession and coverage audit.
- `docs/canonical-main-merge.md`: This local merge validation and deployment-limitation report.
- `docs/person1-release-acceptance.md`: Trailing-whitespace normalization only; historical report meaning unchanged.
- `frontend/app/(workspace)/quality/page.tsx`: Retain protected main Quality Hub; use real owned audit API and disclose missing benchmark/review APIs.
- `frontend/lib/api.ts`: Add authenticated dashboard-summary/unresolved-mismatch helpers; canonical methods unchanged.
- `frontend/proxy.ts`: Protect retained /quality page using the existing session proxy.
- `frontend/public/fonts/inter-OFL.txt`: Whitespace/line-ending normalization only; full license text and assets preserved.
- `frontend/public/fonts/spacegrotesk-OFL.txt`: Whitespace/line-ending normalization only; full license text and assets preserved.
- `frontend/tests/quality.test.tsx`: Two regressions verify actual audit activity and safe retry on failure.
- `frontend/vendor/braces/lib/stringify.js`: Remove one extra trailing blank line only; vendored source behavior unchanged.

## Live limits and next human action

Not verified by this merge: live database revision, hosted CI/Python 3.12 runtime,
production API/MCP, real Bedrock inference, Google/Microsoft account acceptance,
Amazon sign-in producing a real Supabase session, ASK simulator, Echo Dot,
physical Ring or real Bee account/device. Ring/Bee demo observations remain explicitly
simulated. Local fixture and signed-request tests are not device/provider acceptance.

After the local merge commit and human review, the human may run `git push origin main`.
That is not deployment approval. Hosted CI must then run, and production database
reconciliation/provider/device gates above remain mandatory before rollout.
