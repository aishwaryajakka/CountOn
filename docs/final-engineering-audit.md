# CountOn final engineering audit — 2026-10-23

This is the authoritative report for this audit of the **current worktree**, not an archive merge or a production acceptance certificate. Earlier dated reports retain their historical observations. No commit, push, deployment, live OAuth change or production migration was performed.

## A. Current branch

- Branch: `integration/counton-canonical`.
- HEAD: `8d4b72fce137c95bfa01e997ddb839f139063057`.
- Safety branch: `backup/pre-consolidation-2026-10-23`, retained.
- Intentional consolidation modifications and untracked files were present on entry and remain present. No reset, stash, clean, branch switch, removal or wholesale ZIP import occurred.
- Before editing, branch/HEAD/status/diff/untracked paths/recent history were inspected; initial tracked patch and status were saved outside the repository in `/tmp/counton-final/`. A pre-edit feature classification was recorded there. Final exact status is in section K.
- Five supplied ZIPs remain references. The main ZIP's competing OAuth/delivery migrations were re-inspected in memory; no files were extracted over canonical code.

## B. What was already present

The implementation already contains one FastAPI app, Supabase Auth identity boundary, SQLAlchemy persistence/repositories, deterministic evaluators, six-tool MCP server, Bedrock compiler/clarification/investigator, constrained trust orchestrator, browser Alexa demo, ASK adapter, source planner, Google/Microsoft provider synchronization, Ring/Bee simulators, optional local Bee bridge, PostgreSQL workers, notification inbox/outbox and minimal audit history.

Code inspection confirmed these boundaries:

- `backend/app/main.py`, `api/operations.py`, `api/budgets.py`, `api/errors.py`, `core/config.py`, `core/auth.py`, `api/dependencies.py`: lifecycle startup, health/readiness, error envelopes, request IDs, exact CORS, request budgets, JWT claims/signatures and verified profile/ownership. Settings select the backend `.env.local`; production rejects local database/CORS/MCP configurations. Public health is liveness; readiness checks migration revision, tables and columns, not optional provider/model access.
- `services/expectation_service.py`, repositories and schemas: owned create/list/get/update/delete, explicit fields, terminal statuses, tracking controls and safe profile upsert. Child ownership/FKs/RLS are tested, including disposable Supabase-shaped schemas. App authorization remains necessary when the trusted database role bypasses RLS.
- `repositories/evidence.py`, `services/evidence_service.py`, `evaluators/`: exact metric/source selection ordered by `observed_at DESC`, then deterministic tie-breakers; numeric tolerance/zero handling, explicit boolean facts and conservative temporal logic. Monitoring adds freshness, conflicts, permissions and covered-absence policy. UNKNOWN can preserve a previous lifecycle status; clients must use the actual latest evaluation rather than reinterpret the status as a fresh verdict.
- `mcp/server.py`, `mcp/tools.py`, `mcp/http.py`, `mcp/__main__.py`: official SDK `MCPServer.streamable_http_app`, stateless Streamable HTTP `/mcp`, bearer validation, safe errors, Host/Origin policy, `/health` and `/ready`. Six tools each have exactly one top-level `request` and delegate to existing services. `httpx2` is intentionally declared and used by MCP 2.x transports; ordinary HTTPX remains used by REST/provider clients. These are compatible dependencies, not an unresolved import typo.
- `ai/bedrock_client.py`, `expectation_compiler.py`, grounding, clarification/facts, prompts and telemetry: strict typed output; no model-directed tool execution; bounded retries/timeouts/concurrency/token budgets; normal AWS credential chain; configurable compiler/investigator model overrides. Clarification uses canonical signed state and a durable capture ledger with TTL, corrections, replacement, cancellation and replay protection. Ordinary tests invoke no real AWS model.
- `services/investigator_service.py` is the owned DB loader/latest-MISMATCH gate; `services/investigation_service.py` is the pure permission/grounding/model boundary. They are intentionally distinct and retained. `ai/mismatch_investigator.py` validates evidence references and renders bounded supported factors, with safe fallback. MATCH/UNKNOWN never invoke investigation.
- `agent/registry.py`, action/plan schemas, orchestrator/session/trust/privacy: immutable allowlist, validated sequence, explicit web/production ASK capture confirmation, no caller-controlled tools/owner, bounded search/execution and safe provenance. This is constrained orchestration, not a second autonomous agent framework.
- `frontend/app/api/agent/route.ts`, `api/mcp/route.ts`, `lib/mcp/`, `app/alexa/page.tsx`: auth-gated conversation, server-side orchestration, real protocol discovery, no browser arbitrary tool execution, sanitized traces and no token return/logging. An expectation query parameter is an untrusted selection; owned MCP reads reauthorize it. Six tool names and nested contracts are preserved.
- `alexa/verification.py`, `adapter.py`, `api/v1/alexa.py`, interaction model: original-body SHA-256 ASK verification, bounded certificate fetch, maintained PKIX trust-chain validation, timestamp/application/session checks, durable replay protection, linked Supabase identity and seven-second voice budget. An unsigned call is rejected. No signature bypass was added.
- `frontend/lib/auth/`, proxy, auth provider/pages and `api/v1/amazon_auth.py`: email/password/confirmation/recovery/refresh/logout, cookie-backed server validation, guarded callbacks/linking and optional `custom:amazon`. Amazon UserInfo translation checks token audience/subject and returns only `sub`; Supabase alone exchanges codes, links identities and issues sessions. This code does **not** prove the project's live custom-provider setup, email delivery or an actual Amazon-produced Supabase session. Amazon identity grants no order/Ring/Bee access.
- `integrations/accounts.py`, `microsoft.py`, normalization, worker, watches and `services/provider_sync_service.py`: delegated read scopes, PKCE/single-use state, encrypted tokens/checkpoints/projections, identity fencing, bounded provider authorities/links, initial/incremental sync, expiry/revocation/disconnect, signed/verified push hints and periodic reconciliation. Outlook reads Inbox, not arbitrary folders. Google-specific tests cover Gmail pagination/history, large history batches, calendar sync tokens/selection, revocation and authenticated Pub/Sub.
- `source_planning_service.py`, provider source rules, monitoring correlation: user selects actual owned projected records; confirmation recomputes eligibility and current permissions. Exact sender/thread/order/UID/occurrence identity governs correlation. Titles and source type alone do not authorize matching. Disconnected/expired sources cannot continue publishing trustworthy facts.
- `integrations/ring/`, `integrations/bee/`, simulator API and frontend: simulated labels, source-bound owned submissions, stable IDs, persistence and real evaluator responses. Ring no-detection lacks a boolean nondelivery fact. Bee promises remain context, not observed fulfillment. No live hardware is claimed.
- `integrations/bee/cli_bridge.py`, `services/bee_connector_service.py`: fixed CLI invocations, separate local authentication, single-use pairing, hashed revocable connector credential, minimal staged summaries/facts, explicit selection/import approval, checkpoint/dedupe and disconnect. This pass additionally enforces grant/candidate expiry and serializes publication with revocation. A selected completed todo supports only the explicit `todo_completed` metric, not a plumber arrival. Fixture coverage is not real Bee account acceptance. No unauthenticated public local proxy was introduced.
- `monitoring/worker.py`, `integrations/worker.py`, `notifications/worker.py`: SQL leases/fencing, stable run identities, retries/backoff/dead letters, restart-safe publication and atomic evaluation/inbox. MATCH does not create a mismatch alert; UNKNOWN does not reset a mismatch episode; repeated confirmed mismatches are suppressed. Optional email uses opt-in, encrypted recipients/payloads and a bounded provider idempotency window.
- `repositories/audit.py`, `services/audit_service.py`, `/activity`: linked owned persisted events, safe references/metadata, minimal displayed columns. Provider bodies/attachments/audio/video/transcripts are not retained as arbitrary raw audit payloads. Authorized normalized provider projections are bounded/encrypted and expire; conversation records expire; imported Bee staging content is cleared. This is not a claim of an externally audited retention program.

