# Testing and Acceptance

## What each layer proves

| Layer | Exercises | Does not establish |
| --- | --- | --- |
| Offline Python tests | Schema parsing, grounding, provider fixtures, deterministic policies | Actual AWS/provider account access |
| PostgreSQL integration | Real migrations, ownership, persistence, leases, retries, audit and notifications | Production revision/configuration |
| Loopback MCP tests | Real initialize, discovery, nested calls and shared API records | Native Alexa+ onboarding |
| Signed ASK fixtures | Real signature/chain validation under a test CA, identity and conversation routing | Amazon-issued live request, recognition or Echo behavior |
| Frontend Vitest | Auth/API contract fixtures, rendered records and error flows | A deployed signed-in browser session |
| Production build | Type/compile/static-generation compatibility | Healthy cloud dependencies |

## Backend tests

Use the activated supported backend environment from [setup](setup.md):

```sh
cd backend
source .venv/bin/activate
python -m pytest -q --tb=short
```

`pytest.ini` uses `tests/` and the backend root on Python's path. Set process
`TEST_DATABASE_URL` to a distinct **loopback PostgreSQL** database ending in `_test`.
Use `postgresql+psycopg`. The configured application database must have a different
name. Fixtures migrate only the test database and roll back test transactions;
some migration/recovery cases create/drop disposable databases and need CREATEDB.

Create the ordinary local test database once, after PostgreSQL is ready:

```sh
docker compose exec postgres createdb -U counton counton_test
```

If it already exists, reuse it; do not destroy unrelated databases. Export its URL
privately, matching the local Compose credentials. With no test URL, integration
tests skip; a green partial run is not full persistence acceptance.

For credential-free local/CI execution, use `ENVIRONMENT=test`, `DATABASE_TARGET=local`,
an explicit valid local application URL and test URL, `BEDROCK_ENABLED=false` and
`AWS_EC2_METADATA_DISABLED=true`. Use valid memory conversation settings for normal
test startup, with no invalid inherited encryption placeholder. Clear public MCP
deployment URL/origin overrides for loopback test services. In particular, an
ignored `.env.local` can differ from CI; Pydantic process variables take precedence.
Do not edit production secrets to make local tests pass.

Focused lifecycle acceptance:

```sh
python -m pytest -q tests/test_alexa_identity_lifecycle.py tests/test_alexa.py tests/test_agent.py tests/test_agent_api.py tests/test_agent_sessions.py tests/test_mcp.py tests/test_mcp_intelligence.py tests/test_mcp_services.py tests/test_mcp_network.py tests/test_compilation_lifecycle.py tests/test_numeric_evaluator.py tests/test_other_evaluators.py tests/test_evaluations.py tests/test_audit_history.py tests/test_lifecycle_audit.py tests/test_frontend_demo_scenarios.py tests/test_simulator_ingestion.py tests/test_simulator_authorization.py tests/test_adapters_and_simulators.py --tb=short
```

Additional existing checks:

```sh
ruff check app db/scripts tests alembic ../scripts
mypy app --ignore-missing-imports
python db/scripts/alexa_import_smoke.py
python db/scripts/production_smoke.py
python db/scripts/orchestration_eval.py
```

The workflow `.github/workflows/ci.yml` also defines stricter Mypy scopes and
Bandit/pip-audit gates. Install `requirements-security.txt` for those tools. A
synthetic orchestration evaluation is not a substitute for human review or live
model evaluation. Do not claim hosted CI passed without its actual completed run.

## Frontend commands

These scripts exist in `frontend/package.json`:

```sh
cd frontend
npm ci
npm test
npm run lint
npm run typecheck
npm run build
```

`npm ci` installs from the committed lockfile. Normal Vitest tests require no cloud
credentials. One live MCP test is explicitly opt-in and skips without its required
configuration; identify it separately in results.

Production build requires an explicit remote HTTPS API origin. For a compilation
check without deployment credentials, CI uses:

```sh
NEXT_PUBLIC_API_BASE_URL=https://api.counton.invalid npm run build
```

That artifact is a validation artifact, not a deployable live API configuration.
Actual deployment must set the real HTTPS API, Supabase public config and canonical
frontend origin at build time.

## MCP smoke tests

With local API/MCP processes running on the same database:

```sh
cd backend
source .venv/bin/activate
python db/scripts/mcp_smoke.py --discovery-only
python db/scripts/mcp_smoke.py
```

The hidden prompt obtains a real CountOn access token. The full smoke discovers
all six schemas, calls capture/list/get, reads the same row through FastAPI, tests
error paths and cleans only its exact tagged rows. `--demo-login` is an optional
development/test login using explicitly configured credentials, not an auth bypass.

Remote commands require actual approved endpoints and token access:

```sh
python db/scripts/mcp_remote_smoke.py --mcp-url https://<mcp-host>/mcp --discovery-only
python db/scripts/mcp_remote_smoke.py --mcp-url https://<mcp-host>/mcp --api-url https://<api-host>
```

