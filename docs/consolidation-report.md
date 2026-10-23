# Canonical CountOn consolidation — 2026-10-23

## Outcome and base

`integration/counton-canonical` uses `feature/alexa-mcp` commit `8d4b72f` as its
base. The initial worktree was clean. Local safety branch
`backup/pre-consolidation-2026-10-23` points to the unchanged base. No commits,
pushes, deployments, cloud settings, credentials, or production migrations were
performed. This is a selective snapshot consolidation, not a claimed git-history
merge of the ZIP archives.

The newer existing tree already contains the integrated backend, controlled
orchestrator, six MCP tools, ASK adapter, typed Bedrock compiler/clarification,
grounded investigator, encrypted provider sync, monitoring, notifications, Bee
bridge, simulator APIs, Supabase auth and privacy controls. It is retained.

[Before-change inventory and subsystem matrix](consolidation-inventory.md) and
[per-path decisions with SHA-256 and migration graph inputs](consolidation-manifest.json)
record the comparison. The five archives were read independently of stale local
feature refs. The Alexa and Ring/Bee archives are identical after normalizing their
top-level directory and excluding macOS/build/cache artifacts. They are one source.

## Files brought in

### Shared Alexa/Ring source

New files:

- `frontend/app/(workspace)/settings/integrations/page.tsx`: alias of the existing
  authenticated Connections page.
- `frontend/components/reality-decision-card.tsx`: persisted expectation/evidence/
  evaluator display, adapted to preserve UNKNOWN, materiality, and true provenance.
- `frontend/components/resolution-panel.tsx`: existing authenticated lifecycle
  update and explanation navigation, with terminal-state behavior preserved.
- `frontend/tests/reality-decision-card.test.tsx` and
  `frontend/tests/resolution-panel.test.tsx`: applicable source tests plus privacy/
  evaluator regressions. The archived fake AI-suggestion assertion is not imported.

Overlapping source files combined with the canonical implementation:

- `frontend/app/(workspace)/activity/page.tsx`: category filters; existing minimal
  six-column persisted Audit History retained.
- `frontend/app/(workspace)/expectations/page.tsx`: source/type/deadline/search/sort
  controls, preserving backend-derived statuses.
- `frontend/app/(workspace)/expectations/new/page.tsx`: existing source criteria
  builder, presets, optional baseline/deadline and preview/confirmation. Labels,
  simulator source names and existing manual safety guidance retained.
- `frontend/app/(workspace)/expectations/[id]/page.tsx`: result/resolution panels;
  Ring/Bee submission uses the existing source-bound simulator API.
- `frontend/app/(workspace)/integrations/page.tsx`,
  `frontend/app/(workspace)/settings/page.tsx`: source management and existing
  notification-preference controls.
- `frontend/app/alexa/page.tsx`: owned expectation deep links, existing auth gate,
  discovery, continuation and safe traces.
- `frontend/components/expectation.tsx`, `integration.tsx`, `notification.tsx`:
  structured summaries, truthful connection metadata, simulator setup and Why links.
- `frontend/lib/api.ts`, `types.ts`, `manual-expectation.ts`,
  `lib/agent/contracts.ts`: typed existing API adapters and optional selection.
- `frontend/tests/api.test.ts`, `alexa.test.tsx`: simulator-route regression cases
  and the required navigation mock.
- `backend/tests/test_adapters_and_simulators.py`: three existing source regression
  cases for below-baseline, below-materiality and genuine numeric mismatch.
- `backend/app/api/v1/agent.py`: only the optional typed expectation selection is
  ported. Existing remote MCP adapter and ownership enforcement remain intact.

Additional consolidation regression/doc changes:

- `backend/tests/test_agent_api.py`: own/foreign expectation deep-link coverage.
- `frontend/tests/agent-route.test.ts`: typed selection forwarding without identity.
- `frontend/tests/creation.test.tsx`, `presentation.test.ts`: confirmation, simulator
  source, explicit baseline/deadline and invalid-input checks.
- `frontend/tests/screens.test.tsx`: exact persisted observation count updated for
  the two additional result panels; audit and security assertions retained.