### One traced expectation

`tests/test_release_journey.py::test_confirmed_voice_capture_provider_worker_shared_state` exercises both Google and Microsoft fixtures with real local JWT verification, HTTP MCP and PostgreSQL:

```text
ASK-shaped capture -> canonical compiler/clarification (mock model)
 -> explicit yes -> MCP capture -> owned SQL expectation
 -> authorized provider grant + bounded normalized record (provider fixture)
 -> monitoring-plan preview -> explicit selected-source confirmation
 -> source binding -> evidence publication -> monitoring wake/run
 -> deterministic evaluation -> SQL history + one inbox notification
 -> ordinary authenticated API/dashboard data source sees the same row
 -> fresh conversation/worker instances recover durable state; retries deduplicate
```

The bill acceptance tests also exercise 180 versus a 150 target; Ring positive/missing observations and Bee context-only events are exercised through their dedicated backend APIs. These are local integration scenarios, not actual spoken Echo or cloud-provider tests.

## C. Gaps found

| Severity | Files/boundary | Confirmed issue and resolution |
| --- | --- | --- |
| P0 security | Python constraints; frontend package/lock | Advisory scans found vulnerable certifi 2026.7.22, opentelemetry-api 1.45.0, Next.js 16.3.8 and Vite 8.3.0–8.3.2. Updated fixed dependencies; final Python/npm audits pass. |
| P1 provenance | `backend/app/api/v1/evidence.py` | An authenticated manual payload could claim `LIVE_BEE_CLI`/provider grant, sender, coverage and source-version metadata, polluting provenance/audit attribution. HTTP ingestion now strips provider authority and normalizes supplied provenance to USER_SUBMITTED. Internal verified publication remains intact. |
| P1 presentation | decision/resolution panels and presentation helper | A saved evaluation's observation was compared with edited current criteria, and could borrow unrelated latest evidence metadata. Panels now use saved expected target/comparison and the pinned evidence ID; absent snapshots do not invent variance. Backend outcomes/tolerance are unchanged. |
| P1 deadline | manual package preset | “Today” populated tomorrow and used a UTC substring as local wall time. Preset now previews today's local 23:59 and still requires explicit confirmation. |
| P1 authorization/fact integrity | `services/bee_connector_service.py` | Import failed to recheck credential/candidate expiry; arbitrary completed todos could become appointment outcomes. Import now rechecks expiry, holds the revocation credential lock through publication, re-reads candidates under lock, and supports a positive fact only for explicit `todo_completed`. Other todo evidence remains context. Expired connector status is disconnected. |
| P1 acceptance | MCP smoke/live test | Discovery accepted only three core tools, allowing an old deployed surface to appear accepted. Smoke now requires all six and nested request/object output contracts; opt-in frontend discovery also expects all six. |
| P2 CI coverage | strict mypy command | CI omitted the owned investigator DB gate. Added it without removing existing scopes or changing frontend/secrets jobs. |
| P2 docs | README, DB guide, readiness/checklists | “Done locally,” stale migration table/head context, unconditional upgrade advice, old smoke wording and shared-state ambiguity corrected. Historical observations remain explicitly historical. |
| Incomplete, intentionally not fabricated | recommendations | Source-plan suggestions and Bee import review exist; a general owned persisted recommendation inbox/review lifecycle does not. No fabricated AI recommendations were restored. No clear canonical contract justified building a replacement during this release audit. |
| External release gate | production/CI/providers | Current production revision, Python 3.12 hosted CI and real identity/provider/device/model acceptance remain unverified in this pass. See I/J. |

No canonical migration, evaluator, compiler, clarification format, MCP tool or auth authority was replaced. No source assets or tests were deleted. The marker search was reviewed: exception subclasses/base classes, malformed-input abstention, best-effort remote revoke with local purge, discarded stale sessions and the development-memory `persist` override are intentional; they are not fake production implementations. The unused `/agent/reset` string in the OAuth-client allowlist has no registered route and no reachable business operation; reset/cancellation uses the canonical conversation flow. It is not an implemented endpoint.

## D. Implementation changes

Only the following files were added/modified **by this final pass**; pre-existing consolidation work is separately preserved and remains listed in K and the [consolidation manifest](consolidation-manifest.json).

| File(s) | Purpose and preserved behavior | Validation |
| --- | --- | --- |
| `.github/workflows/ci.yml` | Extend strict typing to `investigator_service.py`; retain jobs, permissions and every prior check | Expanded strict mypy, workflow review; hosted execution not claimed |
| `backend/constraints.txt`, `backend/requirements.txt` | certifi 2026.10.19, opentelemetry-api 1.45.1; no credentials/dependency authority change | pip install/check/audit, Alexa import, full backend |
| `backend/app/api/v1/evidence.py` | Separate untrusted manual metadata from internal provider authority; preserve payload shape, user facts, empty metadata and idempotency | Evidence/audit/provider/simulator tests, 69-test focused group, full backend |
| `backend/app/services/bee_connector_service.py`, `backend/tests/test_bee_cli_bridge.py` | Expiry, revocation serialization, truthful connector status and exact todo fact semantics; preserve separate simulator and consent flows | Five added regression cases, including actual PostgreSQL NOWAIT lock verification; focused/full backend |
| `docs/bee-ring-integration-acceptance.md` | Clarify completed-todo scope and expired grant/candidate handling | Source/test review; live Bee remains unverified |
| `backend/tests/test_evidence.py` | Regression: forged authority removed, replay stable, actor USER | Same |
| `backend/db/scripts/mcp_smoke.py` | Require six discovered tools and nested schemas; retain tagged CRUD/cross-check/cleanup | Final 93-test MCP group, full backend |
| `backend/tests/test_mcp_remote.py` | Regressions for missing intelligence tools, flattened schemas and valid six-tool discovery | 29 tests in this file; final MCP/full suites |
| `frontend/package.json`, `frontend/package-lock.json` | Security update to Next/ESLint Next 16.4.2 and transitive Vite 8.3.5; preserve local braces override | Clean locked install, audits, tests/lint/typecheck/build |
| `frontend/lib/presentation.ts` | Optional evaluation snapshot for expected text, conservative missing-target label | Component/presentation/full frontend tests |
| `frontend/components/reality-decision-card.tsx`, `resolution-panel.tsx` | Correct historical target/variance and pinned evidence metadata; preserve persisted verdict and actions | Historical snapshot regressions; full frontend |
| `frontend/tests/reality-decision-card.test.tsx`, `resolution-panel.test.tsx` | Three added historical/missing-snapshot regressions | Focused 28 tests; final full suite |
| `frontend/app/(workspace)/expectations/new/page.tsx`, `frontend/tests/creation.test.tsx` | Today/local preset correction with explicit preview/save retained | Creation 4 tests; full frontend |
| `frontend/tests/mcp-live.test.ts` | Expected discovery includes all six canonical tool names | File loads; its real-account execution remains opt-in/skipped |
| `README.md` | Canonical status, confirmation, truthful durable state and migration gate | Documentation/link review, diff check |
| `backend/db/README.md` | All 13 revisions, internal table/RLS boundaries and live revision gate | Migration/RLS tests and code comparison |
| `docs/mcp.md`, `docs/agent-skill.md` | Accurate six-tool discovery, server-side routing and native Alexa+ versus ASK boundaries | Script/tool/source comparison |
| `frontend/README.md` | Correct current ESLint version/validation description; retain prior consolidation notes | Package/lock/config and successful lint comparison |
| `docs/hackathon-acceptance.md` | Link current evidence and require live revision review | Documentation review |
| `docs/production-readiness.md` | Clearly label October 12 observations as historical | Documentation review |
| `docs/data-minimization-and-audit-policy.md` | Document manual provenance sanitation and trusted publication distinction | Evidence regression and source review |
| `docs/final-engineering-audit.md` | This authoritative inventory, exact validation and human acceptance plan | Structural/link review, final status/diff check |