Replace placeholders before executing. Without an API cleanup URL, the remote
probe stays read-only. Never pass tokens as command-line arguments. These commands
are documented capabilities, not a claim they were run against production.

## Security and repository checks

From the repository root:

```sh
python3 scripts/secret_scan.py
git diff --check
git status --short
```

The scanner requires Docker and its pinned Gitleaks image, scans Git history and
non-ignored source in isolated containers, and reports filenames/rules only. A
blocked scanner is not a pass. Never print discovered credentials or rewrite
history automatically. Use the [security](security.md) response procedure.

## Manual acceptance checklist

- Sign in as CountOn user A; capture through `/alexa`, clarify missing facts and
  explicitly approve. No incomplete row should exist before capture.
- Cancel a separate draft; verify that it produces no new expectation.
- Run the electricity, package and Bee scenarios in [demo guide](demo-guide.md).
  Confirm actual MISMATCH/MATCH/UNKNOWN and visible simulation labels.
- Read the same IDs through ordinary expectation detail/list APIs; reload the UI.
- Verify the complete owned expectation → evidence → evaluation → notification
  linkage and real audit events. Notification creation honors preferences.
- Ask contextual Why. MATCH/UNKNOWN must bypass investigation. A MISMATCH must
  cite only supplied evidence, with safe fallback when inference is unavailable.
- Sign in as user B; verify A's IDs cannot be read, mutated or reused as session
  context. Automated tests already verify this boundary locally.
- For genuine Alexa acceptance, follow [ASK setup](traditional-alexa.md), use a
  real linked account and validate Console/physical-device speech and latency.
- For providers/AWS, distinguish real consent/model calls from fixture tests and
  simulation. Do not label a configured provider as connected.

## Executed validation

Documentation rebuild validation, October 23, 2026, on `main` based on `baaf66d`
plus these uncommitted documentation/template changes. No application code,
dependencies, migration or deployment configuration changed.

| Working directory / command | Observed result |
| --- | --- |
| backend: `.venv/bin/python -m pytest -q --tb=short` with the isolated process configuration below | **PASS — 1,430 passed**, 174 upstream ASK/cryptography deprecation warnings; no database skips |
| backend: `.venv/bin/python -m pytest -q tests/test_config.py tests/test_bedrock_smoke.py --tb=short` after sample edits | **PASS — 76 passed**; smoke tests use injected responses, not AWS |
| frontend: `npm test` | **PASS — 284 passed, 1 skipped**; the live MCP test remains explicitly credential-gated |
| frontend: `npm run lint` | **PASS** |
| frontend: `npm run typecheck` | **PASS** |
| frontend: `npm run build` with credential-free public validation values | **PASS**; all routes compiled, including `/demos`, `/alexa`, `/api/agent`, `/api/mcp` and `/oauth/consent` |
| root: `python3 scripts/secret_scan.py` with local Docker access | **PASS — 0 Git-history findings, 0 non-ignored source findings**; the sandbox-only attempt first reported infrastructure blocked, then the permitted Docker run completed |
| root: temporary local Markdown link/anchor validator | **PASS**; all repository Markdown local links and heading targets resolve |
| root: temporary source/schema/template audit | **PASS**; eight tracked env samples, 99 setting references, six actual MCP definitions and referenced code/test paths checked |
| root: `git diff --check` | **PASS** |

The full backend command ran with `ENVIRONMENT=test`, `DATABASE_TARGET=local`,
a separate loopback `TEST_DATABASE_URL` ending in `counton_test`, an explicit local
application URL, `CONVERSATION_STORE_BACKEND=memory`, a public fixture encryption
key, `BEDROCK_ENABLED=false`, `AWS_EC2_METADATA_DISABLED=true`, empty public MCP URL
and `MCP_ALLOWED_ORIGINS=[]`. Database credentials remained private process values.
These overrides avoided invalid inherited development configuration; no ignored
credential file was changed. The local interpreter was Python 3.14; Python 3.12
remains the CI/container baseline and was not rerun in a clean container here.

The build command explicitly set `NEXT_PUBLIC_API_BASE_URL=https://api.counton.invalid`,
`NEXT_PUBLIC_SUPABASE_URL=https://validation-project.supabase.co`,
`NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=sb_publishable_CICredentialFreeValidationKey`
and `NEXT_PUBLIC_APP_URL=https://frontend.counton.invalid`. These are public synthetic
compile inputs, not usable credentials or a deployment. Existing Node 24/npm
installation was used; this pass did not reinstall dependencies or rerun hosted CI.

Live Bedrock inference, Amazon/Supabase provider consent, ASK/Echo speech/account
linking, mail/calendar access, Bee account import and actual email delivery were
**NOT RUN**. Their statuses remain separate from passing local tests.
Earlier [focused acceptance](focused-acceptance.md) is retained as a dated record,
not a promise of current test counts.
