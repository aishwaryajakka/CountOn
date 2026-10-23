# Repository audit and local baseline

Audit date: 2026-10-11. This records local verification, not deployment or live
AWS/Supabase/Alexa certification. No commits or pushes were performed.

## Important fixes

- Declare `httpx2` directly alongside `httpx`, and declare other directly imported
  runtime packages. MCP 2.3's transport requires HTTPX2; FastAPI test clients and
  CountOn REST/Auth calls use HTTPX. Keep their types, exceptions and mocks separate.
  This follows the [official SDK transport contract](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/client/transports.md)
  and [SDK migration guide](https://github.com/modelcontextprotocol/python-sdk/blob/main/docs/migration.md).
- Add `backend/constraints.txt`, automatically applied by both requirements files
  and copied into Docker. It pins the verified runtime/development dependency
  snapshot. Verify updates on both supported Python versions before replacing it.
- Pin ESLint 9.39.5 because the existing Next.js import, React and accessibility
  plugins do not support ESLint 10. Clean `npm ci` and `npm ls eslint` resolve
  without peer dependency conflicts. npm reports ESLint 9 as deprecated: upgrading
  it requires compatible plugin versions; do not force incompatible peers.
- Fail malformed successful Supabase Auth responses closed with the existing
  sanitized 401 envelope instead of throwing a 500. JWT verification and ownership
  rules remain unchanged across API, agent and MCP endpoints.
- Reject wildcard hosts, invalid/zero ports, credentials, whitespace and empty
  query/fragment delimiters in API CORS/Auth origins. Existing JSON-array
  `ALLOWED_ORIGINS` configuration remains the public configuration contract.
- Bound MCP connection/pool acquisition with existing HTTP settings while retaining
  the 180-second model/protocol read budget. Browser API requests have a 20-second
  deadline; agent and discovery requests have a 185-second deadline. Never retry
  a timed-out write automatically. Check persisted state before attempting again.
- Preserve cancellation for DOMExceptions from other browser realms; cancellation
  must not become a network error or emit an error log.
- Reject malformed historical evaluation metrics before querying explanatory
  evidence. Such snapshots yield no explanatory evidence rather than invalid SQL
  binds or unhashable-key failures. Deterministic evaluation semantics are unchanged.
- Export all registered database models, correct type annotations and review/remove
  unused imports. Apply mechanical import sorting, equivalent context/dict cleanup
  and scoped formatting. Broad exception catches remain only at justified safe
  error boundaries with explicit rationale. No tests were deleted, weakened or
  newly skipped to obtain a passing suite.
- Correct local setup: backend `MCP_PUBLIC_URL`, shared
  `COUNTON_CLARIFICATION_SIGNING_KEY`, dev requirements and frontend `npm ci`.
  Correct acceptance diagrams: conversation goes through `/api/agent`; `/api/mcp`
  is discovery-only. Preserve the six nested-request MCP tools and all existing
  FastAPI/Bedrock/Alexa/PostgreSQL layers.

## Validation performed

Local backend: Python 3.14 virtualenv. Deployment image: fresh Python 3.12-slim,
Linux ARM64 on this workstation. Frontend: Node 24.19.0, npm 11.17.0.

Commands below run from `backend/` unless explicitly marked otherwise. The full
suite received `TEST_DATABASE_URL` privately through the subprocess environment,
using the local `counton_test` database. No application/production database was
migrated or cleaned. Test transactions roll back; migration-cycle tests create
and drop their own uniquely named test databases.

| Exact command / check | Result |
| --- | --- |
| `.venv/bin/python -m pip install --disable-pip-version-check --no-cache-dir -r requirements.txt -r requirements-dev.txt` | PASS |
| `.venv/bin/python -m pip check` | PASS; no broken requirements |
| `.venv/bin/python -m pytest -q --tb=short` with private `TEST_DATABASE_URL` | PASS; 913 tests, no skips; 104 upstream ASK SDK deprecation warnings |
| `.venv/bin/ruff check app db/scripts tests alembic` | PASS |
| `.venv/bin/mypy app --ignore-missing-imports` | PASS; 110 source files |
| Strict scoped mypy command below | PASS; 37 source files |
| `.venv/bin/ruff format --check app/ai tests/test_bedrock.py db/scripts/bedrock_smoke.py app/agent app/alexa tests/test_startup.py` | PASS; 30 files |
| Alembic `command.check(config)` using an injected connection to `counton_test` | PASS; no new upgrade operations |
| Root: `docker build -t counton-audit:local backend` | PASS; clean constrained Python 3.12 installation |
| Root: container test command below, network disabled | PASS; 209 tests; 24 DB tests skipped in the disconnected container only |
| Root: `docker run --rm --network none counton-audit:local python -m pip check` | PASS |
| Frontend: `npm ci --no-audit --no-fund --cache /tmp/counton-npm-cache` | PASS; no ERESOLVE peer conflicts |
| Frontend: `npm ls eslint` | PASS |
| Frontend: `npm run test` | PASS; 112 tests; 1 opt-in live production test skipped, no access token supplied |
| Frontend: `npm run lint` | PASS |
| Frontend: `npm run typecheck` | PASS |
| Frontend: `npm run build` | PASS with network access; initial sandboxed attempt failed to fetch existing Google Fonts |
| Root: `git diff --check` | PASS |
| `.venv/bin/python db/scripts/bedrock_smoke.py --live` | BLOCKED; current `BEDROCK_ENABLED=false`; no invocation attempted |
| `BEDROCK_ENABLED=true .venv/bin/python db/scripts/bedrock_smoke.py --live` | BLOCKED; SDK `LoginRefreshRequired`; no AWS service error code returned |

Strict type check (from `backend/`):

```sh
.venv/bin/mypy --strict --follow-imports=silent --ignore-missing-imports app/ai app/agent app/alexa app/mcp/compiler.py app/mcp/intelligence.py app/mcp/conversation_state.py app/mcp/schemas.py app/api/v1/agent.py app/api/v1/alexa.py app/schemas/compiler.py app/schemas/clarification.py app/schemas/investigation.py app/schemas/trust.py app/services/compiler_service.py app/services/investigation_service.py app/services/agent_audit.py db/scripts/bedrock_smoke.py
```

Disconnected deployment-runtime check (from root):

```sh
docker run --rm --network none \
  -e ENVIRONMENT=test -e DATABASE_TARGET=local \
  -e LOCAL_DATABASE_URL=postgresql+psycopg://fixture@localhost/startup_test \
  -e AWS_EC2_METADATA_DISABLED=true \
  counton-audit:local python -m pytest -q \
  tests/test_startup.py tests/test_mcp.py tests/test_agent.py \
  tests/test_alexa.py tests/test_config.py --tb=short
```

Startup regressions import every application module in fresh forward/reverse
order with external I/O forbidden; exercise FastAPI lifespan, health/docs/OpenAPI,
unauthenticated agent rejection; and discover exactly six tools, each with one
required top-level `request`. Existing local network tests exercise real signed
fixture JWTs, MCP initialize/discovery/capture/get/list, shared API persistence,
error cases and exact cleanup. Existing migration tests exercise upgrade,
ownership backfill guards, foreign keys/cascades, downgrade and re-upgrade.

Auth, grounding, clarification, Trust Orchestrator and signed Alexa regressions
remain enabled. Bedrock unit tests use isolated provider responses. The harmless
live smoke was attempted separately with a process-only enabled override; AWS
login refresh failed before model reachability could be established. No private
environment files were modified. Migration upgrade/downgrade ASTs were also
compared to HEAD and are identical; only imports and annotations changed.

## Security and deployment limits

- Current tracked-file scan found no credential-bearing database URLs, AWS access
  keys, JWTs or private-key blocks. Environment files are untracked/ignored, and
  container context excludes `.env*`. This is a targeted scan, not proof that every
  possible secret format or historical commit is clean.
- Existing logging tests confirm bearer/provider/transcript sentinels do not leak.
  Client diagnostics contain only route/status/timing/support labels. No real
  credentials were displayed or added to source/config templates.
- No valid production test access token was supplied, so the opt-in remote test
  was not run. Local AWS credentials resolve through the SDK provider chain, but
  the live Bedrock probe fails with `LoginRefreshRequired`. Refresh the AWS login,
  then rerun the process-only smoke command above. Live IAM/model access, deployed
  CORS/auth/persistence and Echo/Console behavior remain deployment checks.
  Offline success does not certify them.
- This workstation's private backend environment does not set `MCP_PUBLIC_URL`.
  Set it to the actual HTTPS MCP endpoint for production, or
  `http://127.0.0.1:8003/mcp` locally; restart FastAPI. It is required for agent
  capability execution even though basic startup/health works without it.
- Configure production database selector/SSL, Supabase Auth project URL/public key,
  explicit HTTPS `ALLOWED_ORIGINS`, private `COUNTON_CLARIFICATION_SIGNING_KEY`,
  Bedrock region/model/IAM permissions and server-only frontend `COUNTON_MCP_URL`.
  See [deployment configuration](bedrock-integration.md) and [MCP docs](mcp.md).
- Conversation and Alexa reply stores and rate limiting are process-local. Keep
  the documented single-worker topology; scaling requires a shared store.
- Google Fonts must be reachable for a cold Next.js build. Runtime serves fonts
  locally. The current design/font mechanism was preserved.
- Upstream ASK certificate checks emit Python/cryptography deprecation warnings.
  No verification was disabled. ESLint's compatible version is deprecated;
  npm also reports existing optional native-package install-script notices.

No known local import/startup blockers remain under the documented configuration.
Schemas, migrations' SQL operations, evaluation outcomes, public routes and tool
names were preserved. Live deployment readiness remains conditional on the above.

## Files changed

New files:

- `backend/constraints.txt`
- `backend/tests/test_startup.py`
- `docs/repository-audit.md`

Modified files (many are only mechanical import/lint cleanup):

- `README.md`
- `backend/Dockerfile`
- `backend/alembic/env.py`
- `backend/alembic/versions/1bbc27e27689_create_core_counton_tables.py`
- `backend/alembic/versions/2e0a91d54c31_profiles_and_ownership.py`
- `backend/alembic/versions/4bc128091ea7_operational_contracts.py`
- `backend/alembic/versions/5d201f68ac90_connected_accounts_demo.py`
- `backend/app/agent/adapters.py`
- `backend/app/agent/trust.py`
- `backend/app/ai/investigation.md`
- `backend/app/ai/investigation_evidence.py`
- `backend/app/ai/mismatch_investigator.py`
- `backend/app/api/errors.py`
- `backend/app/api/operations.py`
- `backend/app/api/v1/evaluations.py`
- `backend/app/api/v1/evidence.py`
- `backend/app/api/v1/expectations.py`
- `backend/app/api/v1/integrations.py`
- `backend/app/api/v1/notifications.py`
- `backend/app/core/auth.py`
- `backend/app/core/config.py`
- `backend/app/core/http_client.py`
- `backend/app/core/observability.py`
- `backend/app/db/models/__init__.py`
- `backend/app/db/models/evaluation.py`
- `backend/app/db/models/evidence.py`
- `backend/app/db/models/expectation.py`
- `backend/app/db/models/integration.py`
- `backend/app/db/models/operations.py`
- `backend/app/evaluators/boolean.py`
- `backend/app/evaluators/numeric.py`
- `backend/app/evaluators/temporal.py`
- `backend/app/mcp/__main__.py`
- `backend/app/mcp/server.py`
- `backend/app/repositories/audit.py`
- `backend/app/repositories/evidence.py`
- `backend/app/repositories/integration.py`
- `backend/app/repositories/notification.py`
- `backend/app/repositories/operations.py`
- `backend/app/schemas/integration.py`
- `backend/app/services/evaluation_service.py`
- `backend/app/services/evidence_service.py`
- `backend/app/services/expectation_service.py`
- `backend/app/services/integration_service.py`
- `backend/app/services/notification_service.py`
- `backend/app/services/readiness.py`
- `backend/db/scripts/_acceptance.py`
- `backend/db/scripts/_cleanup.py`
- `backend/db/scripts/_common.py`
- `backend/db/scripts/_demo.py`
- `backend/db/scripts/api_smoke.py`
- `backend/db/scripts/bedrock_smoke.py`
- `backend/db/scripts/check_database.py`
- `backend/db/scripts/check_schema.py`
- `backend/db/scripts/clear_demo_data.py`
- `backend/db/scripts/local_acceptance.py`
- `backend/db/scripts/mcp_remote_smoke.py`
- `backend/db/scripts/mcp_smoke.py`
- `backend/db/scripts/operational_acceptance.py`
- `backend/db/scripts/seed_demo_data.py`
- `backend/db/scripts/setup_demo_user.py`
- `backend/db/scripts/supabase_acceptance.py`
- `backend/db/scripts/supabase_identity_check.py`
- `backend/requirements-dev.txt`
- `backend/requirements.txt`
- `backend/tests/conftest.py`
- `backend/tests/test_alexa.py`
- `backend/tests/test_auth.py`
- `backend/tests/test_bedrock.py`
- `backend/tests/test_bedrock_smoke.py`
- `backend/tests/test_config.py`
- `backend/tests/test_connected_accounts.py`
- `backend/tests/test_database_tools.py`
- `backend/tests/test_demo_data.py`
- `backend/tests/test_demo_identity.py`
- `backend/tests/test_expectation_compiler.py`
- `backend/tests/test_expectations.py`
- `backend/tests/test_intelligence_smoke.py`
- `backend/tests/test_mcp.py`
- `backend/tests/test_mcp_network.py`
- `backend/tests/test_mcp_remote.py`
- `backend/tests/test_migrations.py`
- `backend/tests/test_mismatch_investigator.py`
- `backend/tests/test_numeric_evaluator.py`
- `backend/tests/test_operational_data.py`
- `backend/tests/test_operations.py`
- `backend/tests/test_ownership.py`
- `backend/tests/test_trust.py`
- `docs/hackathon-acceptance.md`
- `frontend/README.md`
- `frontend/lib/agent/client.ts`
- `frontend/lib/api.ts`
- `frontend/lib/manual-expectation.ts`
- `frontend/lib/mcp/client.ts`
- `frontend/package-lock.json`
- `frontend/package.json`
- `frontend/tests/agent-route.test.ts`
- `frontend/tests/api.test.ts`
- `frontend/tests/mcp.test.ts`
