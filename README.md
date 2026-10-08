# CountOn

CountOn stores everyday expectations, ingests evidence and evaluates claims as
`MATCH`, `MISMATCH` or `UNKNOWN`. For a bill expected below $142.10, an observed
$162 produces `MISMATCH`; $130 produces `MATCH`; unrelated evidence produces
`UNKNOWN`. Evaluators remain deterministic.

The [CountOn Agent Skill](docs/agent-skill.md) teaches compatible agent hosts the
existing MCP workflows while separating expectations from evidence/evaluation.
It complements the Alexa+ web demo; transport remains Streamable HTTP.

## Alexa+ hackathon track

Live demo: **https://counton-frontend.vercel.app/alexa**. Sign in normally,
wait for the verified MCP badge, then use the list, electricity detail, and
grocery capture starter prompts. Successful capture links to the ordinary
CountOn detail page; refresh demonstrates shared persistence.

```text
Supabase Auth -> current browser access token
Browser /alexa -> Bearer -> Next.js /api/mcp -> real MCP initialize/tools/list/tools/call
               -> Streamable HTTP -> Lightsail CountOn MCP -> owned services -> Supabase
Browser dashboard -> Bearer -> Lightsail FastAPI -> same services/database
```

The demo uses the official TypeScript MCP client and the existing Python MCP
server. Only capture_expectation, get_expectation, and list_expectations are
exposed; all tool arguments use exactly `{ "request": {...} }`. Tokens remain
in the existing secure session/request flow and are never printed or returned.
Current MCP responses expose stored status, not evidence/evaluation reasoning.
The router is deterministic; Bedrock and native Alexa+ device linking are not
implemented. This is CountOn's web demo, not Amazon's official simulator.

Vercel Production requires NEXT_PUBLIC_API_BASE_URL, NEXT_PUBLIC_SUPABASE_URL,
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY, and server-only COUNTON_MCP_URL. They are
configured for the canonical production URL; no service-role key is used.

Final acceptance on 2026-10-08: production initialize/discovery/list/get/capture,
normal UI handoff, refresh/persistence, mobile layout, and tagged exact-ID cleanup
passed. Frontend lint/typecheck/build and 89 standard tests passed, plus the live
MCP test. Backend: 38 MCP tests against isolated counton_test and 35 auth tests
passed. The Agent Skill passed its reference validator. No backend transport
changes were required.

See [full acceptance, environment setup, manual test, and timed judge scripts](docs/hackathon-acceptance.md),
[simulator guide](frontend/docs/alexa-demo.md), and [Agent Skill guide](docs/agent-skill.md).

## Architecture

```text
Client → FastAPI → JWT authentication → Services → Repositories → SQLAlchemy → PostgreSQL
```

Application persistence lives in `backend/app/db/`. Developer SQL and verification
scripts live in `backend/db/`. Alembic owns schema creation.

## Database target

Backend configuration comes from the gitignored `backend/.env.local`:

```env
APP_NAME=CountOn
ENVIRONMENT=development
DATABASE_TARGET=supabase
LOCAL_DATABASE_URL=postgresql+psycopg://counton:counton_dev_password@localhost:5432/counton
SUPABASE_DATABASE_URL=postgresql+psycopg://USERNAME:PASSWORD@HOST:5432/postgres?sslmode=require
SUPABASE_URL=https://PROJECT.supabase.co
SUPABASE_JWKS_URL=https://PROJECT.supabase.co/auth/v1/.well-known/jwks.json
SUPABASE_PUBLISHABLE_KEY=YOUR_PUBLIC_KEY
LOG_LEVEL=INFO
ALLOWED_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]
RATE_LIMIT_ENABLED=true
RATE_LIMIT_REQUESTS=300
RATE_LIMIT_WRITES=100
RATE_LIMIT_WINDOW_SECONDS=60
```

`settings.database_url` resolves only the explicitly selected target. Use a process
override such as `DATABASE_TARGET=local alembic upgrade head` to switch a command
without rewriting the file. Restart FastAPI after changing configuration.