Security updates were necessary lockfile changes, not an unrelated dependency refresh. The initial findings were confirmed by the advisory scanners and [Next.js's advisory](https://github.com/vercel/next.js/security/advisories/GHSA-2464-fhr4-w9xw) and [Vite's advisory](https://github.com/vitejs/vite/security/advisories/GHSA-9jrq-w75r-8gcw). No forced/major audit fix, weakened severity threshold or advisory ignore was added.

### Preserved consolidation work

The original working set includes the expectation list/new/detail UI, integration/settings controls/alias, activity filters, expectation/notification components, Alexa deep links, API/type/agent contracts and their tests. `backend/app/api/v1/agent.py` still passes only an untrusted selection into the existing remote MCP adapter and owned services. Existing simulator integration fixes and tests remain. No seeded recommendation components or archive-only migration/credential/service layers were imported. See the [per-file manifest](consolidation-manifest.json) and [dated consolidation report](consolidation-report.md) for their file-by-file purpose/provenance; section K records all current paths, including untracked components.

## E. Requirement coverage matrix

“Local” below means automated validation with real isolated PostgreSQL/HTTP where applicable and fixture inference/provider responses. None of these labels certifies current production.

| Area | Implementation status | Automated validation | Live/manual status | Remaining action |
| --- | --- | --- | --- | --- |
| Core/FastAPI | Implemented | Core/startup/operations/readiness/full suites | Not probed | Deploy matching image; health/readiness/CORS/limits |
| Supabase/Postgres | Implemented | Migration cycle/metadata/RLS/local SQL | Production revision not queried | Mandatory F gate, backup and shared DB |
| Auth/ownership | Implemented; Amazon optional/default-off | JWT, tenant/RLS, callback/linking/frontend auth suites | No new real signup/Amazon session | Email/SMTP and real Amazon-produced Supabase session; separate Alexa OAuth |
| Expectations | Implemented | CRUD, fields, lifecycle, manual preview and compiler tests | Not live accepted | Confirm capture, refresh and terminal controls |
| Evidence | Implemented; manual provenance repaired | Normalization/history/dedupe/IDOR/privacy regression | Provider fixtures only | Consented live source/evidence check |
| Evaluations | Implemented, deterministic | Numeric/boolean/temporal, freshness/conflict/deadline suites | Not live accepted | Actual persisted demo facts; no invented outcome |
| Notifications | Implemented inbox + optional outbox | Preferences/read/dedupe/concurrency/crash/retry tests | No actual email sent | Verify inbox once; opt-in delivery separately |
| Monitoring | Implemented SQL workers | Leases/fences/restart/revoked source/deadline tests | No deployed worker proof | Supervise shared-DB workers; restart/recovery |
| Audit | Implemented minimal owned linked history | Audit/privacy/API/frontend tests | Not live accepted | Inspect safe source/result/event links |
| MCP | Implemented six nested tools/Streamable HTTP | 93 targeted; real loopback protocol/JWT/SQL | No public probe this pass | Six-tool discovery and authenticated remote smoke |
| Bedrock | Implemented runtime/compiler/clarification/investigator | 279 targeted, full suites; typed failure/grounding tests | No AWS inference this pass | Real smoke, compile and latency/grounding acceptance |
| Agent/Trust | Implemented constrained coordinator | 259 targeted, injection/budget/owner/replay tests | No new remote run | Human-review synthetic cases and live conversation |
| /alexa | Implemented auth-gated demo | Frontend/API/network agent/capture tests | Not browser/live accepted | Signed-in list/get/confirm/clarify/Why |
| ASK | Implemented adapter/model/verification | 81 targeted + import smoke, durable replay | Console/Echo not tested | Configure exact URLs/client/skill, latency and device |
| Google OAuth | Implemented delegated consent/grants | PKCE/state/refresh/revoke/scope/identity tests | No real consent | Configure console/client; authorize dedicated account |
| Gmail | Implemented bounded Inbox/history sync | Pagination, recovery, exact correlation, Pub/Sub tests | Fixtures only | Real initial/history sync and verified push if enabled |
| Google Calendar | Implemented selected calendar/sync tokens | Selection/recurrence/cancel/reschedule/time tests | Fixtures only | Select actual calendar and occurrence, change/cancel |
| Microsoft OAuth | Implemented delegated consent/grants | Exact callback/state/scopes/refresh/revoke tests | No real tenant consent | Entra credentials/callback; verify issued permissions |
| Outlook | Implemented Graph Inbox/delta | Pagination/cursor/recovery/identity/ownership tests | Fixtures only | Actual Inbox initial + incremental changes |
| Microsoft Calendar | Implemented default delta + selected nondefault window reconciliation | Calendar identity/recurrence/reschedule tests | Fixtures only | Actual default/nondefault calendar acceptance |
| Amazon email evidence | Implemented authorized order/report normalization | Exact order correlation, prediction/report/time tests | Fixtures only | Approved Gmail/Outlook records; no direct retail access |
| Ring simulator | Simulated by design | Owned bound API/evaluator/replay/UI tests | No live hardware claim | Run dedicated simulator and inspect persisted provenance |
| Bee simulator | Simulated by design | Promise versus outcome, ownership/dedupe/API/UI | No live hardware claim | Save context; verify UNKNOWN without outcome |
| Bee CLI | Implemented optional local bridge | Fixture parsing, consent, pairing/import/revoke/isolation | No real CLI/account read performed | Independently verify official CLI/version/auth/data; optional |
| Frontend | Implemented all current routes/controls | 257 passed, 1 live skip; lint/typecheck/build | No current deployed/browser acceptance | Approved env/rebuild; two users and reload checks |
| Security | Implemented boundaries; findings fixed | Ruff/mypy/Bandit/advisories/Gitleaks; malicious-input tests | Not independent penetration test | Edge/shared rate limits, live OAuth/certs, hosted CI |
| Deployment configuration | Implemented templates/process commands | Config/startup/deployment/backup local tests | No deploy/production migration | Runtime secrets/IAM/revision/CI gates and I plan |

### Explicitly incomplete or excluded

General persisted recommendation review is incomplete; source-plan suggestions and Bee candidate review are real. No invented recommendations are shown. Native Alexa+ developer MCP onboarding remains externally blocked. Physical Ring, live Bee wearable acceptance, direct consumer Amazon order sync, Apple Calendar, saved-expectation voice editing, proactive Alexa notifications and a broad autonomous agent are not implemented/claimed. Email/calendar fact extraction is deterministic normalization; the compiler and mismatch investigator actually call Bedrock. Deterministic services are not relabeled as independent AI agents.

## F. Database/migration status

Canonical ordered revisions:

```text
1bbc27e27689 -> 2e0a91d54c31 -> 3a874e01bb52 -> 4bc128091ea7
 -> 5d201f68ac90 -> 6e302a79bd01 -> 7f413b80ce12 -> 8a524c91df23
 -> 9b635da2e034 -> ac746eb3f145 -> b4819ac72e30 -> c592d04e8f41
 -> d6a71c9e24f0 (single head)
```

`alembic heads/history` confirm a connected linear graph. Actual disposable-database migration tests cover upgrade, downgrade to base, re-upgrade, ownership-backfill abort without data loss, new metadata/RLS and guarded rollback. Head upgrade/current ran explicitly against **127.0.0.1/counton_test** only. No canonical migration/schema edits were needed. Relevant constraints/indexes/FKs/NOT NULL and metadata comparisons pass the suite.

The reference main ZIP still forks after `5d201f68ac90`: `f7a9c2d1b640 -> 298fc0cf83dc -> 70e96a04757b` and `8b10af011a55 -> 501e82ab1613 -> e8b2dc123ad7 -> 4c35f2c88019 -> 07bc7f5ce116 -> e5e411421101`. Those branches create competing `oauth_credentials`/`oauth_states`, another notification delivery contract and nullable standalone monitoring. Importing/stamping them into canonical history would not safely reconcile schema/data. They remain excluded.

### Mandatory production gate — not executed

A human must privately connect to the **actual live database** and run:

```sql
SELECT version_num FROM public.alembic_version;
```

Record its revision, schema/roles and backup identity. Do not expose the connection string.

- If already `d6a71c9e24f0`, inspect schema readiness/metadata rather than stamp it.
- If on a verified ancestor in the canonical chain, review migration SQL, backup/restore and lock/data-backfill requirements before the normal approved command `cd backend && .venv/bin/alembic upgrade head` in the intended trusted production environment.
- If on any rejected main-only revision, unknown revision or divergent schema: **STOP**. Require a reviewed transition migration and data/ownership reconciliation plan. **Do not run `alembic stamp head` or blindly run `alembic upgrade head`.**
- No live revision was inspected in this pass; historical reports are not proof of today's revision.

## G. Validation commands and results

All commands below actually ran. Local Python is **3.14.6**, Node **24.19.0**, npm **11.17.0**. Python 3.12/gh/standalone gitleaks/skills-ref were not found on the local PATH; common local Python install locations also had no 3.12. CI/Dockerfile still target Python 3.12. An AST syntax check with `feature_version=(3,12)` passed 199 production/migration/script files; this is **not** a Python 3.12 runtime claim.

For every DB-backed pytest command, `TEST_DATABASE_URL` selected only the distinct loopback `counton_test` database. Fixtures reject nonlocal, non-`_test` or application-identical targets. Migration/concurrency/backup tests create and remove uniquely named local test databases/profiles. `.venv/bin/pytest -q --tb=short` is the common prefix for the targeted rows below, from `backend/`.

| Command/scope | Actual result |
| --- | --- |
| `python --version`; `.venv/bin/python --version` | Python 3.14.6 / 3.14.6 |
| `PYTHONPYCACHEPREFIX=/tmp/counton-final/pycache .venv/bin/python -m compileall -q app alembic db/scripts` | PASS, also repeated after fixes |
| `.venv/bin/python db/scripts/alexa_import_smoke.py` | PASS default and ctypes crypto imports; repeated after CA update |
| `.venv/bin/alembic heads`; `.venv/bin/alembic history` | PASS, one head and 13 revisions |
| `ENVIRONMENT=test DATABASE_TARGET=local LOCAL_DATABASE_URL=<isolated loopback counton_test URL> .venv/bin/alembic upgrade head` then `current` | PASS, `d6a71c9e24f0`; no live DB |
| Core: `tests/test_auth.py tests/test_auth_rls.py tests/test_ownership.py tests/test_expectations.py tests/test_evidence.py tests/test_evaluations.py tests/test_numeric_evaluator.py tests/test_other_evaluators.py tests/test_health.py tests/test_startup.py tests/test_config.py tests/test_migrations.py` | 235 passed before the new provenance regression; final full suite includes it |
| MCP: `tests/test_mcp.py tests/test_mcp_network.py tests/test_mcp_services.py tests/test_mcp_intelligence.py tests/test_mcp_remote.py` | 90 passed initially; **93 passed** after smoke hardening |
| Bedrock: `tests/test_bedrock.py tests/test_bedrock_smoke.py tests/test_expectation_compiler.py tests/test_clarification.py tests/test_compilation_lifecycle.py tests/test_mismatch_investigator.py tests/test_aws_preflight.py` | 279 passed; no AWS requests |
| Agent/trust: `tests/test_agent.py tests/test_agent_api.py tests/test_agent_sessions.py tests/test_trust.py tests/test_orchestration_budgets.py tests/test_orchestration_eval.py tests/test_data_minimization.py tests/test_production_conversations.py tests/test_production_security.py` | 259 passed |
| Alexa: `tests/test_alexa.py tests/test_alexa_dependencies.py` | 81 passed; targeted run 106 upstream warnings |
| OAuth/providers: `tests/test_connected_accounts.py tests/test_microsoft_provider.py tests/test_provider_sync.py tests/test_source_planning.py tests/test_source_correlation.py` | 143 passed; includes Google/Gmail/calendar cases, not just Microsoft |
| Ring/Bee (initial): `tests/test_adapters_and_simulators.py tests/test_simulator_authorization.py tests/test_simulator_ingestion.py tests/test_bee_cli_bridge.py` | 35 passed; no separate `test_bee_cli_connector.py` exists; connector coverage is in bridge/authorization suites |
| Monitoring/notifications: `tests/test_monitoring.py tests/test_automatic_tracking.py tests/test_operational_data.py tests/test_operations.py` | 113 passed, including persisted outbox/inbox and retries/concurrency |
| Audit/release: `tests/test_audit_history.py tests/test_evidence_pipeline_acceptance.py tests/test_release_journey.py tests/test_deployment_readiness.py tests/test_deployment_probe.py tests/test_backup_restore_smoke.py` | 44 passed |
| Provenance regression: `tests/test_evidence.py tests/test_audit_history.py tests/test_simulator_ingestion.py tests/test_automatic_tracking.py` | 69 passed after fix |
| Bee hardening: `tests/test_bee_cli_bridge.py tests/test_simulator_authorization.py tests/test_adapters_and_simulators.py tests/test_data_minimization.py` | 42 passed, including expired credential/candidate, unrelated todo and publication lock regressions |
| Final fixture check: `tests/test_bee_cli_bridge.py` | 9 passed on the final source |
| `.venv/bin/pytest -q --tb=short` (final, security-updated dependencies) | **1,332 passed, 0 failed, 0 skipped, 0 xfailed, 104 warnings; 61.07 s** |
| `.venv/bin/ruff check app db/scripts tests alembic ../scripts` | PASS |
| `.venv/bin/mypy app --ignore-missing-imports` | PASS, 159 source files |
| Expanded strict mypy command below | PASS, 38 source files |
| `.venv/bin/bandit -q -r app -ll` | PASS, existing medium/high policy |
| `.venv/bin/python -m pip check` | PASS, no broken requirements |
| `.venv/bin/pip-audit --progress-spinner off` | Initial 2 findings; after fixed install PASS, no known vulnerabilities |
| `python3 scripts/secret_scan.py` (root) | PASS Git history + nonignored source: 0 findings; pinned Gitleaks v8.30.1 Docker, network disabled, no host mounts |
| Standalone `gitleaks` | Not installed; no separate command claimed. Actual Gitleaks execution is through the repository scanner above |
| `.venv/bin/python db/scripts/orchestration_eval.py` | PASS synthetic agreement **26/26**, zero model calls, 199 cache hits/1 normalization across 200 unchanged records; 26 human reviews/live model/provider gates remain BLOCKED |
| `.venv/bin/python db/scripts/production_smoke.py` with isolated TEST_DATABASE_URL | PASS all six offline groups: API/six contracts, Streamable/ownership, signed Alexa dialogue, durable state, confirmed capture/provider/notification recovery, source/correlation/budgets; external acceptance explicitly NOT RUN |
| `node --version`; `npm --version` | v24.19.0 / 11.17.0 |
| `npm ci --ignore-scripts` (frontend, after security lock update) | PASS, clean locked install; no lifecycle scripts executed |
| `npm run test` (frontend, final) | **257 passed, 1 skipped, 0 failed**; 22 files passed/1 skipped |
| `npm run lint` | PASS |
| `npm run typecheck` | PASS |
| `NEXT_PUBLIC_API_BASE_URL=https://api.counton.invalid npm run build` | PASS, Next.js 16.4.2 optimized production build/routes/proxy; no provider secrets needed |
| `npm audit --omit=dev`; `npm audit --audit-level=high` | Initial critical/high findings; after fixes both PASS, **0 vulnerabilities** |
| Agent Skill YAML name/description/reference structural check | PASS; official `skills-ref` is not installed; host discovery/use not claimed |
| `git diff --check` | PASS after source/docs changes |

Strict command, from `backend/`:

```sh
.venv/bin/mypy --strict --follow-imports=silent --ignore-missing-imports \
  app/ai app/agent app/alexa app/mcp/compiler.py app/mcp/intelligence.py \
  app/mcp/conversation_state.py app/mcp/schemas.py app/api/v1/agent.py \
  app/api/v1/alexa.py app/schemas/compiler.py app/schemas/clarification.py \
  app/schemas/investigation.py app/schemas/trust.py app/services/compiler_service.py \
  app/services/investigation_service.py app/services/investigator_service.py \
  app/services/agent_audit.py db/scripts/bedrock_smoke.py
```

Exact security installs were `.venv/bin/python -m pip install -c constraints.txt certifi==2026.10.19 opentelemetry-api==1.45.1`, `npm install --ignore-scripts 'next@^16.4.1' 'eslint-config-next@^16.4.1'` (resolved 16.4.2), and `npm update --ignore-scripts vite` (resolved 8.3.5). No broader dependency replacement was performed.

Command diagnostics were kept outside the repository under `/tmp/counton-final/`; these temporary logs are not committed test artifacts. Early operator invocations used nonexistent test names or the repository root instead of component working directories and ran no tests; corrected commands above were then executed. Initial sandbox advisory/Docker/local-database attempts failed infrastructure access and were retried with scoped access. An automatic migration review initially rejected the target as ambiguous; inspection proved `Settings.database_url` selects `LOCAL_DATABASE_URL` for `DATABASE_TARGET=local` and Alembic uses it, after which the same isolated command was approved. No restriction was bypassed or production target used.

## H. Warnings and verification limits

- The final backend run has 104 ASK upstream deprecation warnings (`datetime.utcnow`, naive certificate validity properties); a separate targeted run had 106. Cryptographic verification is still enabled and tested. Warnings were not filtered out to achieve green.
- Python 3.14 local checks do not establish Linux/Python 3.12 runtime compatibility. The 3.12 syntax check and unchanged CI target are narrower evidence. Hosted CI was not queried: gh is unavailable and no new SHA was pushed.
- The one frontend skip is `tests/mcp-live.test.ts`, explicitly requiring `COUNTON_MCP_URL` and `COUNTON_MCP_TEST_ACCESS_TOKEN`. It is not an ordinary test silently disabled. The local real-HTTP MCP tests pass separately.
- No AWS invocation, current Supabase signup/session issuance, Amazon login, real Gmail/Outlook/calendar consent, ASK console/Echo, email send, Bee CLI account read, live webhook or deployment probe was performed here. No previous report's live observation is promoted to a current PASS.
- Rate limits/metrics are process-local; edge/shared fleet policies and operational export require deployment review. Conversation storage must be PostgreSQL in production. Provider polling and worker delivery need separate supervision; `/health` alone does not prove those processes run.
- Bee real-account schema/version/data access and local credential lifecycle require optional manual acceptance; a paired connector is a user-authorized local bridge, not provider-attested hardware. Full recommendations remain incomplete. Direct un-ticketed MCP capture is intentionally non-idempotent; do not automatically retry an ambiguous write.
- One root `.gitignore` covers env/cache/build/credential artifacts while preserving samples/examples. No nested backend/frontend gitignore or root package lock was created; no tracked generated/env secret files were found. Existing `.dockerignore` files and source assets remain.
- Markdown source searches and changed-file links/fences were reviewed; the local-file link/fence check passed and all 54 acceptance rows were structurally checked. Dated historical test counts, branch names and previous live failures were retained as history; the root/readiness entry points now point here. There is no configured Markdown linter claimed as run.

## I. Live acceptance still required

The following is a **human plan, not actions executed in this pass**. Use dedicated owned demo accounts/data and record safe run IDs/results. Keep bearer tokens, DB URLs and provider secrets out of commands/history/screenshots/logs. Enter credentials through approved secret stores/hidden prompts. Inspect persisted rows using authenticated API/UI or a private SQL client, never printed access tokens.

### Runtime configuration and processes

All API/MCP/provider/monitoring/notification processes use the **same approved Supabase database** and backend settings:

- `ENVIRONMENT=production`, `DATABASE_TARGET=supabase`, private TLS `SUPABASE_DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`; `ALLOWED_ORIGINS` is a JSON array of exact HTTPS frontend origins, no trailing slash.
- `MCP_PUBLIC_URL=https://<approved-MCP-host>/mcp`, `MCP_HOST=0.0.0.0`, intended `MCP_PORT`; `MCP_ALLOWED_ORIGINS` only if a browser client requires them. Server-side Next uses `COUNTON_MCP_URL`; these are different settings on different processes.
- Shared private `COUNTON_CLARIFICATION_SIGNING_KEY`, `CONVERSATION_STORE_BACKEND=postgres`, shared private `CONVERSATION_ENCRYPTION_KEY` (32-byte encoded AES key). No bearer token belongs in stored conversation state.
- `BEDROCK_ENABLED=true`, `AWS_REGION=us-east-2`, `BEDROCK_MODEL_ID=openai.gpt-oss-120b-1:0`; optional `BEDROCK_COMPILER_MODEL_ID`/`BEDROCK_INVESTIGATOR_MODEL_ID`, max-token/temperature/request/operation timeout/retry/concurrency/total-token budgets from `backend/production.env.sample` and `bedrock.env.sample`. Runtime credential provider/IAM must permit only intended model invocation; no frontend AWS credentials or invented BEDROCK_API_KEY.
- Actual `ALEXA_SKILL_ID`, `ALEXA_OAUTH_CLIENT_ID`, matching `OAUTH_ALLOWED_CLIENT_IDS` JSON array, `ALEXA_REQUIRE_CONFIRMATION=true`. Supabase native OAuth client secret belongs only in its trusted console and ASK account-link settings.
- Delegated provider settings: `GOOGLE_INTEGRATIONS_ENABLED`, `GOOGLE_CLIENT_ID`, private `GOOGLE_CLIENT_SECRET`, exact `GOOGLE_REDIRECT_URI`; `MICROSOFT_GRAPH_ENABLED`, `MICROSOFT_CLIENT_ID`, private `MICROSOFT_CLIENT_SECRET`, `MICROSOFT_TENANT_ID`, exact `MICROSOFT_REDIRECT_URI`; shared private `INTEGRATION_TOKEN_ENCRYPTION_KEY`.
- `PROVIDER_SYNC_ENABLED=true`, bounded interval/retention; optional `PROVIDER_WEBHOOK_URL`, `GMAIL_PUBSUB_TOPIC`, `GMAIL_PUBSUB_AUDIENCE`, `GMAIL_PUBSUB_SERVICE_ACCOUNT` only after verified push setup.
- `MONITORING_ENABLED=true`, poll/lease/backoff; opt-in `NOTIFICATION_EMAIL_ENABLED` and private key/verified sender/`FRONTEND_PUBLIC_URL` only after email acceptance. The in-app inbox works without email. Protect `OPERATIONS_METRICS_TOKEN`; do not expose metrics publicly without its boundary.
- Vercel public: `NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`, `NEXT_PUBLIC_APP_URL`. Server-only: `COUNTON_MCP_URL`. Optional Amazon: backend `AMAZON_AUTH_ENABLED`/`AMAZON_CLIENT_ID`, frontend `NEXT_PUBLIC_AMAZON_AUTH_ENABLED` only after actual custom provider acceptance. Optional native Alexa consent public identifiers: `NEXT_PUBLIC_ALEXA_OAUTH_CLIENT_ID`, `NEXT_PUBLIC_ALEXA_REDIRECT_URIS` (exact comma-separated ASK redirects). Never use NEXT_PUBLIC for DB/AWS/OAuth client secrets or service-role keys.

Process commands (trusted backend image/environment):

```sh
uvicorn app.main:app --host 0.0.0.0 --port 8000
python -m app.mcp
python -m app.integrations.worker
python -m app.monitoring.worker
python -m app.notifications.worker  # only when optional email is configured/enabled
```

Use existing supervisor/Lightsail container configuration; do not invent a single combined worker process. Templates are `backend/{production,alexa,amazon-auth,bedrock,monitoring,notifications,providers}.env.sample` and `frontend/.env.example`; filled secrets stay in ignored local/runtime configuration.

### Exact 54-step acceptance plan

For readable commands below, `API`, `MCP` and `WEB` mean the **operator-approved current** HTTPS API origin, MCP URL ending `/mcp`, and frontend origin. Existing documentation lists the CountOn Lightsail API/MCP and Vercel hosts, but they were not revalidated here. Set only these nonsecret URL shell variables; no token variable should be echoed. Commands using the backend venv are run from `backend/`.

| # | Command or UI action after review | Expected result | Failure interpretation / stop condition |
| --- | --- | --- | --- |
| 1 | On the current branch, review `git diff`, all untracked source/report files and secret-scan results; manually stage the approved set and commit | One reviewed canonical source snapshot; record SHA | Unexpected deletion/secret/diff: stop, do not blanket-stage |
| 2 | Manually push `integration/counton-canonical`; inspect all jobs for that exact SHA in GitHub Actions | Backend/Python 3.12, frontend, secrets all complete green | Local success is not hosted CI; fix actual failed log before rollout |
| 3 | Private live SQL client: `SELECT version_num FROM public.alembic_version;` | Record actual canonical ancestor/head | Unknown/alternative main revision: stop for transition plan, never stamp |
| 4 | Take/verify approved backup; review migration SQL and ownership backfill, then run approved `alembic upgrade head` only for verified canonical ancestry | Head `d6a71c9e24f0`, matching schema/FKs/RLS, restore plan | Divergence/backfill/permission/lock failure: stop; no forced stamp |
| 5 | Lightsail console: deploy reviewed API image/SHA, shared backend configuration and `uvicorn app.main:app --host 0.0.0.0 --port 8000`; supervise provider and monitoring workers separately | API and workers start against intended shared DB | Startup/config/IAM/DB failure is a rollout blocker |
| 6 | `curl --fail --silent --show-error "$API/health"` | `status=ok`, `service=counton-api` | TLS/routing/process issue; liveness alone is insufficient |
| 7 | `curl --fail --silent --show-error "$API/ready"` | `status=ready` | 503: inspect safe readiness code; schema/DB mismatch, do not mask |
| 8 | Lightsail console: deploy same reviewed backend image as separate MCP service, command `python -m app.mcp`, configured public URL/Host and shared DB/keys | Separate HTTPS MCP process starts | Wrong bind/port/key/DB/Host rejects calls; no local fallback |
| 9 | `curl --fail --silent --show-error "${MCP%/mcp}/health"` | MCP liveness OK | Routing/process issue |
| 10 | `curl --fail --silent --show-error "${MCP%/mcp}/ready"` | MCP readiness ready | Different DB/schema/config; stop before writes |
| 11 | `python db/scripts/mcp_remote_smoke.py --mcp-url "$MCP" --discovery-only` with hidden current-user token prompt | Real SDK initialize succeeds | Auth/TLS/protocol/Host failure; do not substitute REST |
| 12 | Inspect same smoke result (now enforces all six nested request/object schemas) | Six canonical tools discovered | Old image/missing intelligence/flattened contract: block acceptance |
| 13 | `python db/scripts/mcp_remote_smoke.py --mcp-url "$MCP" --api-url "$API"` using dedicated demo user | Auth/list/capture/get/API cross-check/errors and exact tagged cleanup pass | Any cleanup failure: inspect only exact tagged rows; no unrelated deletion |
| 14 | On trusted runtime: `python db/scripts/aws_preflight.py --verify-identity`, then `python db/scripts/bedrock_smoke.py` with Bedrock enabled | Real harmless JSON model invocation usable; safe model/status only | Credentials/region/model/IAM/capacity failure, not a mocked PASS |
| 15 | Securely provide test token; `python db/scripts/intelligence_smoke.py --mcp-url "$MCP" --compile` | Real model returns validated compilation/clarification without persistence | Invalid structured output or invented fields blocks rollout |
| 16 | In signed-in `/alexa`, say “I'm counting on my bill being lower”; answer bill/baseline/timing | One material question at a time; facts retained, no saved row yet | Lost facts/guesses/early save is a defect |
| 17 | Run `python db/scripts/intelligence_smoke.py --mcp-url "$MCP" --api-url "$API" --capture` with secure token | Compiled tagged row saved once, API sees same row, exact cleanup succeeds | Persistence/owner/replay/cleanup failure blocks acceptance |
| 18 | Vercel console: set exact reviewed public/server variables above and redeploy `frontend/` at reviewed SHA | Build uses public HTTPS API and intended MCP | Wrong public base/CORS/server URL; env changes need rebuild |
| 19 | Dedicated user: register/confirm email/login, reload/refresh, logout/login/reset; then separately execute actual Amazon consent when configured and inspect valid Supabase session/owned data | One consistent CountOn UUID; account isolation; explicit linking only | A button/translator is insufficient; no valid Supabase session means Amazon BLOCKED |
| 20 | Signed-in `$WEB/alexa`: “What am I counting on?” | Actual owned list or honest empty result, safe MCP trace | Fake rows, auth leak or cross-user data: stop |
| 21 | “Tell me about my electricity bill”; disambiguate if needed | MCP gets chosen owned UUID/status | Wrong selection or fabricated detail: stop |
| 22 | Give complete grocery expectation, review and explicitly approve | One saved row only after completion/approval | Duplicate or preapproval capture is a defect |
| 23 | Start ambiguous bill and answer several clarification turns | Correct sequential state and facts | Invented baseline/deadline or mixed draft is a defect |
| 24 | During draft: “Actually make that $150” | Only relevant amount changes; confirmation matches it | Reset/contradictory facts/early write: reject |
| 25 | Separate draft: “Never mind”; try stale reply/refresh | Draft cancelled; no row and no replay capture | Persisted cancelled/incomplete draft is a defect |
| 26 | Open saved expectation in normal dashboard, refresh and reread through MCP | Same ID/claim/current persisted data | Different DB/owner/local demo state: block |
| 27 | Dedicated tagged bill expectation below 150: submit explicit demo amount 180 using owned evidence API/UI; evaluate once with stable key | Real SQL evidence/evaluation MISMATCH; one inbox alert | Model/frontend outcome or untagged fake provider provenance is unacceptable |
| 28 | Select it and ask “Why did it fail?” | Owned latest mismatch routes to explanation tool | Wrong expectation/evaluation selection: stop |
| 29 | Compare speech with saved evaluation/evidence and safe provenance | Only supported facts, correct evidence IDs internally; no external invented cause | Uncited/unsupported cause: reject; safe insufficient-evidence fallback is honest |
| 30 | Prepare owned MATCH with real demo fact; ask Why | Says matched; no investigator/model explanation call | Investigating MATCH or new alert is a defect |
| 31 | Prepare owned UNKNOWN (no useful/stale/conflicting fact); ask Why | Waiting/uncertainty; no investigator call or mismatch alert | Unknown converted to failure/success: reject |
| 32 | Integrations → Google email; registered OAuth client/callback; consent to necessary read scopes only | State/PKCE verified, encrypted owned grant, real connected state | Metadata-only record is not connected; invalid/missing scope fails closed |
| 33 | Trigger Gmail sync; inspect initial Inbox records and then a new relevant message/history increment | Minimal authorized facts/checkpoint; exact sender/thread/order IDs | Whole inbox archival/wrong folder/duplicate publication/cursor gap must be fixed |
| 34 | Authorize/select Google Calendar; bind exact UID/occurrence; modify/cancel dedicated event and sync | Normalized selected occurrence, correct persisted evaluation | Title-only matching/wrong occurrence/timezone is a defect |
| 35 | Disconnect Google, attempt later import, then explicitly reconnect/reauthorize/rebind | Old grant/bindings cannot publish; reconnect gets fresh authority | Continued old-authority import is a security blocker |
| 36 | Integrations → Microsoft email; Entra registered POST callback and explicit consent | Stable verified account/scopes and encrypted grant | Wrong account, invalid state/redirect or email metadata alone is not success |
| 37 | Sync Outlook Inbox initial/delta, then add relevant message | Owned minimal evidence/checkpoint; replay-safe SQL | Sent/draft/spam or unrelated source association: reject |
| 38 | Authorize Microsoft Calendar; select default/nondefault as applicable, edit/cancel exact occurrence and reconcile | Supported default delta/nondefault window behavior, correct chronology | Unsupported endpoint or wrong selected calendar is a defect |
| 39 | Disconnect/reconnect Microsoft; test expired/revoked grant | Imports stop; auth-required/UNKNOWN safely shown; fresh consent needed | Cached credential/source reuse is a blocker |
| 40 | Confirm a real source binding for tagged expectation; let provider worker synchronize and monitoring worker run | Source → bounded fact → SQL evidence → wake → deterministic SQL result | Manual/frontend-predicted outcome does not certify automatic path |
| 41 | Repeat mismatch event/sync/job retry and inspect notifications/audit | One alert for same mismatch episode, linked evidence/result | Duplicate inbox/delivery after retry: reject |
| 42 | Produce supported MATCH and then insufficient evidence for another expectation | MATCH silent; UNKNOWN keeps monitoring; no spurious mismatch | Incorrect alert/state authority: reject |
| 43 | ASK Developer Console → existing CountOn Custom Skill → English (US), invocation `count on`; copy real skill ID to backend | IDs/model belong to intended account/skill | Native Alexa+ onboarding is not a substitute and is not required here |
| 44 | ASK Build → Endpoint → HTTPS → `$API/api/v1/alexa`, correct actual CA certificate option | Signed fulfillment reaches adapter; unsigned request rejected | `/mcp`/Vercel URL or disabled verification is invalid |
| 45 | Supabase OAuth server: Authorization Path `/oauth/consent`, confidential Alexa client/exact ASK redirects; ASK account linking code grant, Basic client auth, S256 and approved `openid` scope | Authorization `$SUPABASE_URL/auth/v1/oauth/authorize`, token `$SUPABASE_URL/auth/v1/oauth/token`; issued/refreshed access token passes issuer/aud/role/sub/client checks | Incompatible issuance/refresh/consent is BLOCKED; do not weaken JWT checks or use LWA token |
| 46 | Upload `backend/app/alexa/interaction-model.en-US.json` in ASK JSON editor; Save Model → Build Model | Model validates with implemented intents and elicitation | Console rejection requires fixing actual schema/utterances, no claimed acceptance |
| 47 | ASK Test → Development; enable/link skill under intended account | Testing and CountOn consent grant active | Wrong account/client/token causes linking failure |
| 48 | ASK simulator: open, list, capture ambiguous bill, answer, correct, explicitly yes, get/Why; cancel a separate draft | Natural concise replies, one shared row, signatures/replay and <voice budget behavior | Unsigned fixture tests do not replace console; latency/recognition is a live blocker |
| 49 | Physical Echo under linked account: repeat core conversation and dashboard cross-check | Actual voice capture/clarification/confirmation/Why works | No device interaction means Echo remains unverified |
| 50 | Dashboard `/demos` → Ring simulator on explicitly approved owned source; send stable package observation, replay, then separate no-detection | SQL positive observation yields supported result; replay deduped; no-detection alone UNKNOWN | Fake hardware claim/wrong target/absence failure: reject |
| 51 | `/demos` → Bee simulator on approved expectation; landlord/plumber promise; optional separately approved explicit observed outcome | Commitment context persisted; promise alone UNKNOWN; actual backend result shown | Promise-as-fulfillment or local verdict is a defect |
| 52 | Inspect simulator labels, evidence timeline and Audit History for both | SIMULATED_RING/SIMULATED_BEE visibly distinct from genuine imports | Any live-hardware claim is unacceptable; Bee CLI optional acceptance separate |
| 53 | Supervised test deployment: restart API/MCP/provider/monitoring processes during tagged work; replay event/request and resume | Durable conversations/jobs recover; stale leases fenced; no duplicate capture/alert | Lost state/double side effect is a release blocker; never crash production indiscriminately |
| 54 | Run the three-minute demo below against dedicated data, record safe evidence/results and clean up exact test rows only | End-to-end observed behavior with honest live/simulated labels | Failed prerequisite means use clearly labeled backup simulator plan, not a success claim |

Google callback is `/api/v1/integrations/oauth/google/callback` (GET); Microsoft is `/api/v1/integrations/oauth/microsoft/callback` (POST). CountOn auth callback is `$WEB/auth/callback`; Amazon's allowed return is the actual project `/auth/v1/callback`, not the backend UserInfo route. Configure optional `custom:amazon` with `profile:user_id` and the narrow backend `/api/v1/auth/amazon/userinfo` adapter as documented in [authentication](authentication.md). Verify a real Supabase session and explicit existing-account link/unlink separately; never merge accounts solely by email. Use only exact approved origins/redirects, not wildcard previews.

### Three-minute demo and fallback

- **0:00–0:45:** Show dashboard/real signed-in user; ASK “open count on,” list; start an ambiguous electricity expectation and answer questions. Confirm explicitly and show the same saved ID through dashboard refresh. If ASK is not accepted, use `/alexa` and clearly call it the CountOn web demo.
- **0:45–1:35:** Show tagged explicit bill evidence 180 against limit 150, real deterministic MISMATCH, one inbox alert, and ask Why. If Bedrock is unavailable, show the truthful grounded fallback, not invented cause/model success.
- **1:35–2:20:** Show exact package/source association and a clearly simulated Ring positive observation; demonstrate missing detection does not prove failure. MATCH stays quiet.
- **2:20–3:00:** Send clearly simulated Bee landlord/plumber commitment; show persisted context and UNKNOWN rather than fulfillment. Show minimal audit links and safe trace. End with model/transport/state authority boundaries and current live blockers.

Backup mode uses dedicated simulator APIs and persisted SQL with explicit demo labels. It must not present mocked model responses, local fixture tests, simulated events or the web voice toggle as live AWS/ASK/Echo/provider acceptance.

## J. Deployment readiness

**NOT READY FOR DEPLOYMENT** as an unconditional production release claim.

The canonical code is locally green with no known startup/build/test blocker remaining in the verified environment. The explicit remaining gates are:

1. **Blocking:** actual production Alembic revision/schema/backup and approved migration or transition plan are unknown. Never infer them from historical reports.
2. **Blocking for real Alexa demo:** current hosted Python 3.12 CI, exact deployed images/readiness/six-tool contracts, native Supabase Alexa OAuth access-token/refresh compatibility, real Bedrock availability and seven-second ASK latency require acceptance. No console/device/cloud action was run here.
3. **Blocking for live integrations:** email/Amazon session and delegated Google/Microsoft consent/sync/webhook/email delivery need actual authorized account verification. Optional Bee CLI is separately blocked on installed compatible CLI and authenticated user data. Ring/Bee remain simulated by design.

After code review, the human may follow I in order to clear these gates. This verdict does not mean local implementation is failing or invite a replacement architecture. Shared edge limiting, metrics export, deployed retention and backup/key recovery are operational follow-ups; broad recommendations and excluded integrations are not fabricated release features.

## K. Exact Git status

```text
 M .github/workflows/ci.yml
 M README.md
 M backend/app/agent/README.md
 M backend/app/api/v1/agent.py
 M backend/app/api/v1/evidence.py
 M backend/app/services/bee_connector_service.py
 M backend/constraints.txt
 M backend/db/README.md
 M backend/db/scripts/mcp_smoke.py
 M backend/requirements.txt
 M backend/tests/test_adapters_and_simulators.py
 M backend/tests/test_agent_api.py
 M backend/tests/test_bee_cli_bridge.py
 M backend/tests/test_evidence.py
 M backend/tests/test_mcp_remote.py
 M docs/agent-skill.md
 M docs/bee-ring-integration-acceptance.md
 M docs/data-minimization-and-audit-policy.md
 M docs/hackathon-acceptance.md
 M docs/mcp.md
 M docs/production-readiness.md
 M frontend/README.md
 M frontend/app/(workspace)/activity/page.tsx
 M frontend/app/(workspace)/expectations/[id]/page.tsx
 M frontend/app/(workspace)/expectations/new/page.tsx
 M frontend/app/(workspace)/expectations/page.tsx
 M frontend/app/(workspace)/integrations/page.tsx
 M frontend/app/(workspace)/settings/page.tsx
 M frontend/app/alexa/page.tsx
 M frontend/components/expectation.tsx
 M frontend/components/integration.tsx
 M frontend/components/notification.tsx
 M frontend/docs/alexa-demo.md
 M frontend/docs/mcp-client.md
 M frontend/lib/agent/contracts.ts
 M frontend/lib/api.ts
 M frontend/lib/manual-expectation.ts
 M frontend/lib/presentation.ts
 M frontend/lib/types.ts
 M frontend/package-lock.json
 M frontend/package.json
 M frontend/tests/agent-route.test.ts
 M frontend/tests/alexa.test.tsx
 M frontend/tests/api.test.ts
 M frontend/tests/creation.test.tsx
 M frontend/tests/mcp-live.test.ts
 M frontend/tests/presentation.test.ts
 M frontend/tests/screens.test.tsx
?? docs/consolidation-inventory.md
?? docs/consolidation-manifest.json
?? docs/consolidation-report.md
?? docs/final-engineering-audit.md
?? frontend/app/(workspace)/settings/integrations/
?? frontend/components/reality-decision-card.tsx
?? frontend/components/resolution-panel.tsx
?? frontend/tests/reality-decision-card.test.tsx
?? frontend/tests/resolution-panel.test.tsx
```

## L. Suggested commit message

```text
Harden canonical CountOn provenance, MCP acceptance and release validation

Preserve consolidated architecture and UI; fix historical result presentation
and local deadlines, require six-tool smoke contracts, update vulnerable
runtime/build dependencies, and document local evidence and live release gates.
```

Suggested only. No commit, push, deployment or production migration was performed.
