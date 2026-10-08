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
  Browser /alexa → authenticated Next.js /api/mcp
    → official MCP client → Streamable HTTP → Python MCP
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
| **Done locally** | FastAPI; PostgreSQL/Supabase persistence and expectation/evidence/evaluation models; deterministic numeric/boolean evaluation; JWT auth/ownership; real MCP Streamable HTTP and six tools; Bedrock compiler with typed Pydantic output and conservative temporal interpretation; stateful clarification, corrections/cancellation and replay-safe compiled capture; grounded mismatch investigation with safe failure degradation; auth-gated `/alexa` conversational capture/Why flow; FastAPI dashboard sharing persistence; CountOn Agent Skill; local test/build validation. |
| **Needs deployment/live verification** | Current MCP intelligence rollout to Lightsail; production Bedrock/model/signing configuration; live Bedrock smoke; live intelligence E2E and production `/alexa` verification. Configured addresses and earlier core-tool demos do not prove the latest code is live. |
| **Not complete** | Traditional Alexa Skill intents/backend connection, Alexa Skills Kit simulator acceptance and real Alexa/Echo testing; Alexa+ onboarding/account linking; Outlook, Ring and Bee ingestion; continuous scheduling/monitor worker; broader Trust Orchestrator/privacy ledger. Existing account/job/audit/provenance records are contracts, not those completed integrations. |

The core MCP tools are `capture_expectation`, `get_expectation`, and
`list_expectations`. The intelligence tools are `compile_expectation`,
`continue_expectation_compilation`, and `explain_expectation_mismatch`.
Every tool accepts exactly one top-level `request`. Bedrock is disabled by default
and needs secure runtime AWS access; deterministic evaluation remains authoritative.
Temporal interpretation is implemented, while temporal/event evaluation remains
UNKNOWN. The web conversation is not an official Amazon simulator or Echo skill.

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
```

The database password above is the local Docker development value only. See
[database setup and demo seeding](backend/db/README.md) for Supabase selection,
JWT configuration, migrations and owned demo data. For conversational capture,
configure the backend-only [Bedrock settings](backend/app/ai/README.md#configuration)
and secure AWS credential provider; list/detail work without Bedrock.

Terminal 1, from the repository root:

```sh
docker compose up -d
cd backend
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
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
npm install
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

From the root: `git diff --check`. Detailed AI/MCP Ruff, strict mypy and opt-in
smoke commands are in their component docs. The scoped AI/MCP lint checks pass;
a broad backend Ruff audit still reports existing legacy lint findings, so
repository-wide backend lint is not clean. Mocked inference tests do not
establish live model quality.

## Deployment overview

Deploy `frontend/` as Next.js on Vercel and run FastAPI and MCP separately behind
HTTPS on Lightsail. Apply `alembic upgrade head` to the shared Supabase database
before rolling out code that needs the compilation ledger. Configure public
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
provider ingestion (including Ring/Bee), scheduling workers, notification delivery,
and temporal/event deterministic evaluation remain incomplete. Connected accounts
are metadata only. Shared rate limiting, durable metrics export, backup/restore,
and conversation/audit retention need operational work. `/alexa` uses constrained
routing and a bounded owned-record search, not an autonomous agent.

## Next-work priority

1. Review and commit the clean current work (manual next step; this pass does not commit).
2. Apply existing migrations and deploy MCP intelligence to Lightsail.
3. Configure secure live Bedrock/model access on the MCP service.
4. Run live Bedrock smoke on the trusted backend.
5. Run live `/alexa` intelligence E2E, including clarification, shared persistence and Why.
6. Finish traditional Alexa Skill intents/interaction model.
7. Connect its authenticated backend endpoint without changing the evaluator boundary.
8. Test the Alexa Skills Kit simulator.
9. Test real Alexa/Echo.
10. Add Outlook ingestion.
11. Add Ring ingestion.
12. Add Bee ingestion.
13. Build the broader Trust Orchestrator/privacy/provenance layer using existing grounded provenance.
14. Complete final demo hardening.

This order preserves the requested priorities. Runtime configuration and migrations
must be provisioned before declaring a deployment ready; no current placeholder
makes a provider, worker or Alexa device integration complete.

## Component documentation

- [MCP tools, auth, startup and remote smoke](docs/mcp.md)
- [Bedrock integration and rollout](docs/bedrock-integration.md)
- [Compiler/client semantics](backend/app/ai/README.md),
  [clarification state machine](backend/app/ai/clarification.md), and
  [grounded investigator](backend/app/ai/investigation.md)
- [Database, RLS, migrations and demo data](backend/db/README.md)
- [Frontend setup](frontend/README.md), [Alexa web demo](frontend/docs/alexa-demo.md),
  and [Next.js MCP client](frontend/docs/mcp-client.md)
- [Hackathon acceptance](docs/hackathon-acceptance.md) and
  [Agent Skill inspection/consumption](docs/agent-skill.md)