Frontend configuration belongs in `frontend/.env.local`, containing only
`NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY`.
Database credentials and `SUPABASE_SECRET_KEY` stay backend-only; the latter is
needed only by the optional administrative verification script.

## Authentication

Supabase Auth owns credentials. A verified user UUID maps to an idempotently
created `profiles` row. All expectation, evidence, evaluation and notification
routes require `Authorization: Bearer <Supabase access token>`. Clients cannot
assign ownership in JSON. Services scope every parent lookup by owner, returning
404 for missing or other users' resources.

Sign in through Supabase Auth with the public URL/publishable key. In
`http://localhost:8000/docs`, choose **Authorize** and enter the session's access
token. API keys and refresh tokens do not authenticate CountOn API calls.

JWT verification checks signature, expiry, issuer, audience and authenticated
role. ES256/RS256 uses the project's JWKS; legacy HS256 additionally requires a
successful Auth-server check. Public keys cache for up to ten minutes; asymmetric
tokens remain valid until expiry. See [Supabase JWT guidance](https://supabase.com/docs/guides/auth/jwts).

## Core schema

| Table | Purpose |
| --- | --- |
| profiles | Auth UUID plus optional display name/timezone |
| expectations | Required owner, claim, comparison and lifecycle status |
| evidence | Observations, ordered by observation time; optional idempotency key |
| evaluations | Persisted deterministic results |
| notifications | Owned in-app mismatch records with message/status; no delivery |
| monitoring_jobs | Persistent scheduling contract; one active job per expectation |
| audit_events | Redacted entity/actions, metadata and request IDs |
| integration_connections | Owned provider account metadata; no credential storage |

Jobs are created with expectations; no worker executes them yet. Evidence and
notifications derive ownership through expectations. Hard deletion removes an
expectation's evidence, evaluations, notifications and jobs. Audit events retain
resource UUIDs with their parent reference cleared; deleting the profile removes
its audit records. No external integrations or legal retention policy currently
require a soft-delete lifecycle.

## Connected Accounts

CountOn models Google and Microsoft email/calendar accounts, Ring cameras, Bee
wearables, utility and delivery connections. Multiple accounts of the same
provider/type are allowed. These are **metadata-only contracts**; OAuth, live
provider APIs and encrypted credential storage are future work. Responses expose
`credential_state=not_configured`. `connected` describes metadata state and does
not prove a working provider authorization.

Authenticated `/api/v1/integrations` supports list/create and read/patch/delete
by ID. Lists filter by `provider`, `connection_type`, `status` and use bounded
pagination. Metadata accepts only mock/demo/account-kind fields; token fields
are rejected. Tokens must eventually live in a dedicated encrypted credential
store, never JSONB metadata. In the future account-linking design, Alexa identifies
the linked CountOn user; CountOn owns the selected provider accounts. Alexa does
not supply arbitrary Gmail/Outlook content or act as their source of truth.

## Notifications

The evaluation service delegates notification persistence to a notification
service. `MISMATCH` creates one in-app record per evaluation; `MATCH` and `UNKNOWN`
are silent. No email/SMS/push delivery occurs. `/api/v1/notifications` lists owned
records; `GET` and `PATCH /{id}` support reading and changing status to `read` or
`dismissed`. Sent/failed states are reserved for future delivery code.

## Audit / Request IDs

Backend-controlled audits record profiles, expectations, evidence, evaluations,
notifications and account changes in the same transaction as the write. Entity
IDs, actions and safe metadata are stored, without credentials or source payloads.
Existing action names `evidence.ingested` and `expectation.evaluated` are preserved.
`X-Request-ID` accepts UUIDs or is generated, appears in errors and JSON logs, and
correlates HTTP-originated audit records. CLI demo writes have no HTTP request ID.
Audit tables have no client write grants; there is no public audit-write endpoint.

## Demo Account

The tagged Ashley Mccormick demo has six mocked connections, five expectations, ten
evidence rows, five evaluations and one notification. Utility billing produces
MISMATCH; delivery confirmation and a normalized appointment-confirmed boolean
produce MATCH. Dentist calendar disagreement and the after-hours calendar scenario
remain UNKNOWN because temporal semantics are intentionally unsupported.
The package/plumber examples assert normalized confirmation; they do not infer
calendar semantics from raw provider content.

The dedicated account is **Ashley Mccormick**, **demo@counton.app**, in
**America/Chicago**. The demo password is intentionally not stored in Git.
For team access, obtain it through the team's secure shared channel.

### How to Seed Demo Data

From `backend`, with the virtual environment active:

```sh
DATABASE_TARGET=local python db/scripts/setup_demo_user.py
DATABASE_TARGET=local python db/scripts/seed_demo_data.py
```

Local uses the existing stable UUID unless `COUNTON_DEMO_USER_ID` is configured;
setup and seeding require no Supabase Auth access. For Supabase, configure the
backend-only Auth Admin key and demo password in ignored `backend/.env.local`, then:

```sh
DATABASE_TARGET=supabase python db/scripts/setup_demo_user.py
```

Setup finds the account by email or creates it using the Auth Admin API. It
reuses existing accounts without resetting passwords. Save the printed UUID as
`COUNTON_DEMO_USER_ID` in that same ignored file, then run:

```sh
DATABASE_TARGET=supabase python db/scripts/seed_demo_data.py
```

Setup ensures Ashley's profile; seeding reuses tagged rows without overwriting
them. An outer transaction and advisory lock prevent partial or concurrent
duplicate seeds. All connections are mocked. See [demo setup details](backend/db/README.md#application-contracts-and-demo-data).

### How to Clear Demo Data

```sh
DATABASE_TARGET=local python db/scripts/clear_demo_data.py
DATABASE_TARGET=supabase python db/scripts/clear_demo_data.py
```

Use the same configured demo UUID. Cleanup requires both owner and demo markers,
removes tagged audit artifacts and uses parent cascades. An empty tagged profile
is removed; a profile with untagged expectations/accounts/audit history is retained.
Supabase Auth users are never deleted by the demo scripts. No TRUNCATE or broad
team-data deletion occurs. Successful verification leaves the demo cleared.

## How to run

From the repository root, start local PostgreSQL if using the local target:

```sh
docker compose up -d
cd backend
source .venv/bin/activate
python -m pip install -r requirements.txt
DATABASE_TARGET=local alembic upgrade head
DATABASE_TARGET=local uvicorn app.main:app --reload
```

For Supabase, use `DATABASE_TARGET=supabase` for migration and server commands.
`/health` reports process liveness. `/ready` checks database access, required tables
and the current migration head, returning a safe 503 when unavailable.

API errors use `{"error":{"code":"...","message":"...","request_id":"..."}}`
and preserve HTTP status codes. Responses include `X-Request-ID`; an incoming
UUID is accepted or a new UUID is generated. Lists use `limit` (1–100, default
100) and `offset`; expectations filter by `status`/`type`, notifications by
`status`. Evidence ingestion accepts an optional `external_event_id` in JSON or `Idempotency-Key` in headers: identical retries return
the original record, conflicting payloads return 409. Provider events are unique
within `(expectation_id, source, external_event_id)`, preventing cross-account
collisions while allowing one event to support separate expectations. Unkeyed
manual evidence remains supported. Each explicit evaluation
creates history and a mismatch notification when appropriate.

## How to test

Use a separate loopback PostgreSQL database ending in `_test`:

```sh
TEST_DATABASE_URL='postgresql+psycopg://counton:counton_dev_password@localhost:5432/counton_test' pytest
DATABASE_TARGET=local python db/scripts/local_acceptance.py
DATABASE_TARGET=supabase python db/scripts/check_schema.py
DATABASE_TARGET=supabase python db/scripts/supabase_acceptance.py
python db/scripts/operational_acceptance.py
```

Create `counton_test` once with your local PostgreSQL tools. Without
`TEST_DATABASE_URL`, integration tests skip. Migration-cycle tests require
CREATEDB and operate only on a newly created disposable local database.

Authenticated acceptance scripts prompt for a real token with hidden input, or
read `COUNTON_ACCESS_TOKEN` from the process environment. Never put credentials
in command arguments or chat. `supabase_identity_check.py` optionally provisions
three temporary confirmed Auth users without email delivery, tests both database
targets and RLS, and removes only those users and their test artifacts. Run it
with both databases migrated and FastAPI serving Supabase on port 8000.

## Supabase deployment

Store the PostgreSQL URL from **Supabase → Connect** in the backend file, then run:

```sh
DATABASE_TARGET=supabase alembic upgrade head
DATABASE_TARGET=supabase python db/scripts/check_schema.py
DATABASE_TARGET=supabase alembic check
```

Production configuration requires `ENVIRONMENT=production`, Supabase Auth
configuration, a TLS database URL, explicit HTTPS `ALLOWED_ORIGINS`, and enabled
rate limiting. Wildcard origins are rejected. Deploy with a supervised ASGI
server without `--reload`, HTTPS ingress and correctly configured proxy handling.

Supabase RLS/grants deny anonymous table access and isolate owners. The backend's
privileged database role can bypass RLS, so backend ownership checks remain
mandatory. See [database workflows and policies](backend/db/README.md).

## Current capabilities

Operational safeguards include database connection/pool/statement timeouts,
explicit CORS, safe error envelopes, atomic audit writes, bounded lists and an
in-memory rate limiter (300 requests/100 writes per client address per minute by
default). The `RateLimiter` interface accepts a shared implementation; the current
limiter is per process and **does not protect multiple workers or replicas with a
shared budget**. Health/readiness and CORS preflights are exempt.

Metrics hooks count requests, latency totals, 5xx responses, evaluation results,
evidence ingestion and notification creation. The default sink is in-memory;
configure a durable exporter and alerting for deployment. Logs contain route
patterns, status, duration and request IDs, without headers or request bodies.

The shared HTTP client has separate connect/read timeouts and bounded exponential
backoff for GET/HEAD transport failures and 502/503/504 only. It never retries
writes, authentication failures or validation failures. No external integrations
use it yet. See [HTTPX timeouts](https://www.python-httpx.org/advanced/timeouts/).

Known gaps: shared rate-limit storage and trusted ingress policy, metrics export,
backup/restore operations, an explicit audit retention policy, and future worker
claim/lease/retry and notification delivery logic. Bedrock, MCP, Ring, Bee,
EventBridge and external notification delivery remain unimplemented. Temporal
and event evaluation still returns `UNKNOWN`.

Verified on 2026-10-02: **227 tests passed**, local and Supabase operational
acceptance passed with real Auth tokens, and all eight application tables with Supabase RLS
were exercised. Both schemas match metadata at revision `5d201f68ac90`; temporary
users and test artifacts were removed. One non-failing Starlette/HTTPX
deprecation warning remains. Local checks used native PostgreSQL 17 because
Docker is unavailable on this machine.

Canonical demo identity verified on 2026-10-02: Ashley Mccormick /
`demo@counton.app`; local stable and explicitly configured UUIDs passed, real
Supabase sign-in passed, and repeat seeds preserved 6/5/10/5/1 counts with all
five expected results. Cleanup removed tagged data and retained the Auth account.
The supplied credential remains only in ignored backend configuration; repository
secret scanning passed. The complete backend suite passed **237 tests** with one
existing Starlette/HTTPX deprecation warning. No frontend or evaluator changes.

## Run the CountOn frontend

The existing frontend directory now contains Next.js, React and TypeScript. It
uses Supabase Auth and calls FastAPI for all application data.

Backend terminal:

```sh
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload
```

Frontend terminal:

```sh
cd frontend
npm install
npm run dev
```

Configure the public API/Supabase values in ignored `frontend/.env.local`, then
open **http://localhost:3000**. Teammate setup, routes, demo seeding, limitations
and validation commands are in [frontend/README.md](frontend/README.md).

## MCP integration

See the [MCP handoff guide](docs/mcp.md) for local Streamable HTTP startup,
JWT authentication, tool contracts, network smoke tests, the Person 2 compiler
interface, and Alexa+ integration next steps.
