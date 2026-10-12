# CI failure investigation — October 12, 2026

Branch: `feature/alexa-mcp`, base revision `e7c74ac5db21`, with existing uncommitted
work retained. **Local CI commands pass; GitHub-hosted CI has not been rerun.**
No commit, push, workflow dispatch, production migration or deployment occurred.

## Evidence and root causes

The [failed hosted run](https://github.com/aishwaryajakka/CountOn/actions/runs/38175444093)
reports backend failure at **Initialize containers**, frontend failure at
**npm run build**, and a successful secrets job. GitHub CLI and authentication
tokens are unavailable. Public job metadata and check annotations were retrieved;
full job log endpoints return HTTP 403. Historical frontend stderr is unavailable;
the committed build was reproduced independently.

1. **Docker health-command quoting.** The backend annotation includes the Docker
   create arguments with single-quoted `--health-cmd`. The runner passes process
   arguments rather than using shell single-quote parsing. Reproducing those
   tokens returns exit 125, `unknown shorthand flag: 'U' in -U`. Double quotes
   keep the entire health command one argument. The corrected PostgreSQL 16
   container starts and becomes healthy.
2. **Missing build-time API origin.** A clean Node 24 install of committed HEAD
   compiles, then fails prerendering `/_not-found` with
   `Configure NEXT_PUBLIC_API_BASE_URL before building the production frontend.`
   CI now supplies `https://api.counton.invalid` only to the build step. This
   credential-free validation artifact is not deployed. Vercel still needs its
   actual production API origin and public Supabase configuration. The production
   HTTPS/localhost guards are retained.
3. **Unconfigured auth construction.** Without a local Supabase URL, newer PyJWT
   rejects the relative JWKS URI during verifier construction, causing a 500
   instead of 401. The verifier now constructs no JWKS client when unconfigured
   and rejects credentials normally. API and MCP regression tests verify this
   fail-closed behavior without network access or bypasses.
4. **Security gates after startup.** The fresh Python image bundled vulnerable
   pip 25.0.1. CI upgrades the installer to 26.2.1 before dependency installation.
   The full frontend audit also identified the unpatched dev-only Next lint
   chain `fast-glob -> micromatch -> braces`. A documented MIT-licensed local
   fork adds non-disableable parser/AST depth limits and cycle rejection while
   retaining existing lint rules. It is installed through npm's root dependency
   override reference. No advisory is ignored and neither audit gate is removed.
   See [patch provenance and removal procedure](../frontend/vendor/braces/README.md).
   Audit cannot prove the security of a local fork: dedicated tests exercise the
   actual installed transitive module, deep strings/ASTs, cycles, and ten ordinary
   upstream compatibility fixtures. The original compile/expand stack overflow
   was reproduced with a 9,999-character pattern.
5. **Metrics regression assertion.** An existing worker test enumerated only
   the old metrics. It now checks the additional outcome/reason metrics and their
   exact labels, preserving request correlation and context-restoration assertions.

## Database and dependencies

`POSTGRES_DB=counton` creates the application database only. The workflow already
has an explicit `CREATE DATABASE counton_test` step before pytest; it was not
reached in the failed hosted backend job. In the clean reproduction, the database
was absent before that step and present afterward. The test fixture migrates only
the separate loopback `*_test` database. Its final Alembic revision equals head:
`ac746eb3f145`. Model/migration, downgrade, ownership and concurrency tests run
within the full suite. No application or production database was migrated.

Backend requirements/constraints install successfully. HTTPX and HTTPX2 remain
intentional distinct dependencies for REST and MCP 2.x, respectively. The frontend
lockfile is consistent with `npm ci`; only the lint dependency override changed.
Previously added local fonts remove build-time Google Fonts network dependence.

## Executed checks

Fresh Docker Linux snapshots excluded `.env*` credentials, node_modules, virtual
environments and build caches. Versions: Python **3.12.15**, PostgreSQL **16.15**,
Node **24.21.0**, npm **11.19.0**. These reproduce the workflow's configured runtime
versions and dependency services; the containers use Debian, not the GitHub
Ubuntu runner image. They do not prove the hosted runner will pass.

Backend environment matches CI: `ENVIRONMENT=test`, `DATABASE_TARGET=local`,
the workflow's loopback application/test URLs, `BEDROCK_ENABLED=false`, and
`AWS_EC2_METADATA_DISABLED=true`. No cloud credentials are supplied.

Run from `backend/`, after creating `counton_test` as in the workflow:

```sh
python -m pip install --upgrade pip==26.2.1
python -m pip install -r requirements.txt -r requirements-dev.txt -r requirements-security.txt
ruff check app db/scripts tests alembic ../scripts
mypy app --ignore-missing-imports
mypy --strict --follow-imports=silent --ignore-missing-imports app/ai app/agent app/alexa app/mcp/compiler.py app/mcp/intelligence.py app/mcp/conversation_state.py app/mcp/schemas.py app/api/v1/agent.py app/api/v1/alexa.py app/schemas/compiler.py app/schemas/clarification.py app/schemas/investigation.py app/schemas/trust.py app/services/compiler_service.py app/services/investigation_service.py app/services/agent_audit.py db/scripts/bedrock_smoke.py
python -m pytest -q --tb=short
python db/scripts/production_smoke.py
python db/scripts/orchestration_eval.py
bandit -q -r app -ll
pip-audit --progress-spinner off
```

All pass. **1,207 backend tests**, no skips; 104 existing upstream ASK deprecation
warnings. Mypy checks 144 general / 37 strict source files. All six smoke groups
pass; cloud/device acceptance is explicitly not run. The synthetic evaluation
passes 20 cases; its 20 pending human reviews remain a release gate, not a CI claim
of real provider accuracy. The dependency audit reports no known vulnerabilities.

From `frontend/` in the clean Node 24 container, with no Supabase or MCP credentials:

```sh
npm ci
npm run lint
npm run typecheck
npm run test
NEXT_PUBLIC_API_BASE_URL=https://api.counton.invalid npm run build
npm audit --omit=dev
npm audit --audit-level=high
```

All pass. **168 frontend tests**, with one pre-existing credential-gated live MCP
test skipped; no new skips. All application routes build. Both audits report zero
vulnerabilities. The 23 new dependency regression tests also passed separately.

From the repository root, `python3 scripts/secret_scan.py` passes both history and
source scans with zero findings. `git diff --check` passes. The secrets job is
byte-for-byte unchanged from HEAD.

## Remaining verification

- Publish the reviewed changes through the normal development process and observe
  a complete successful GitHub-hosted run. No hosted success is claimed here.
- Remove the local dependency fork when a compatible reviewed upstream security
  fix is available; retain its regression tests.
- Live MCP/cloud/device acceptance still requires dedicated credentials. CI uses
  isolated fixtures and never proves production connectivity or Alexa acceptance.