- Root/frontend/agent READMEs and frontend Alexa/MCP docs: canonical integration
  and the optional selection contract.
- This report, the before-change inventory and machine-readable manifest.

### Main source

No alternative main backend files were installed. Its useful OAuth/token rotation,
Gmail/Outlook/calendar synchronization, retry/health and delivery-queue behaviors
already have stronger integrated equivalents, listed in the inventory. Importing
its ORM/services would create two credential paths, two delivery queues and a
provider calendar archive. Current owner checks, PKCE, OAuth generations, bounded
fact projections and lease/retry/deduplication tests remain canonical.

### Backend reality-engine source

Used as semantic/reference input for persistence, validation, evaluator outcomes,
API contracts and tests. No older application files replace current code. The
current deterministic evaluators and all historical migrations remain byte-for-byte
unchanged.

### Bedrock intelligence source

No parallel AI implementation installed. `ai/compiler.py`, `investigator.py`,
`time_parser.py`, `ai/models/*` duplicate current typed services. The older time
parser guesses a 30-day billing deadline; the current grounded compiler clarifies
instead. Context helpers default to mock mode based on credential environment
variables and can return exception details. Quality/recommendation stores are
global, seeded and unowned; they do not constitute real user-derived discoveries.
The duplicate `frontend/app/lib/*` and developer scripts under `app/db/` also stay
out. Existing stronger equivalents remain in `app/ai/`, owned services and
`backend/db/scripts/`.

## Non-trivial conflict decisions

| File(s) | Sources | Decision and reason |
|---|---|---|
| `backend/app/api/v1/agent.py` | current / Alexa-Ring | Accept optional UUID selection and let the existing MCP services enforce ownership. Reject the archived local-adapter fallback, which changes the remote Streamable HTTP path. Do not expose raw row metadata or fetch business rows in the transport. |
| `backend/app/ai/mismatch_investigator.py` | current / Alexa-Ring / Bedrock | Keep current model-failure/fallback behavior. Archived disabled-model rate/usage drafting changes product explanation semantics and has no corresponding added grounding tests. |
| `backend/app/schemas/clarification.py` | current / Alexa-Ring | Keep current validated state/typing; the cast-only archive change is not needed by passing Mypy. |
| `backend/app/integrations/bee/cli_bridge.py` | current / Alexa-Ring | Keep secure configured local credential location. The alternate fallback to the current directory when home resolution fails is not required for consolidation. |
| `backend/db/scripts/_demo.py` | current / Alexa-Ring | Keep current observation ordering; do not alter demo/evaluator input semantics as a merge side effect. |
| `frontend/components/ai-recommendations.tsx`, `ai-suggestions.tsx` | Alexa-Ring only | Exclude seeded claims presented as connected-account discoveries and static advice labeled Bedrock-generated. Their callers and fake assertions are excluded too. No existing canonical functionality is removed. |
| `frontend/tests/integration-flow.test.tsx` | Alexa-Ring only | Do not port assertions that call mocked functions directly as proof of backend persistence, expect Bee context to be MISMATCH, or require fabricated recommendations. Canonical PostgreSQL/HTTP tests and new UI regressions provide actual integration evidence. |
| `frontend/components/reality-decision-card.tsx` | Alexa-Ring + current policy | Display persisted reasoning rather than calculating a raw comparison that ignores tolerance or maps UNKNOWN to FALSE. Source names alone cannot mark live Bee imports simulated or user facts verified. |
| `frontend/components/expectation.tsx`, `integration.tsx` | Alexa-Ring + current policy | Use stored simulation/provenance and credentials/status metadata. Avoid claims that every delivery record already read Amazon email or that every error is a token failure. Simulated connections request no fake live scopes. |
| `frontend/components/resolution-panel.tsx` | Alexa-Ring + current lifecycle | Retain authenticated PATCH behavior, display no active resolution controls for resolved/cancelled rows, and keep untrusted selection separate from user identity. |
| `frontend/app/(workspace)/expectations/[id]/page.tsx` | current / Alexa-Ring | Retain source authorization by calling dedicated Ring/Bee ingestion endpoints; reuse their actual evaluation response, not browser predictions. |
| `frontend/app/(workspace)/expectations/new/page.tsx`, `lib/manual-expectation.ts` | current / Alexa-Ring | Preserve explicit preview approval and backend source names; reject malformed optional inputs rather than silently dropping them. Do not infer fields from arbitrary prose in the browser. |
| `frontend/app/(workspace)/demos/page.tsx` | current / Alexa-Ring | Keep current simulator. Archived launcher bypasses dedicated simulator authorization and appends hard-coded bill/delivery/cancellation verdict narratives to arbitrary backend responses. |
| `frontend/hooks/use-resource.ts`, dashboard refresh | current / Alexa-Ring | Keep navigation/request cancellation, surfaced errors and current refresh semantics. Do not carry unrelated prior resource data across changed loaders or swallow evidence failures as empty results. |
| `frontend/app/(workspace)/activity/page.tsx` | current / Alexa-Ring | Add category filtering while retaining minimal persisted audit fields and exact live/simulated source attribution. |
| `frontend/app/alexa/page.tsx`, notification/result Why links | current / Alexa-Ring | Port expectation selection through the trusted server; links use the generic question and ID, avoiding private claim text in URLs. Existing auth/trace/conversation behavior preserved. |
| Archive `AGENTS.md`, `CLAUDE.md`, subproject `.gitignore` | source-only | Generated coding instructions and duplicate ignore files are not application functionality. Root ignore and established project instructions remain canonical. |
| Main OAuth/calendar/delivery migration and service families | main / current | Preserve one owner-constrained connection, encrypted grant, normalized evidence, sync and delivery system. Specific alternative schema conflicts are recorded below and in the inventory. |

