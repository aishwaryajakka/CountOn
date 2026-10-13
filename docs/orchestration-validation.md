# Resumed orchestration validation — October 12, 2026

This records the uncommitted `feature/alexa-mcp` working tree on HEAD `e7c74ac`.
The existing changes were preserved. No commit, push, deployment, production migration,
account consent or real notification send was performed. This is local verification;
cloud/device and human-review acceptance remain blocked.

## What was retained and finished

The interrupted implementation already contained typed owned source planning,
explicit binding confirmation, stable-ID cross-source correlation, scoped normalization
caching, Bedrock routing/budgets, delivery timestamp/metric compatibility, source-review
UI and a 20-case synthetic corpus. These extend existing services, encrypted provider
projections and PostgreSQL workers. All six MCP names and nested `request` contracts
remain unchanged; no second compiler, conversation state or orchestration framework
was introduced.

Focused fixes in this resume:

- Revalidate enabled providers, read scopes, encrypted account/grant identity and local
  access/refresh usability before planning or using provider-backed evidence. Refresh
  credential identity-map state so deleted credentials cannot authorize confirmation.
  Remote revocation is detected when the provider reports it; an unreported remote
  revocation cannot be established by a read-only local preview.
- Lock and refresh account → stream → expectation records before confirmation; protect
  cancellation/deletion and preserve paused/cancelled/completed jobs and replay identity.
  `wake` refreshes the expectation before activating work.
- Align legacy Outlook polling publication to account → expectation → job lock order.
  A concurrent PostgreSQL test holds the account while another worker starts, then
  obtains the expectation with NOWAIT and cancels it. The worker finishes safely.
- Conflicting independent order arrival reports yield UNKNOWN; choosing the later
  alleged arrival is unsafe. Different reschedules, or cancellation versus reschedule,
  also yield UNKNOWN even if each record independently mismatches. Correlation policy
  `stable_sources_v2` participates in fingerprints.
- Normalize Graph UTC `originalStart` alongside Google `originalStartTime`; recurring
  instances remain matched by exact identity, never calendar titles.
- Explicitly version normalization (`normalization_v3`), invalidate changed content,
  scope and extractor versions, and remove expired cached private facts in idle
  processes with one lazy daemon expiry timer per cache. Entries remain bounded to
  256 / 900 seconds; cache shutdown cancels the timer.
- Show candidate reason/sync information, discard old selections after query edits or
  stale/revoked failures, expose accessible loading/errors and prevent duplicate submits.
  Existing manual binding remains available.
- Expand the synthetic corpus to 26 cases and separately report synthetic agreement,
  human review, actually executed mocked-provider regressions, live-provider acceptance
  and real Bedrock acceptance. Unknown case operations are rejected. Optional regression
  execution requires an explicit loopback `*_test` database and reports only aggregates.
- Extend the real JWT/Streamable HTTP/SQL release journey for both Gmail and Outlook:
  clarify → confirm MCP capture → preview owned sources → explicitly confirm binding
  → replay without duplicates → sync → deterministic MISMATCH → one notification
  → shared web/MCP/voice status. Discovery alone creates no evidence/notification.

## Commands and environment

Local backend `.venv`: Python 3.14.6, PostgreSQL 17 in the existing local Docker service.
Frontend uses its existing installed lockfile dependencies. Dependency installation
was already verified in the preceding clean-Linux CI pass; this resume adds no package
or SQL migration. That earlier Python 3.12/PostgreSQL 16/Node 24 record is separate:
[CI validation](ci-validation.md). No hosted GitHub rerun is claimed here.

The private `/tmp/counton_test_suite.py` wrapper runs `.venv/bin/python -m pytest`
with exactly the forwarded flags, derives `counton_test` from the ignored local
`LOCAL_DATABASE_URL`, and redacts captured secrets. No database URL is printed.
Integration fixtures create uniquely named disposable local `*_test` databases,
apply the existing Alembic head `ac746eb3f145`, and remove those databases afterward.
The smoke/evaluation wrappers use the same explicit local test URL. To reproduce,
set `TEST_DATABASE_URL` securely to an isolated loopback `*_test` database, then run
these canonical commands; never point tests at the application/production database.

