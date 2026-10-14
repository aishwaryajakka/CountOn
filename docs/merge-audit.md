# Ring/Bee merge audit and repair

Audit date: October 12, 2026. Branch: `feature/alexa-mcp`.
Changes are uncommitted. No push, reset, revert, deployment or production migration
was performed. The working tree was clean at the start of this audit.

## Git and hosted failure evidence

Merge HEAD is `54306ee3443be3789eca431d9b59e4bcd5e25df2` (PR #7), with parents:

- `0c06ff4`: destination Alexa/MCP implementation, including the libcrypto fix.
- `3229da5`: Ring/Bee branch after merging the destination into itself.

The second parent's tree already equals the merge tree. Comparison against the
first parent identifies 24 changed/added files: four adapter/simulator modules,
one backend test module, two fixture JSON files, and seventeen frontend files.
There are no unmerged index entries or literal conflict markers. The merge did
not change the existing AI, MCP, agent, Alexa, services, API, models, migrations
or CI files. The integration failure was a semantic conflict: both versions of
several frontend declarations were retained, although Git considered them resolved.

The latest [hosted run](https://github.com/aishwaryajakka/CountOn/actions/runs/38270384043)
ran this exact merge SHA:

| Job | Hosted result | First failing step |
| --- | --- | --- |
| Backend | FAIL | Ruff |
| Frontend | FAIL | npm run lint |
| Secrets | PASS | None |

GitHub CLI is not installed. Public REST job metadata was retrieved; full job
logs returned HTTP 403 without authentication. The preceding two runs on
`0c06ff4` succeeded in all three jobs. Failures below were independently reproduced
using local commands and clean Linux containers. This working tree has **not**
been committed/pushed or validated by a new hosted run.

## Root causes and focused repairs

### Frontend

1. Expectations list retained two complete implementations in one function,
   redeclaring board/filter/rows and calling hooks after an unconditional return.
   Consolidated into one implementation with **both** provider filtering and
   expectation management.
2. Detail page duplicated icon imports and its resource hook/return. SourceBinding,
   TrackingControls and polling were in unreachable code. The reachable detail page
   now preserves those controls, polling, simulators, history and management.
3. App shell duplicated imports and the navigation constant. Combined navigation
   preserves both `/alexa` and `/demos`, plus the existing workspace routes.
4. Dashboard/activity created a new empty rows array each render, destabilizing
   callback dependencies and potentially retriggering resource loading. Memoized
   rows and made dashboard polling depend on the stable reload function.
5. Demos contained invalid unescaped JSX and unused imports; additional components
   contained unused imports. Corrected these without suppressing lint rules.
6. Simulator pages printed assumed MATCH/MISMATCH rather than the API response,
   and could attach evidence to an unrelated `rows[0]`. They now require an exact
   compatible expectation (explicit selection when ambiguous), retain event
   expectation simulations and display the returned deterministic evaluation.
7. The bill demo fabricated usage/tariff explanations without submitting those
   facts. Removed those claims; sample amounts are labeled input previews.
8. Explicit zero materiality tolerance was replaced with five percent by `|| 5`.
   Preserve zero when saving. Detail management remounts when reopened to avoid
   stale form state after edits. Invalid/blank tolerance is rejected rather than invented.
9. The action modal represented pause as terminal cancellation and only reset
   expectation status on resume, leaving the durable job cancelled. Pause/resume
   now uses the existing monitoring API. Explicitly reopening a cancelled/resolved
   expectation also reconfigures its existing job; failures are shown to the user.
   The backend rule against automatically waking cancelled jobs is preserved.
10. Dashboard/activity swallowed all timeline request errors as empty evidence.
    Errors now reach the existing error state rather than claiming no observations.

### Backend

Clean Ubuntu reproduced **17 Ruff errors**, exclusively in the new Ring/Bee files:
unsorted/unused imports, five unused tuple variables and two broad exception
handlers. Alexa adapter imports and both native crypto backends already passed;
the previous oscrypto fix is intact. No dependency or CI configuration change was
needed for this merge.

Sorted imports and removed unused imports. Timestamp validation now rejects invalid,
naive or missing source times instead of making stale/invalid data fresh by assigning
"now". Existing Pydantic evidence validation still enforces bounds and aware times.

### Simulator correctness and trust boundaries

- Ring camera **no detection** preserves `detected: false` as context but does not
  assert delivery failed. A boolean delivery expectation evaluates UNKNOWN, with
  no mismatch alert. Evaluator code/semantics were not changed.
- Bee facts require an explicit boolean. String `"false"`, integers and arbitrary
  conversation text are not coerced or keyword-classified as verified facts.
- Generated Ring/Bee events always carry `simulated: true`, even if an extra field
  attempts to override it. Normalized simulator sources are `ring_simulator` and
  `bee_simulator`; real-format adapter inputs retain the existing source names.
  This uses the existing open-ended evidence source schema.
- Evidence cards and timelines display **SIMULATED**, including utility simulations
  and older records that already have the raw provenance flag.
- Event IDs use UUIDs to avoid same-millisecond collisions. All simulator actions
  use the existing bearer-authenticated evidence API and evaluator API. The latter
  receives the existing `Idempotency-Key` header derived from the event ID, so an
  identical event/evaluation replay creates neither extra rows nor extra alerts.
- No direct frontend database writes, new MCP tools, provider credential flows,
  database schema changes or evaluator changes were introduced.
- Real Ring/Bee connections remain unavailable and are explicitly described that
  way. These adapters/simulators do not register a live provider or autonomous poller.

## Audit scope and retained functionality

Reviewed every file introduced/changed relative to the destination parent, including
registration/login, API/types/presentation, evidence timeline, action modal, Vitest
configuration and sample fixtures. Inspected CI/environment/dependency configuration,
evidence/evaluation/notification authorization and idempotency, provider selection,
source controls, workers, deterministic evaluators and migration/test fixtures.
The unchanged core was exercised through the full backend and frontend suites.

Production smoke verifies six authenticated MCP tools; Streamable HTTP and ownership;
signed Alexa verification and clarification/confirmation; durable conversations;
shared persistence; confirmed provider monitoring; notification recovery; authorized
source planning; correlation and operation budgets. Existing tests cover compiler,
stateful clarification, OAuth, Google/Microsoft email/calendars, concurrent workers,
missing/stale/conflicting evidence and deduplication. These are **local isolated-test
claims**, not proof of deployed credentials or live device/provider acceptance.

Added focused regressions for authorized Ring/Bee ingestion, missing auth, cross-user
association rejection, evidence/evaluation replay, single notifications, invalid
source timestamps, malicious confirmation text, simulator provenance, stable page
hooks, source/tracking controls, authoritative detail status, editing, target
selection, navigation, zero tolerance and pause/reopen job configuration. Existing assertions were retained; the
old "missing package means mismatch" assertion was corrected together with the
faulty normalization and now explicitly asserts UNKNOWN and no notification.
No test skips were added; the existing opt-in live MCP frontend test is unchanged.

## Changed files

Backend:

- `backend/app/integrations/ring/{__init__,adapter,simulator}.py`
- `backend/app/integrations/bee/{__init__,adapter,simulator}.py`
- `backend/tests/test_adapters_and_simulators.py`
- `backend/tests/test_simulator_authorization.py` (new)

Frontend:

- `frontend/app/(workspace)/{activity,dashboard,demos,expectations}/page.tsx`
- `frontend/app/(workspace)/expectations/[id]/page.tsx`
- `frontend/components/app-shell.tsx`
- `frontend/components/evidence-timeline.tsx`
- `frontend/components/expectation-actions-modal.tsx`
- `frontend/components/expectation.tsx`
- `frontend/lib/{api,presentation,simulators,types}.ts`
- `frontend/tests/{api,simulators}.test.ts`
- `frontend/tests/merge-regressions.test.tsx` (new)

Fixtures: `fixtures/ring_sample.json` and `fixtures/bee_sample.json` now explicitly
carry `simulated: true`; their observations are not live vendor data.

Documentation: this new `docs/merge-audit.md`.

No dependency, lockfile, migration, deployment or workflow changes. The passing
secrets job and all existing backend/frontend CI gates remain enabled and unchanged.

## Validation environment and exact commands

Backend: clean Ubuntu 24.04 x86_64 container, Python 3.12.3, OpenSSL 3.0.13,
PostgreSQL 16 in a separate disposable container. Python's patch version differs
from setup-python; the OS and Python minor match the workflow. Both package
installation and test execution used the current requirements/constraints.
The source copy excluded local environment files and credentials.

Used the workflow environment:
`ENVIRONMENT=test`, `DATABASE_TARGET=local`, `BEDROCK_ENABLED=false`,
`AWS_EC2_METADATA_DISABLED=true`, and loopback database URLs naming distinct
`counton`/`counton_test` databases with synthetic container-only credentials.
`pg_isready -U counton -d counton` succeeded. The workflow's `CREATE DATABASE
counton_test` ran before tests. Alembic fixtures migrated only disposable test
and worker databases. No production connection was used.

From `backend`:

```sh
python -m pip install --upgrade pip==26.2.1
python -m pip install -r requirements.txt -r requirements-dev.txt -r requirements-security.txt
python db/scripts/alexa_import_smoke.py
ruff check app db/scripts tests alembic ../scripts
mypy app --ignore-missing-imports
mypy --strict --follow-imports=silent --ignore-missing-imports app/ai app/agent app/alexa app/mcp/compiler.py app/mcp/intelligence.py app/mcp/conversation_state.py app/mcp/schemas.py app/api/v1/agent.py app/api/v1/alexa.py app/schemas/compiler.py app/schemas/clarification.py app/schemas/investigation.py app/schemas/trust.py app/services/compiler_service.py app/services/investigation_service.py app/services/agent_audit.py db/scripts/bedrock_smoke.py
python -m pytest -q --tb=short
python db/scripts/production_smoke.py
python db/scripts/orchestration_eval.py
bandit -q -r app -ll
pip-audit --progress-spinner off
python -m pip check
```

Frontend: fresh Node 24 Linux container, Node 24.21.0 / npm 11.19.0; local supplemental
runs used Node 24.19.0 / npm 11.17.0. No `.env.local` entered the clean checkout.
From `frontend`:

```sh
npm ci
npm run lint
npm run typecheck
npm run test -- --reporter=dot
NEXT_PUBLIC_API_BASE_URL=https://api.counton.invalid npm run build
npm audit --omit=dev
npm audit --audit-level=high
```

From the repository root:

```sh
backend/.venv/bin/python scripts/secret_scan.py
git diff --check
```

| Final validation | Result |
| --- | --- |
| Full backend pytest | **PASS: 1,270 tests**, 104 warnings, 62.44 seconds; no skips |
| Backend Ruff | PASS |
| General / strict mypy | PASS, 148 / 37 files |
| Alexa native dependency / adapter import | PASS, default and ctypes |
| Production smoke | PASS, all six groups |
| Orchestration evaluation | PASS, 26/26 synthetic cases, zero Bedrock calls |
| Frontend clean install, lint and typecheck | PASS; lint has no warnings |
| Frontend tests | **PASS: 201 tests**, one existing opt-in live test skipped |
| Frontend production build | PASS, all retained pages including `/alexa`, `/demos`, `/register` |
| Local production HTTP smoke | PASS, seven public/auth-gated routes return 200 |
| Ring/Bee sample normalization | PASS, both explicitly SIMULATED |
| Bandit | PASS |
| pip-audit / pip check | PASS, no known vulnerabilities / broken requirements |
| npm runtime / full high-severity audits | PASS, zero vulnerabilities |
| Gitleaks history / working source | PASS, zero findings |
| git diff --check | PASS |

The HTTP smoke verifies startup and route responses, not a live authenticated
browser/provider journey. It queried `/`, `/login`, `/register`, `/alexa`, `/demos`,
`/dashboard` and `/expectations` inside the container. Authentication and interaction
regressions ran in the frontend tests; deployed credentials were not supplied.
The 104 backend warnings are existing SDK/crypto deprecations, not failed checks.
Complete command logs were saved outside the repository under
`/tmp/counton-merge-audit/` before disposing of the task-created containers.

Final Git status: 24 modified files and three new files listed above; no deleted
files, staged changes, commits or pushes. Branch remains `feature/alexa-mcp`.

## Remaining external gates and rerun instructions

- GitHub-hosted validation of these **uncommitted** changes is pending. Review the
  diff, commit/push to `feature/alexa-mcp` yourself, then confirm all three jobs pass
  on the new SHA. Use `gh run list --branch feature/alexa-mcp --limit 5` and
  `gh run view <new-run-id> --log-failed` when CLI/authentication are available.
  Re-running the old merge SHA cannot test uncommitted fixes. Do not merge to main
  or deploy based solely on this local audit.
- Live Bedrock, Alexa account linking/device signatures, Google/Microsoft OAuth,
  subscriptions and webhook acceptance require real credentials/consent and
  recorded production acceptance. Offline mocks and signed local certificate
  fixtures do not establish that acceptance.
- Live Ring/Bee integrations are not implemented. Simulations exercise existing
  authorized APIs and persistence, not physical hardware or vendor webhooks.
- Direct manual temporal/event evaluation retains existing UNKNOWN semantics;
  authorized source-bound worker evaluation handles supported temporal rules.
  No invented event time or deadline was added to make demos appear successful.
- Previously persisted **untagged** simulator evidence cannot safely be relabeled
  automatically without provenance. New simulations are tagged; existing data
  requires owner review. This audit did not modify or remove production rows.
- The synthetic orchestration evaluation does not complete pending human review
  or real provider/Bedrock acceptance. Its optional separate mocked-regression
  mode was not requested; the full pytest suite ran the corresponding tests.