Every changed/unique path has a source hash and retain/combine/reject decision in
the manifest. Unchanged source files were compared by content and need no conflict
resolution.

## Alembic

All source migrations were collected and their revision/down-revision graph
inspected. Canonical chain has 13 revisions and exactly one head,
`d6a71c9e24f0`. `alembic heads`, `alembic history` and **local test database**
`alembic current` pass. Existing migration round-trip and metadata checks pass.

Main's nine additional migrations form two branches from `5d201f68ac90`; they are
not additive branches of this application's schema. Two OAuth credential/state
creation paths conflict with each other; an alternative notification-delivery
creation conflicts with canonical `ac746eb3f145`. Nullable standalone monitoring
conflicts with canonical expectation ownership; generic calendar persistence is
superseded by privacy-bounded projections. They were not copied into the live
migration directory, deleted from the archives, renumbered, rewritten, or stamped
as applied. A merge revision cannot fix duplicate DDL or incompatible ORM layouts.

A database already at one of those main-only revision IDs needs a separately
reviewed migration/credential transition. Do not deploy by stamping it to the
canonical head. No production database was queried or changed.

## Dependencies, configuration, and junk

No dependency manifest, constraint, package lock or historical migration changed.
Alexa/Ring dependency files match the current tree. Older source dependencies for
rejected parallel Google/AI/crypto layers are unnecessary. Existing secret-free
Bedrock, API, MCP, ASK, Amazon auth, provider, monitoring and frontend templates are
retained. The source frontend template adds no variable names beyond current.
Ignored `.env.local` files were not copied or printed.

No tracked files were deleted. `__MACOSX`, `.DS_Store`, caches, generated build
output and secret env files were excluded from review/import. The original ZIPs
remain intact. No root `package-lock.json` exists; `frontend/package-lock.json`
remains unchanged. Root `.gitignore` remains authoritative.

`investigator_service.py` is retained as the owner-scoped database orchestration
boundary; `investigation_service.py` is retained as the pure grounding/model
boundary. They are not duplicate implementations.

## Architecture and acceptance

```text
Supabase Auth -> authenticated CountOn user / bearer JWT
  Next.js dashboard -> FastAPI -> owned services -> PostgreSQL
  /alexa -> Next.js /api/agent -> FastAPI controlled orchestrator
    -> authenticated MCP SDK Streamable HTTP -> same owned services
  ASK signed request + linked Supabase identity -> same orchestrator/MCP

Bedrock Runtime -> typed compilation / canonical clarification / grounded explanation
Approved connections + source bindings -> normalized facts -> evidence
PostgreSQL workers -> deterministic MATCH / UNKNOWN / MISMATCH
  -> persisted evaluation -> deduplicated in-app/optional configured delivery
```

