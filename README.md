# CountOn

The deterministic backend implements:
**Expectation → Evidence → Evaluation → MATCH / UNKNOWN / MISMATCH**.
PostgreSQL persists both the result and expectation status in one transaction.
The same FastAPI/SQLAlchemy backend runs locally and against Supabase PostgreSQL.

API routes → services → repositories → SQLAlchemy/PostgreSQL. Pure evaluators own
deterministic comparison logic. Future adapters normalize into the shared Evidence
contract. Numeric evaluation compares observations; it does not infer causes.

## Environment files

Backend configuration belongs only in **`backend/.env.local`**. Create that file
if it is missing. For local Compose, save these values:

```dotenv
APP_NAME=CountOn
ENVIRONMENT=development
DATABASE_URL=postgresql+psycopg://counton:counton_dev_password@localhost:5432/counton
LOG_LEVEL=INFO
```

These credentials are local-development values. Settings require `DATABASE_URL`
and load `.env.local` relative to the backend package, independent of the shell's
working directory. Environment variables override file values. Restart the API
after changes because settings and the engine are cached per process. Do not use
`.env` or `.env.example` for configuration.

Frontend Supabase variables belong only in **`frontend/.env.local`**:

```dotenv
NEXT_PUBLIC_SUPABASE_URL=<project-url>
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<publishable-key>
```

Never put DATABASE_URL or a database password in the frontend or NEXT_PUBLIC_*
variables. Both `.env.local` files are ignored by Git; backend environment files
are excluded from Docker builds. Do not print, commit, or paste database credentials
into chat. The frontend keys do not supply a PostgreSQL connection credential.

## Local PostgreSQL first

Prerequisites: Python 3.12+, Docker with Docker Compose, and port 5432 available.
From the existing project root:

```sh
docker compose up -d
cd backend
# If a virtual environment is not already present:
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
alembic upgrade head
python db/scripts/check_database.py
python db/scripts/check_schema.py
python db/scripts/local_acceptance.py
uvicorn app.main:app --reload
```

Reuse the existing `.venv` when present; any Python 3.12+ interpreter works.
Docker Compose starts PostgreSQL 17 only. A native PostgreSQL 17 installation is
also supported when Docker is unavailable, provided it has the database/user in
`backend/.env.local` and is reachable at the configured host/port.

- Health: http://localhost:8000/health
- Swagger: http://localhost:8000/docs
- OpenAPI: http://localhost:8000/openapi.json

Health returns `{"status":"ok","service":"counton-api"}` with HTTP 200.
Database tools and read-only SQL are grouped under [backend/db](backend/db/README.md).
Application persistence remains under `backend/app/db/`.

## Manual Swagger acceptance

In Swagger, create three separate expectations using
`POST /api/v1/expectations` (expect HTTP 201):

```json
{
  "claim": "My next electricity bill will be lower",
  "type": "numeric_comparison",
  "metric": "total_cost",
  "comparison": "less_than",
  "baseline": 142.1,
  "evidence_sources": ["utility_bill"],
  "materiality_threshold": 0.05
}
```

For the first ID, call `POST /api/v1/expectations/{id}/evidence`
(expect HTTP 201):

```json
{
  "source": "utility_bill",
  "metric": "total_cost",
  "value": {"amount": 162},
  "unit": "USD",
  "observed_at": "2026-10-01T20:00:00Z",
  "confidence": 1.0,
  "raw_data": {}
}
```

Call `POST /api/v1/expectations/{id}/evaluate` (HTTP 200). Expect MISMATCH;
`GET /api/v1/expectations/{id}` should show contradicted status.
For the second ID, use the same evidence with `{"amount": 130}`. Expect MATCH
and fulfilled. For the third ID, add only this evidence:

```json
{
  "source": "utility_usage",
  "metric": "energy_usage_change",
  "value": {"percentage": -18},
  "unit": "percent",
  "observed_at": "2026-10-01T20:00:00Z",
  "confidence": 1.0,
  "raw_data": {}
}
```

Evaluate the third ID: expect UNKNOWN and monitoring, with
`no_relevant_evidence` for total_cost. Read evaluation history through
`GET /api/v1/expectations/{id}/evaluations`. Delete your three manual examples
with `DELETE /api/v1/expectations/{id}` (204) when finished. Scripted acceptance
performs these scenarios through services and automatically cleans its own rows.

## Switch the same backend to Supabase

After local acceptance passes, use the existing project's **Connect** dialog to
get its PostgreSQL connection string. Supply the database password, percent-encode
reserved characters, change the scheme to `postgresql+psycopg://`, and use TLS.
Save the completed string as DATABASE_URL in `backend/.env.local`, without printing
it. Keep APP_NAME, ENVIRONMENT and LOG_LEVEL as appropriate.

