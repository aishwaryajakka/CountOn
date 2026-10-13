# Database workflows

`backend/app/db/` is application persistence. `backend/db/` holds developer
checks, acceptance tools and read-only inspection SQL. Alembic is the schema
source of truth; do not replace it with SQL table creation or `create_all()`.

## Schema

```text
Supabase auth.users → profiles (Auth FK on Supabase only)
profiles
   ├── expectations → evidence / evaluations / notifications / monitoring_jobs
   ├── integration_connections
   └── audit_events
Trusted backend → compilation_sessions (canonical clarification state and capture receipt)
```

Expectation ownership is required and indexed. Child data cascades on parent
deletion. Job ownership uses a composite FK to the expectation/owner pair;
notifications use a composite FK to the evaluation/expectation pair. Evidence header idempotency keys are unique within an expectation; optional
provider `external_event_id` is unique within expectation/source when non-null.
NULL permits ordinary unkeyed observations. A provider ID is deliberately not
unique across unrelated accounts/expectations. Audit parent references become NULL on expectation deletion;
profile deletion removes that owner's audit history.

Monitoring jobs have `id`, `expectation_id`, `user_id`, `status`, `next_run_at`,
`last_run_at`, `attempt_count`, `last_error`, and timestamps. Valid states are
pending/running/paused/completed/failed/cancelled. Attempts cannot be negative;
a partial unique index permits one pending/running/paused job per expectation.
The status/due-time index supports future workers. `last_error` is reserved for
safe error codes. Workers, leases, executions and external scheduling are absent.

## Migrations

| Revision | Change |
| --- | --- |
| `1bbc27e27689` | Original deterministic tables; unchanged |
| `2e0a91d54c31` | Portable profiles and mandatory ownership |
| `3a874e01bb52` | Supabase Auth FK, RLS and grants |
| `4bc128091ea7` | Operational tables, idempotency and ownership constraints |
| `5d201f68ac90` | Connected accounts, expanded notifications/audits, provider IDs and demo tag |
| `6e302a79bd01` | Durable compilation lifecycle and capture replay protection |

The ownership migration locks expectations and aborts if legacy rows require
backfill; it never invents identities or deletes those rows. The operational
migration is additive and does not retroactively invent jobs for older claims.
Supabase-specific SQL detects actual `auth.users`/`auth.uid()` independently of
the selector. Local migrations do not fabricate Auth tables or roles.

Upgrade both targets with `alembic upgrade head`. Run `alembic check` to compare
schema/metadata. Use disposable local databases for downgrade/re-upgrade tests;
downgrades remove operational/profile history. Never downgrade important Supabase
data. Plan backups, migration lock windows and restores before production changes.

## RLS

The eight domain tables have RLS on Supabase; the additional
`compilation_sessions` ledger enables RLS with no browser policies. `PUBLIC`/`anon` have no table
grants. Authenticated clients can access only their own rows:

| Table | Client permissions |
| --- | --- |
| profiles | SELECT, INSERT, UPDATE |
| expectations | SELECT, INSERT, UPDATE, DELETE |
| evidence | SELECT, INSERT |
| evaluations, notifications, monitoring_jobs, audit_events, integration_connections | SELECT |
| compilation_sessions | None; trusted backend role only |