The six unchanged tools are `capture_expectation`, `get_expectation`,
`list_expectations`, `compile_expectation`, `continue_expectation_compilation`,
`explain_expectation_mismatch`. Every MCP call retains `{ "request": { ... } }`.
No second compiler, investigator, schema hierarchy, auth authority, connector
store, or agent framework was introduced.

| Status | Category | Evidence |
|---|---|---|
| 🟡 Implemented/tested, not live verified | Core SQL/ownership/evaluation/monitoring | Full backend suite with isolated PostgreSQL |
| 🟡 Implemented/tested, not live verified | MCP Streamable HTTP and six contracts | Real local protocol/HTTP/auth tests; public deployment not probed |
| 🟡 Implemented/tested, not live verified | Bedrock compiler/clarification/investigator | Typed mocked inference/grounding tests; no real AWS inference in this pass |
| 🟡 Implemented/tested, not live verified | ASK adapter and interaction model | Signed local fixture requests; no ASK console or physical Echo test |
| 🟡 Implemented/tested, not live verified | Supabase email/password and supported Amazon provider path | Existing auth/session/ownership tests; no real signup/Amazon consent in this pass |
| 🟡 Implemented/tested, not live verified | Gmail/Outlook/calendar and Bee CLI | Authorized fixture tests; real accounts not accessed |
| 🟡 Simulated and locally tested | Ring/Bee observations | Source-bound backend simulator APIs, clear provenance; no live hardware claim |
| 🟡 Implemented/tested, not live verified | Next.js dashboard, Connections, audit, Alexa conversation | Frontend regression/lint/type/build; no deployed browser acceptance |
| ❌ Not implemented/verified | Native Alexa+ developer onboarding, physical Ring ingestion | Remain external/future integration work |

No integration is newly labeled ✅ live verified by this consolidation.

## Validation performed

Commands were run using the existing `backend/.venv` and frontend `node_modules`.
No dependency installation or lock regeneration was necessary. Backend Python is
3.14 locally; CI config targets 3.12. Node is 24.19.0 locally. Dedicated loopback
`counton_test`/temporary test databases were used with `TEST_DATABASE_URL`; the
configured production database was never a target.

| Command / scope | Result |
|---|---|
| `PYTHONPYCACHEPREFIX=/tmp/counton-consolidation/pycache .venv/bin/python -m compileall -q app alembic` | PASS |
| `.venv/bin/python db/scripts/alexa_import_smoke.py` | PASS default and ctypes crypto imports |
| `.venv/bin/pytest -q tests/test_adapters_and_simulators.py tests/test_data_minimization.py` | 14 passed |
| `.venv/bin/pytest -q tests/test_agent_api.py --tb=short` | 24 passed, including new cross-user selection test |
| `.venv/bin/alembic heads` / `.venv/bin/alembic history` | PASS, single 13-revision chain |
| `ENVIRONMENT=test DATABASE_TARGET=local LOCAL_DATABASE_URL=<dedicated loopback test URL> .venv/bin/alembic current` | PASS, `d6a71c9e24f0` |
| `.venv/bin/pytest -q tests/test_mcp.py tests/test_mcp_network.py tests/test_mcp_services.py tests/test_mcp_intelligence.py --tb=short` | 64 passed |
| `.venv/bin/pytest -q tests/test_expectation_compiler.py tests/test_clarification.py tests/test_mismatch_investigator.py --tb=short` | 200 passed |
| `.venv/bin/pytest -q tests/test_alexa.py tests/test_alexa_dependencies.py --tb=short` | 81 passed; upstream ASK deprecations |
| `.venv/bin/pytest -q tests/test_microsoft_provider.py tests/test_provider_sync.py tests/test_bee_cli_bridge.py tests/test_source_planning.py tests/test_source_correlation.py tests/test_simulator_authorization.py tests/test_migrations.py --tb=short` | 143 passed |
| `.venv/bin/pytest -q --tb=short` | **1,323 passed**, 104 upstream ASK warnings |
| `.venv/bin/ruff check app db/scripts tests alembic ../scripts` | PASS |
| `.venv/bin/mypy app --ignore-missing-imports` | PASS, 159 files |
| Strict Mypy scope below | PASS, 37 files |
| `npm run test` | **253 passed, 1 existing live-MCP check skipped** (no endpoint/token) |
| `npm run lint` | PASS |
| `npm run typecheck` | PASS |
| `NEXT_PUBLIC_API_BASE_URL=https://api.counton.invalid npm run build` | PASS, 19 generated pages including settings alias |
| `.venv/bin/bandit -q -r app -ll` | PASS, no medium/high findings |
| `.venv/bin/python db/scripts/orchestration_eval.py` | PASS synthetic agreement 26/26; human/cloud/provider acceptance remains unverified |
| `python3 scripts/secret_scan.py` | PASS git/source, zero findings (Docker access required) |
| `git diff --check` | PASS |