Use a direct connection for migrations when reachable; a session-pooler connection
on port 5432 is the fallback for an IPv4-only workstation. Copy the host/username
from Connect. The transaction pooler on port 6543 is not the intended connection
for this unchanged backend. [Supabase connection guidance](https://supabase.com/docs/guides/database/connecting-to-postgres).

From `backend`, with the environment active and any old exported DATABASE_URL unset:

```sh
python db/scripts/check_database.py
alembic upgrade head
python db/scripts/check_schema.py
python db/scripts/supabase_acceptance.py
uvicorn app.main:app --reload
```

Expected acceptance output: PASS MISMATCH, PASS MATCH, PASS UNKNOWN, then
SUPABASE ACCEPTANCE PASSED. Restart an existing API process after switching.
Re-run the Swagger flow against the restarted backend if desired.

Alembic is the only source of schema creation; the existing revision
`1bbc27e27689` creates the three tables, enums, indexes, and cascading foreign keys.
Do not replace it with SQL-editor CREATE TABLE statements or `supabase db push`.
Applying the migration does not copy local data to Supabase. Test downgrade only
on disposable local databases; it deletes the core schema and its data.

## Tests

From the project root, with local Compose running, create a separate test database
once, then run the complete suite:

```sh
docker compose exec postgres createdb -U counton counton_test
cd backend
source .venv/bin/activate
export TEST_DATABASE_URL='postgresql+psycopg://counton:counton_dev_password@localhost:5432/counton_test'
pytest
```

Without TEST_DATABASE_URL, unit/health tests run and PostgreSQL integration tests
explicitly skip. Test databases must use postgresql+psycopg, end in `_test`, and
have a different name from the application database. Tests apply Alembic only to
that test database. API tests roll back each test's data; acceptance cleanup tests
create and delete their own committed rows. No SQLite substitution is used.
The existing baseline is 117 tests; new tests cover `.env.local`, late-arriving
evidence, sanitized tool failures, and acceptance cleanup success/failure.
Starlette currently emits a non-failing HTTPX TestClient deprecation warning.

## API routes and semantics

All routes have the `/api/v1` prefix:

| Methods | Path | Behavior |
| --- | --- | --- |
| POST, GET | `/expectations` | Create (201), or list with status/limit/offset |
| GET, PATCH, DELETE | `/expectations/{id}` | Read, update supplied fields, delete (204) |
| POST, GET | `/expectations/{id}/evidence` | Add (201), list by observed_at ascending |
| POST | `/expectations/{id}/evaluate` | Evaluate and persist (200) |
| GET | `/expectations/{id}/evaluations` | History, newest first |
| GET | `/expectations/{id}/evaluations/latest` | Latest result; 404 if none |

Missing expectations return 404; invalid input returns 422; database errors return
a generic 500. Numeric expectations require metric, comparison, and baseline or
target_value. target_value takes precedence, including zero. Latest evidence for
the exact metric means greatest observed_at, then created_at and UUID for ties;
a late-arriving older observation does not override a newer observation.

Numeric strings, booleans, NaN and infinity are rejected. Equality uses inclusive
relative tolerance; directional failures strictly below tolerance return MATCH.
Zero targets use absolute tolerance in the metric's units. Boolean expectations
assert True and accept actual booleans only. Temporal/event evaluation remains
UNKNOWN. UNKNOWN preserves status; resolved/cancelled statuses stay unchanged.
Units/sources are assumed normalized. Changes do not automatically re-evaluate.

## Current scope

Not implemented: Bedrock, MCP, Alexa+, Ring/Bee integrations, EventBridge,
scheduling, authentication, dashboard, frontend features, notifications, or causal
investigation. Compiler/investigator and adapter packages remain placeholders.
The API has no user access control and is intended for development. Frontend
publishable keys are not used to access the core tables by this backend.

## Backend container

Environment files are excluded from the build. From the project root:

```sh
docker build -t counton-api ./backend
docker run --rm -p 8000:8000 --env-file backend/.env.local counton-api
```

For a container talking to native PostgreSQL through Docker Desktop, change the
local DATABASE_URL host to `host.docker.internal` in backend/.env.local first.
For Supabase, use its configured endpoint. Apply migrations before starting the
container; application startup never creates tables.

## Verification recorded on 2026-10-01

Local PostgreSQL verification passed: connection, current Alembic revision,
MISMATCH/MATCH/UNKNOWN acceptance, all seven inspection SQL files, the live API
flow on port 8000, and 124 tests. Downgrade/enum cleanup/re-upgrade and metadata
consistency passed on a separate disposable local database. The existing core
migration and deterministic evaluators were left unchanged.

Docker is unavailable in the current workstation environment, so these checks
used PostgreSQL 17 directly. Supabase migration and remote acceptance are pending:
the configured DATABASE_URL still points to local PostgreSQL. The Supabase URL
and API keys do not provide the required PostgreSQL database password.