Child policies check parent ownership. Backend-only writes produce evaluations,
notifications, jobs, audit events and integration writes. Read-only integration
client grants ensure metadata validation and audits cannot be bypassed through
PostgREST. FastAPI provides authenticated account CRUD and notification status
updates. No `USING (true)` policy is used. Privileged
PostgreSQL owner/service-role connections may bypass RLS: FastAPI therefore also
checks ownership. See [Supabase RLS](https://supabase.com/docs/guides/database/postgres/row-level-security).

## Database checks

From `backend/` with the virtual environment active:

```sh
python db/scripts/check_database.py
python db/scripts/check_schema.py
alembic check
```

Checks report target, connectivity, required tables and current revision without
printing URLs/passwords. `/ready` checks connectivity, migration head and table
presence; it exposes no internal failure details. Connection, pool and statement
timeouts are configured in backend settings.

## Local workflow

Store `LOCAL_DATABASE_URL` and the selector in gitignored `backend/.env.local`.
From the project root:

```sh
docker compose up -d
cd backend
source .venv/bin/activate
DATABASE_TARGET=local alembic upgrade head
DATABASE_TARGET=local python db/scripts/local_acceptance.py
TEST_DATABASE_URL='postgresql+psycopg://counton:counton_dev_password@localhost:5432/counton_test' pytest
```

The test URL must use loopback PostgreSQL and a separate database ending in
`_test`. Integration transactions roll back; concurrency tests explicitly clean
their unique profile. Migration tests create/drop a new disposable database.

## Supabase workflow

Store `SUPABASE_DATABASE_URL` from Supabase's Connect dialog with TLS enabled.
Configure the project's Auth URL/JWKS/public key in the backend; keep any admin
secret key backend-only. Use process overrides without rewriting the file:

```sh
DATABASE_TARGET=supabase alembic upgrade head
DATABASE_TARGET=supabase python db/scripts/check_schema.py
DATABASE_TARGET=supabase python db/scripts/supabase_acceptance.py
DATABASE_TARGET=supabase python db/scripts/operational_acceptance.py
DATABASE_TARGET=supabase python db/scripts/api_smoke.py
LOG_LEVEL=WARNING DATABASE_TARGET=supabase python db/scripts/supabase_identity_check.py
```

Token-based tools prompt with hidden input or read `COUNTON_ACCESS_TOKEN` from
the environment. The operational flow authenticates, upserts a profile, creates
a claim, retries keyed evidence, evaluates, verifies notification/audit/job
persistence and ownership, then removes only identified test artifacts.

The identity tool requires both databases migrated, a live Supabase FastAPI
server on localhost:8000, and backend `SUPABASE_SECRET_KEY`. It creates three
confirmed temporary Auth users without sending email, uses real access tokens
for both targets, tests cross-user isolation/RLS, and deletes only those users
and matching local test profiles. Cleanup failure reports FAIL. Inspect only
users with `app_metadata.counton_verification` if manual recovery is needed.

Acceptance cleanup removes its own tagged records and generated audit events;
ordinary application deletion retains redacted audit history. Existing profiles
are retained by token-based acceptance, except identities explicitly provisioned
and owned by the administrative verification tool.

## Application contracts and demo data

`integration_connections` stores owner, provider/type, optional external account
ID/display name, status, scopes, safe JSONB metadata, sync time and timestamps.
There is no one-account-per-provider uniqueness rule. Owner/filter indexes support
bounded API queries. Live OAuth and encrypted credentials are not implemented;
raw access/refresh tokens are rejected by the metadata API contract.

Notifications now have a required profile/expectation owner pair, type/channel,
message, metadata, sent time and pending/read/sent/failed/dismissed states. Existing
rows receive their actual parent owner in migration; no identity is invented.
The notification service persists MISMATCH notifications atomically and audits
creation; clients may mark records read/dismissed through FastAPI. Delivery is absent.

Audit events retain the existing `resource_id`, with the application alias
`entity_id`, plus `entity_type`, safe metadata, owner, optional expectation link,
action, request ID and created time. Owner/time indexes support inspection.
Audit writes are backend-controlled; owner reads are RLS-scoped.

The canonical demo profile is **Ashley Mccormick**, **demo@counton.app**,
with timezone **America/Chicago**. Configure in ignored backend `.env.local`:

```env
COUNTON_DEMO_EMAIL=demo@counton.app
COUNTON_DEMO_USER_ID=
COUNTON_DEMO_PASSWORD=
```

Obtain the password through the team's secure shared channel; it has no source
code default. Never put it in public frontend variables, commands or tracked files.

```sh
DATABASE_TARGET=local python db/scripts/setup_demo_user.py
DATABASE_TARGET=local python db/scripts/seed_demo_data.py
DATABASE_TARGET=local python db/scripts/clear_demo_data.py
DATABASE_TARGET=supabase python db/scripts/setup_demo_user.py
# Save the printed Auth UUID as COUNTON_DEMO_USER_ID in backend/.env.local.
DATABASE_TARGET=supabase python db/scripts/seed_demo_data.py
DATABASE_TARGET=supabase python db/scripts/clear_demo_data.py
```

`setup_demo_user.py` runs independently from the dataset. Local uses the unchanged
stable UUID `741dc8cd-6d44-5e2f-bdc9-ce8b6d3df1e1` unless explicitly overridden;
it never contacts Auth. Supabase uses backend `SUPABASE_URL` and
`SUPABASE_SECRET_KEY` to [look up users with the paginated Auth Admin API](https://supabase.com/docs/reference/javascript/auth-admin-listusers)
and [create a confirmed user](https://supabase.com/docs/reference/python/auth-admin-createuser)
only when missing. No confirmation email is sent. Existing accounts and passwords
are reused unchanged. A configured UUID must match the email lookup, otherwise
setup fails without replacing the account. Clear a stale UUID before creating a
missing account. Setup prints the UUID and readiness, never credentials, and does
not rewrite environment files. It creates/reuses the profile, updates canonical
name/timezone, and can adopt an existing profile only after verifying its Auth
email; unrelated application rows are preserved. Local setup refuses an untagged
profile belonging to an arbitrary configured UUID.

The stable tag is `counton-demo-v1`. Supabase seed/clear requires the real demo
Auth UUID in `COUNTON_DEMO_USER_ID`; no SQL is used to fabricate Auth state.
Demo account and application dataset have separate lifecycles: setup once,
seed → demo → clear → seed. Cleanup never deletes the Auth account. All six
connections are explicitly mocked, without OAuth credentials.

An outer database transaction surrounds the services' savepoint commits and an
advisory transaction lock serializes seeds for the same identity. Matching demo
rows/events/evaluations are reused; existing data is never overwritten. Cleanup
requires the demo owner and tags, removes only tagged audit events and cascades
children. Untagged rows/history are retained, including those owned by the same
profile; the profile is deleted only when no untagged data remains.

Expected seed summary: 6 connections, 5 expectations, 10 evidence rows,
5 evaluations, 1 notification. Bill MISMATCH; delivery and confirmed appointment
MATCH; conflicting calendars and after-hours temporal expectations UNKNOWN.
An untagged profile or conflicting existing evidence causes refusal and rollback.

## Inspection SQL

All files in `db/sql/` are read-only:

| File | Purpose |
| --- | --- |
| inspect_tables.sql | Public tables |
| inspect_profiles.sql | Profile metadata/demo tag |
| inspect_integrations.sql | Metadata-only connected accounts |
| inspect_expectations.sql | Claim state and owner |
| inspect_evidence.sql | Observations ordered by observation time |
| inspect_evaluations.sql | Deterministic history |
| inspect_monitoring_jobs.sql | Job state and due time |
| inspect_notifications.sql | In-app mismatch records |
| inspect_audit_events.sql | Redacted actions/request IDs |
| inspect_constraints.sql | Foreign keys/delete rules |
| inspect_indexes.sql | Indexes |
| sanity_report.sql | Per-expectation evidence/evaluation counts |

## Current verification scope

Run the checks above against the selected database and current migration head.
Historical local/Supabase checks do not prove the latest schema is deployed.
`check_schema.py` checks the domain tables and current Alembic revision;
`alembic check` compares metadata. The compilation ledger is also covered by
MCP lifecycle/integration tests on isolated PostgreSQL. Do not point tests or
downgrade commands at production data.