The exact strict typing command:

```sh
.venv/bin/mypy --strict --follow-imports=silent --ignore-missing-imports \
  app/ai app/agent app/alexa app/mcp/compiler.py app/mcp/intelligence.py \
  app/mcp/conversation_state.py app/mcp/schemas.py app/api/v1/agent.py \
  app/api/v1/alexa.py app/schemas/compiler.py app/schemas/clarification.py \
  app/schemas/investigation.py app/schemas/trust.py app/services/compiler_service.py \
  app/services/investigation_service.py app/services/agent_audit.py db/scripts/bedrock_smoke.py
```

The initial system-Python compile attempt hit macOS's protected user-cache
location; rerun with the supported virtualenv and a temporary cache passed. The
first frontend run exposed archived text/layout differences; original manual safety
labels/guidance were retained and the persisted-result assertion now covers the
additional panels. All pre-existing canonical tests remain; none were disabled or
removed. Unselected archive assertions are documented above, not claimed as passes.

## Remaining manual verification and blockers

1. **Deployment migration gate:** inspect the actual deployment's Alembic revision
   before choosing any upgrade path. Main-only deployed histories need a separate
   reviewed transition. No production migration was performed.
2. **Cloud/provider acceptance:** test Supabase signup/reset/Amazon consent, ASK
   linking and real console/Echo requests, Bedrock inference, selected provider
   sync/revocation and separately authenticated optional Bee CLI with authorized
   accounts. Fixtures do not prove access or consent.
3. **Deployed UI:** verify the consolidated settings, builder, Why navigation and
   simulator flow in a real signed-in browser against the intended backend/MCP.
4. **Hosted CI:** no workflow was pushed or rerun. Local Python 3.14 validation is
   reported independently of GitHub-hosted Python 3.12 status.
5. **Existing operations:** retain the privacy policy's approval gate for cleanup
   of legacy provider data and production expiry housekeeping; this merge does not
   perform that destructive work.

Suggested commit message, after review:

```text
consolidate CountOn frontend workflows on canonical secure Alexa MCP backend
```

## Exact worktree status

No existing tracked file was deleted. New files are intentionally untracked until
review; no staging or commit was performed.

```text
## integration/counton-canonical
 M README.md
 M backend/app/agent/README.md
 M backend/app/api/v1/agent.py
 M backend/tests/test_adapters_and_simulators.py
 M backend/tests/test_agent_api.py
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
 M frontend/lib/types.ts
 M frontend/tests/agent-route.test.ts
 M frontend/tests/alexa.test.tsx
 M frontend/tests/api.test.ts
 M frontend/tests/creation.test.tsx
 M frontend/tests/presentation.test.ts
 M frontend/tests/screens.test.tsx
?? docs/consolidation-inventory.md
?? docs/consolidation-manifest.json
?? docs/consolidation-report.md
?? frontend/app/(workspace)/settings/integrations/
?? frontend/components/reality-decision-card.tsx
?? frontend/components/resolution-panel.tsx
?? frontend/tests/reality-decision-card.test.tsx
?? frontend/tests/resolution-panel.test.tsx
```
