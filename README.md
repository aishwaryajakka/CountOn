# CountOn

CountOn records what you are counting on, compares real evidence against it, and
calls attention to verified exceptions. **Calm monitoring. Clear signals.**

## Product thesis

**Expectation → Evidence → Evaluation → Exception**

Expectations are claims, not evidence. Deterministic evaluation alone decides
`MATCH`, `UNKNOWN` or `MISMATCH`: matched expectations stay quiet, unknown outcomes
keep watching, and mismatches merit attention. Missing evidence is never success.
Bedrock interprets language and explains grounded mismatches; it does not decide
outcomes or invent observations.

## Architecture

```text
Supabase Auth → current user's bearer token
  Browser /alexa → Next.js /api/agent → JWT-authenticated FastAPI agent route
    → controlled orchestrator/session → MCP SDK Streamable HTTP → Python MCP
      → compiler / stateful clarification / grounded investigator
      → owned CountOn services → repositories → PostgreSQL / Supabase
  Browser dashboard → authenticated FastAPI → same services/database

Real evidence → deterministic evaluator → persisted evaluation → in-app exception
```

The FastAPI and MCP processes must select the same database. Alembic owns schema
creation. `backend/app/db/` contains application persistence; `backend/db/`
contains developer checks and inspection SQL. Frontend application data is never
written directly to Supabase.

## Current Status

| Status | Scope |
| --- | --- |
| **Done locally** | FastAPI; PostgreSQL/Supabase persistence and expectation/evidence/evaluation models; deterministic numeric/boolean evaluation; JWT auth/ownership; real MCP Streamable HTTP and six tools; Bedrock compiler with typed Pydantic output and conservative temporal interpretation; stateful clarification, corrections/cancellation and replay-safe compiled capture; grounded mismatch investigation with safe failure degradation; auth-gated `/alexa` conversational capture/Why flow; FastAPI dashboard sharing persistence; CountOn Agent Skill; durable PostgreSQL monitoring workers, conservative evidence checks, encrypted delegated Outlook connector and in-app inbox; local test/build validation. |
| **Needs deployment/live verification** | Current MCP intelligence rollout to Lightsail; production Bedrock/model/signing configuration; live Bedrock smoke; live intelligence E2E and production `/alexa` verification. Configured addresses and earlier core-tool demos do not prove the latest code is live. |
| **Traditional ASK adapter implemented locally** | Signed HTTPS fulfillment and en-US interaction model reuse the same orchestrator/MCP path; linked tokens use existing Supabase JWT verification. Console/OAuth setup, deployed latency and ASK simulator/Echo acceptance remain unverified. |
| **Not complete** | Traditional Alexa account-linking provider/consent setup, Alexa Skills Kit simulator acceptance and real Alexa/Echo testing; Alexa+ onboarding/account linking; live Gmail/Outlook/calendar consent and ingestion verification, Ring and Bee ingestion; broader autonomous orchestration/shared session infrastructure. Metadata records alone do not prove live provider or device integrations. |

The core MCP tools are `capture_expectation`, `get_expectation`, and
`list_expectations`. The intelligence tools are `compile_expectation`,
`continue_expectation_compilation`, and `explain_expectation_mismatch`.
Every tool accepts exactly one top-level `request`. Bedrock is disabled by default
and needs secure runtime AWS access; deterministic evaluation remains authoritative.
Temporal interpretation is implemented. Monitoring can compare a real positive event
observation against an explicit deadline; missing events remain UNKNOWN. The
legacy manual temporal endpoint remains conservative. The web conversation is not an official Amazon simulator or Echo skill.

