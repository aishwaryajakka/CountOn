# Database developer tools

`backend/app/db/` contains application persistence code: SQLAlchemy models,
metadata, engine, and sessions. This `backend/db/` directory contains developer
inspection SQL, verification scripts, and documentation. Nothing here replaces
Alembic or creates application tables.

Run the commands below from `backend`, with `.venv` active. Every tool loads the
same settings and engine as FastAPI, using `backend/.env.local`. Exported
environment variables take precedence; unset an old `DATABASE_URL` when switching
this file. Tools work from other working directories when invoked by full path.
They never print the connection URL, password, or exception traceback.

## Local workflow

Start PostgreSQL from the project root:

```sh
docker compose up -d
cd backend
source .venv/bin/activate
python -m pip install -r requirements.txt
alembic upgrade head
python db/scripts/check_database.py
python db/scripts/check_schema.py
python db/scripts/local_acceptance.py
```

Expected output includes four table PASS lines, revision `1bbc27e27689`, and:

```text
PASS MISMATCH
PASS MATCH
PASS UNKNOWN
LOCAL ACCEPTANCE PASSED
```

The acceptance runner uses existing services, including commits, then reads the
result and status with a fresh session. It tags its expectations with a unique
per-run UUID in `user_id`. Cleanup selects only that UUID and calls the existing
delete service; PostgreSQL cascades the associated evidence and evaluations.
Cleanup runs on both success and failure. A disconnected database can prevent
cleanup; the script exits non-zero rather than claiming success. No unrelated
rows are deleted, and no table is truncated.

`check_database.py` is read-only and reports database name, database user, and
PostgreSQL version. `check_schema.py` is read-only and checks the four required
public tables and that the applied revision matches the repository's Alembic head.
Missing tables, stale revisions, connection failures, or failed acceptance return
a non-zero exit code. Acceptance scripts modify only their own temporary rows.

## Supabase workflow

1. Complete local checks first.
2. In the existing Supabase project's **Connect** dialog, copy a PostgreSQL
   connection string and supply its database password locally.
3. Replace only `DATABASE_URL` in `backend/.env.local`. Use the
   `postgresql+psycopg://` scheme. Percent-encode reserved password characters and
   use TLS (`sslmode=require`, or stronger certificate verification if configured).
4. Restart FastAPI after switching; settings are cached and the engine is created
   once per process.
5. Run:

```sh
python db/scripts/check_database.py
alembic upgrade head
python db/scripts/check_schema.py
python db/scripts/supabase_acceptance.py
uvicorn app.main:app --reload
```

Use the direct connection for Alembic when reachable. For an IPv4-only workstation,
a session-pooler connection on port 5432 is the alternative. Copy its actual host
and project-specific username from Connect. Avoid the transaction pooler on port
6543 for this unchanged persistent backend; it has different prepared-statement
and session behavior. See [Supabase's connection guide](https://supabase.com/docs/guides/database/connecting-to-postgres).

The local and Supabase acceptance entry points share one implementation; only
`DATABASE_URL` and the final output label differ. Expected final output is
`SUPABASE ACCEPTANCE PASSED`. A frontend publishable key is not a database password
and cannot authenticate SQLAlchemy or Alembic.

Schema deployment is **`alembic upgrade head`**, not `supabase db push`, SQL-editor
CREATE TABLE commands, or `Base.metadata.create_all()`. This applies the same core
migration without importing local rows. Do not use `alembic stamp` to hide missing
tables. Never run a downgrade against Supabase data that you need to keep. Validate
downgrade/re-upgrade on a disposable local database only.

## Inspection SQL

All files in `sql/` are read-only. Run them in a local PostgreSQL client or the
Supabase SQL editor connected to the intended project:

| File | Purpose |
| --- | --- |
| `inspect_tables.sql` | Public table names/types |
| `inspect_expectations.sql` | Expectations and status |
| `inspect_evidence.sql` | Evidence ordered by observed_at, newest first |
| `inspect_evaluations.sql` | Evaluation history |
| `inspect_constraints.sql` | Foreign keys, targets, and ON DELETE rules |
| `inspect_indexes.sql` | Public indexes and definitions |
| `sanity_report.sql` | Per-expectation evidence/evaluation counts without join multiplication |

Do not pass a password-bearing URL on a command line or paste it into logs/chat.
The SQL files intentionally contain no database connection configuration.

## Migration review

`alembic/versions/1bbc27e27689_create_core_counton_tables.py` creates expectations,
evidence, and evaluations; four PostgreSQL enum types; UUID, JSONB and ARRAY
columns; and the required indexes. Both child expectation foreign keys have
ON DELETE CASCADE. Downgrade drops children before expectations, then removes
the enum types. The migration is unchanged by this database-tooling task.