```sh
cd backend
source .venv/bin/activate
python -m pytest -q --tb=short
ruff check app db/scripts tests alembic ../scripts
mypy app --ignore-missing-imports
mypy --strict --follow-imports=silent --ignore-missing-imports app/ai app/agent app/alexa app/mcp/compiler.py app/mcp/intelligence.py app/mcp/conversation_state.py app/mcp/schemas.py app/api/v1/agent.py app/api/v1/alexa.py app/schemas/compiler.py app/schemas/clarification.py app/schemas/investigation.py app/schemas/trust.py app/services/compiler_service.py app/services/investigation_service.py app/services/agent_audit.py db/scripts/bedrock_smoke.py
python db/scripts/production_smoke.py
python db/scripts/orchestration_eval.py --run-regressions --repeat 200
python db/scripts/orchestration_eval.py --require-human-review
bandit -q -r app -ll
pip-audit --progress-spinner off
python -m pip check
python -m app.integrations.worker --help
python -m app.monitoring.worker --help
python -m app.notifications.worker --help
cd ../frontend
npm run lint
npm run typecheck
npm run test -- --reporter=dot
npm run build
npm audit --omit=dev
npm audit --audit-level=high
cd ..
backend/.venv/bin/python scripts/secret_scan.py
git diff --check
```

Exact private invocations used `.venv/bin/python /tmp/counton_test_suite.py -q
--tb=short`, `.venv/bin/python /tmp/counton_operations_smoke.py`, and
`.venv/bin/python /tmp/counton_orchestration_eval.py --run-regressions --repeat 200`
from `backend`. Strict human review used `.venv/bin/python
db/scripts/orchestration_eval.py --require-human-review` directly. The remaining
commands above ran using `.venv/bin` executables or the listed npm commands.

## Final results

| Check actually executed | Result |
| --- | --- |
| Full backend `python -m pytest -q --tb=short` via private wrapper | PASS — 1,229 tests, 47.82 seconds; 104 upstream SDK warnings |
| Ruff `app db/scripts tests alembic ../scripts` | PASS |
| App-wide mypy / configured strict mypy | PASS — 144 / 37 source files |
| Offline `production_smoke.py` | PASS — all six groups; startup, six MCP contracts, HTTP ownership, signed Alexa, durable shared state, confirmed provider journey and orchestration budgets |
| Categorized `orchestration_eval.py --run-regressions --repeat 200` | PASS synthetic 26/26; PASS 346 mocked-provider/intelligence/SQL regression tests, zero failures/errors/skips |
| Strict `--require-human-review` | BLOCKED as intended, exit 2 — 26 pending cases, zero reviewed |
| Frontend lint / typecheck / production build | PASS |
| Frontend `npm run test -- --reporter=dot` | PASS — 172 passed, one pre-existing live-token test skipped |
| Bandit `-q -r app -ll` | PASS medium/high severity gate |
| `pip-audit --progress-spinner off` / `python -m pip check` | PASS — no known vulnerabilities / no broken requirements |
| `npm audit --omit=dev` / `npm audit --audit-level=high` | PASS — zero vulnerabilities in both |
| Existing Gitleaks source and history script | PASS — zero findings in each; secret values never printed |
| Three worker `--help` entry points | PASS |
| `.env` / `.env.local` gitignore checks | PASS — backend and frontend ignored |
| `git diff --check` | PASS |

Final evaluation measured synthetic per-case median **0.030 ms**, p95 **0.139 ms**.
The unchanged-record benchmark processed **200** synthetic records in **2.366 ms**:
**1** normalization, **199** cache hits, **0** Bedrock calls. These are one repeatable
local run's parsing measurements, not cloud latency, live matching accuracy or billed
cost savings. Existing cache/content/scope/version/idle-expiry tests and mocked Bedrock
model routing, concurrency, deadline/queue and total-token budget tests pass.

Security coverage includes owned discovery/binding, stale and missing grants, cached
credential removal, replay preservation, cancellation, cross-user API/MCP denial,
prompt injection treated as data, cache tenant/generation boundaries, deterministic
abstention and notification deduplication. Correlated results retain evidence IDs.
Live provider revocation and cloud recovery still require external acceptance.