See [component docs](#component-documentation) for the compiler, canonical
clarification state/ledger, grounded evidence selection and Agent Skill details.

## Quick local setup

Prerequisites: Python with `venv`, Node.js/npm, Docker/PostgreSQL, and a Supabase
project for authentication. Configure ignored `backend/.env.local`:

```env
ENVIRONMENT=development
DATABASE_TARGET=local
LOCAL_DATABASE_URL=postgresql+psycopg://counton:counton_dev_password@localhost:5432/counton
SUPABASE_URL=https://YOUR_PROJECT.supabase.co
SUPABASE_PUBLISHABLE_KEY=YOUR_PUBLIC_KEY
MCP_PUBLIC_URL=http://127.0.0.1:8003/mcp
```

The database password above is the local Docker development value only. See
[database setup and demo seeding](backend/db/README.md) for Supabase selection,
JWT configuration, migrations and owned demo data. For conversational capture,
configure the backend-only [Bedrock settings](backend/app/ai/README.md#configuration)
and secure AWS credential provider; list/detail work without Bedrock.
Set the same private `COUNTON_CLARIFICATION_SIGNING_KEY` in backend/MCP configuration
for conversational compilation. Never put it in frontend variables.

Terminal 1, from the repository root:

```sh
docker compose up -d
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
DATABASE_TARGET=local alembic upgrade head
DATABASE_TARGET=local uvicorn app.main:app --reload
```

Terminal 2, from the repository root:

```sh
cd backend
source .venv/bin/activate
DATABASE_TARGET=local python -m app.mcp
```

Terminal 3, configure ignored `frontend/.env.local` using the public fields in
[frontend/.env.example](frontend/.env.example), plus server-only
`COUNTON_MCP_URL=http://127.0.0.1:8003/mcp`. Then:

```sh
cd frontend
npm ci
npm run dev
```

Open `http://localhost:3000`; API docs are at `http://localhost:8000/docs`, and
local MCP at `http://127.0.0.1:8003/mcp`. Both backend processes provide `/health`
and `/ready`; those paths do not verify optional Bedrock model access.

## Demo flow

1. Sign in and open `/alexa`; initialize/discover MCP and list actual expectations.
2. Ask “I'm counting on my bill being lower.” Answer which bill, the baseline,
   and timing. Nothing is saved until compilation is complete.
3. Follow the saved expectation into the normal dashboard and refresh. MCP and
   FastAPI read the same row.
4. Ask why a prepared, owned electricity expectation failed. Its latest
   deterministic `MISMATCH` enables a grounded explanation; `MATCH`, `UNKNOWN`
   and no evaluation skip the investigator. No matching row is reported honestly.

Use real test evidence/evaluations, not a claim that capture generates them.
[Acceptance checklist and timed demos](docs/hackathon-acceptance.md) cover repeatable
checks, safe cleanup and deployment prerequisites.

## Test commands

From `backend`, activate `.venv`, then run `pytest`. For the full integration
suite, privately set `TEST_DATABASE_URL` to a separate loopback PostgreSQL database
ending in `_test` (for example `counton_test`); otherwise database tests skip.
Migration-cycle tests require local CREATEDB permission. Never use production data.

From `frontend`:

```sh
npm run test
npm run lint
npm run typecheck
npm run build
```

From `backend`, also run `ruff check app db/scripts tests alembic` and
`mypy app --ignore-missing-imports`. From the root: `git diff --check`.
Detailed AI/MCP strict mypy and opt-in smoke commands are in their component docs.
The [repository audit](docs/repository-audit.md) records dependency snapshots,
startup checks and validation limits. Mocked inference tests do not establish
live model quality.

## Deployment overview

Deploy `frontend/` as Next.js on Vercel and run FastAPI and MCP separately behind
HTTPS on Lightsail. Apply `alembic upgrade head` to the shared Supabase database
before rolling out code that needs the compilation ledger and monitoring leases.
Run the optional worker as a supervised backend process; see [monitoring setup](docs/monitoring.md). Configure public
API/Supabase frontend values, server-only `COUNTON_MCP_URL`, explicit API CORS,
and backend-only database/auth/AWS/signing secrets.

Existing deployment addresses and required variables are documented in
[frontend setup](frontend/README.md#vercel-production),
[MCP deployment](docs/mcp.md#remote-deployment), and
[Bedrock rollout and live checks](docs/bedrock-integration.md).
Discover all six tools and run live acceptance before describing that deployment
as current. Never commit credentials or put private keys in `NEXT_PUBLIC_*`.

## Unfinished integrations

Real Alexa+/Echo onboarding and account linking, compatible OAuth discovery,
live Microsoft Graph consent/ingestion, Ring/Bee ingestion and external notification
delivery remain incomplete. PostgreSQL monitoring, encrypted Outlook OAuth and
in-app delivery are implemented locally; see [worker operation](docs/monitoring.md). Shared rate limiting, durable metrics export, backup/restore,
and conversation/audit retention need operational work. `/alexa` uses constrained
routing and a bounded owned-record search, not an autonomous agent.

## Next-work priority

1. Review and commit the clean current work (manual next step; this pass does not commit).
2. Apply existing migrations and deploy MCP intelligence to Lightsail.
3. Configure secure live Bedrock/model access on the MCP service.
4. Run live Bedrock smoke on the trusted backend.
5. Run live `/alexa` intelligence E2E, including clarification, shared persistence and Why.
6. Import the traditional Alexa interaction model and deploy its signed HTTPS adapter.
7. Provision compatible OAuth account linking/consent and verify the authenticated path.
8. Test the Alexa Skills Kit simulator.
9. Test real Alexa/Echo.
10. Register the Microsoft app, consent a test mailbox and run live Outlook acceptance.
11. Add Ring ingestion.
12. Add Bee ingestion.
13. Manually validate the minimal Trust Orchestrator source policy, receipts and audit delivery; validate the monitoring worker against live provider credentials before deployment.
14. Complete final demo hardening.

This order preserves the requested priorities. Runtime configuration and migrations
must be provisioned before declaring a deployment ready; no current placeholder
makes a provider, worker or Alexa device integration complete.

## Component documentation

- [CI failure investigation, fixes and executed validation](docs/ci-validation.md)
- [Controlled orchestrator and Alexa session boundary](backend/app/agent/README.md)
- [Traditional Alexa HTTPS adapter, interaction model and console/account-link setup](docs/traditional-alexa.md)
- [MCP tools, auth, startup and remote smoke](docs/mcp.md)
- [Bedrock integration and rollout](docs/bedrock-integration.md)
- [Background monitoring and legacy Outlook setup](docs/monitoring.md)
- [Gmail, Outlook, calendars and order evidence acceptance](docs/integrations-acceptance.md)
- [Compiler/client semantics](backend/app/ai/README.md),
  [clarification state machine](backend/app/ai/clarification.md), and
  [grounded investigator](backend/app/ai/investigation.md)
- [Database, RLS, migrations and demo data](backend/db/README.md)
- [Frontend setup](frontend/README.md), [Alexa web demo](frontend/docs/alexa-demo.md),
  and [Next.js MCP client](frontend/docs/mcp-client.md)
- [Hackathon acceptance](docs/hackathon-acceptance.md) and
  [Agent Skill inspection/consumption](docs/agent-skill.md)

The minimal Trust Orchestrator now validates evidence-source permissions, creates
backend-authored response receipts and records redacted runs in existing audit_events.
The web simulator exposes an expandable safe provenance summary. See the
[trust acceptance and exact manual runbook](docs/trust-orchestrator.md); implementation
and local tests do not establish production Bedrock or Alexa/Echo acceptance.

Production hardening adds native Supabase OAuth consent for ASK account linking,
client-bound JWT verification, encrypted PostgreSQL conversation/replay state and
explicit Alexa capture confirmation. The six MCP tool contracts and deterministic
evaluator remain authoritative. See the [production readiness checklist and exact
deployment/acceptance commands](docs/production-readiness.md). Live OAuth, AWS,
ASK/Echo, Graph and deployed end-to-end acceptance remain required.

Account sync now has local Google/Microsoft OAuth, official Gmail/Graph/calendar reads,
encrypted durable checkpoints, push wake-ups and explicit source bindings. Provider
credentials and live read-only acceptance remain required; see the integration guide.

Automatic provider tracking now connects authenticated push/poll sync to the existing durable monitoring worker, deterministic evaluation and deduplicated inbox. Coverage-gated reply deadlines, calendar changes, predicted shipping warnings, tracking controls and opt-in email are implemented locally. Real provider/email acceptance remains pending. See [automatic tracking and operations](docs/automatic-tracking.md).

The resumed [typed source orchestration](docs/orchestration.md) connects complete saved
expectations to explicitly confirmed authorized sources and existing durable workers.
[Current validation and release gates](docs/orchestration-validation.md) distinguish
local automated results from human review, cloud/model and Alexa device acceptance.