Git status remains deliberately dirty on `feature/alexa-mcp`, HEAD `e7c74ac`: **124**
modified/untracked paths (including earlier pending work and asset files); no deletions,
commit or push. The full status was recorded privately at
`/tmp/counton-orchestration-final-status.txt`.

The upstream ASK SDK emits 104 datetime/certificate deprecation warnings. Existing
verification was preserved; these are not test failures. The frontend live-MCP test
is an existing credential-gated skip, not offline production acceptance. No tests were
disabled or weakened. A provider fixture was corrected to enable its actual provider
configuration before evaluating provider-backed evidence under the stricter guard.

## Changed files in this resume

Existing interrupted files updated:

- `backend/app/integrations/accounts.py`, `extraction_cache.py`, `normalization.py`
- `backend/app/monitoring/sources.py`, `correlation.py`, `worker.py`
- `backend/app/services/source_planning_service.py`, `provider_sync_service.py`
- `backend/app/schemas/source_plan.py`
- `backend/db/scripts/orchestration_eval.py`
- `backend/tests/test_source_planning.py`, `test_source_correlation.py`,
  `test_orchestration_budgets.py`, `test_provider_sync.py`, `test_release_journey.py`,
  `test_orchestration_eval.py`, `fixtures/orchestration-golden.json`
- `frontend/components/monitoring-plan.tsx`, `source-binding.tsx`,
  `frontend/lib/providers.ts`, `frontend/tests/monitoring-plan.test.tsx`
- `README.md`, `frontend/README.md`, `docs/orchestration.md`,
  `docs/automatic-tracking.md`, `docs/production-readiness.md`
- `backend/bedrock.env.sample`, `backend/providers.env.sample`

New file: this validation record. Many files above were already untracked in the
interrupted working tree; this list describes resume edits, not a wholesale new
implementation. Earlier release/CI modifications and pending migrations remain
intentionally intact. No source assets, migrations, tests or skill files were removed.

## Release blockers and next steps

| Gate | State / required action |
| --- | --- |
| Human-reviewed golden quality | BLOCKED: all 26 cases await actual reviewer identity/approval. Review expected facts and policy, record review fields only afterward, rerun the strict gate. |
| Real Bedrock | BLOCKED: current credential-chain check returns `LoginRefreshRequired`; Bedrock is disabled locally. Refresh secure runtime credentials, verify least-privilege Converse access/model overrides and run harmless smoke plus grounded quality/latency acceptance. |
| Gmail/Outlook/calendars | BLOCKED: local Google/MS/sync flags are disabled; no real dedicated-account consent or provider events accepted. Configure read-only grants and shared token encryption, then validate enrollment/refresh/revocation, push/reconciliation and recurring occurrence semantics. |
| Production release | BLOCKED: earlier read-only probes found readiness/schema/image drift and only three deployed core tools. Recheck current deployment state, review backups/migrations and hosted CI, then seek explicit rollout authorization. No production writes were performed. |
| Alexa/Echo and email receipt | BLOCKED: complete live OAuth/ASK console/device and opt-in recipient-delivery acceptance; local signed requests/mock delivery do not prove these integrations. |

After approval, deploy mutually compatible API/MCP/provider/monitoring workers, review
and apply pending migrations via the existing deployment process, validate readiness
and six tools, and run two-user capture/source-confirmation/evidence/notification
acceptance including crash/retry/revocation. Supervise workers and export existing
process-local metrics. Cache and inference concurrency limits are per process, not
cluster-wide. Total token usage budgets stop later work; they cannot pre-guarantee
billing or forcibly cancel a boto call already in flight.

Voice capture and status/Why already use the shared orchestrator; source-account/order
selection remains an explicit web detail step. No new voice source-selection dialogue,
consumer Amazon API, carrier integration, LLM-per-event extraction, or proactive Alexa
notifications are claimed. The current architecture and operational limits are in
[orchestration](orchestration.md) and [automatic tracking](automatic-tracking.md).
