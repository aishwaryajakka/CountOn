# Developer Setup

Start inside the existing CountOn checkout. This guide follows source entrypoints,
package scripts, `docker-compose.yml`, the Dockerfile and CI. It does not provision
cloud accounts or confirm that any existing deployment is current.

## Prerequisites

- Python **3.12** for the container/CI baseline; the local environment also has
  Python 3.14. Install the repository requirements with their shared constraints;
  the oscrypto source dependency also has an immutable commit and SHA-256 pin.
- Node.js **24** and npm; use `frontend/package-lock.json` with `npm ci`.
- Docker with Compose and local PostgreSQL access. Compose uses PostgreSQL 17;
  CI uses 16. Database tests require a separate loopback database and some require
  permission to create/drop isolated test databases.
- A Supabase Auth project for real sign-in and API/MCP user authentication.
- Optional AWS account/model access for conversational compilation and live Why.

## Configuration files and precedence

Pydantic Settings loads **`backend/.env.local`**, resolved from `app/core/config.py`.
Process environment overrides that file. Legacy `DATABASE_URL` is not the active
selector: configure `DATABASE_TARGET` and its matching URL below.

Next.js loads **`frontend/.env.local`**. Public variables are compiled into the
browser bundle; restart development or rebuild after changing them. Both files
are ignored by Git. Sample files are tracked instructions, not an automatic loader.
Do not `source` placeholder-filled dotenv examples as shell programs.

| Template | Purpose |
| --- | --- |
| `backend/production.env.sample` | Trusted production service requirements; incomplete until private deployment values are supplied |
| `backend/bedrock.env.sample` | Disabled-by-default model settings |
| `backend/alexa.env.sample` | ASK client/Skill and conversation configuration |
| `backend/amazon-auth.env.sample` | Optional Amazon UserInfo translator configuration |
| `backend/providers.env.sample` | Google/Microsoft OAuth, sync and optional push |
| `backend/monitoring.env.sample` | Monitoring worker defaults |
| `backend/notifications.env.sample` | Optional Resend/SMTP outbox |
| `frontend/.env.example` | Browser-safe public configuration and commented server settings |

Copy only the relevant options into the actual `.env.local` or service environment.
Keep optional secrets unset, not empty invalid encryption strings or literal
placeholders. A placeholder client ID/URL is not a connected provider.

## Backend environment

Create `backend/.env.local` with local values replacing the placeholders:

```dotenv
# Application
APP_NAME=CountOn
ENVIRONMENT=development
LOG_LEVEL=INFO

# Database: use the password configured for your local Compose service.
DATABASE_TARGET=local
LOCAL_DATABASE_URL=postgresql+psycopg://counton:<local-postgres-password>@127.0.0.1:5432/counton

# Supabase Auth: same project as the frontend, even when SQL is local.
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_PUBLISHABLE_KEY=<publishable-key>

# AWS / Bedrock: core API and evidence demos can run with inference disabled.
BEDROCK_ENABLED=false
AWS_REGION=us-east-2
BEDROCK_MODEL_ID=openai.gpt-oss-120b-1:0

# Conversation state: memory is a development-only option.
CONVERSATION_STORE_BACKEND=memory

# MCP and CORS: leave the public URL unset for an ordinary local server.
MCP_HOST=127.0.0.1
MCP_PORT=8003
MCP_ALLOWED_ORIGINS=[]
ALLOWED_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]
```

URL-encode special characters in a database password. Keep the `postgresql+psycopg`
driver. Selecting `supabase` instead requires `SUPABASE_DATABASE_URL`; production
also requires TLS (`sslmode=require` or certificate verification). API, MCP and
workers must select the same application database. Never point a test fixture at it.

## Install and database migrations

From the repository root:

```sh
docker compose up -d
docker compose ps
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pip check
alembic upgrade head
python db/scripts/check_database.py
python db/scripts/check_schema.py
```

Alembic imports all registered models and uses `settings.database_url`.
`backend/db/sql/` contains inspection queries, not replacement CREATE TABLE scripts.
Do not copy another branch's migration chain or stamp an unknown schema.
[Database operations](../backend/db/README.md) cover local/Supabase differences.

## Start FastAPI and MCP

From an activated backend environment:

```sh
uvicorn app.main:app --reload
```

In another terminal, activate the same environment:

```sh
cd backend
source .venv/bin/activate
python -m app.mcp
```

| Surface | Local address |
| --- | --- |
| API and OpenAPI UI | `http://localhost:8000`, `/docs` |
| API health/readiness | `http://localhost:8000/health`, `/ready` |
| MCP | `http://127.0.0.1:8003/mcp` |
| MCP health/readiness | `http://127.0.0.1:8003/health`, `/ready` |

Business endpoints require a verified Supabase access token; no runtime test-user
bypass is enabled. With missing Auth configuration, health may respond while
authenticated requests fail. Readiness checks database/schema, not OAuth or AWS.

## Frontend environment and run

In a new terminal, from the repository root:

```sh
cd frontend
cp .env.example .env.local
```

Set the public project URL/publishable key, API origin and canonical frontend origin.
Use `http://localhost:8000` and `http://localhost:3000` locally. Required names are
`NEXT_PUBLIC_API_BASE_URL`, `NEXT_PUBLIC_SUPABASE_URL`,
`NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` and `NEXT_PUBLIC_APP_URL`.
`COUNTON_MCP_URL` is server-only for the discovery route; `/alexa` conversation
actions instead reach FastAPI, whose MCP destination is `MCP_PUBLIC_URL`.
For local conversational actions set that backend destination to
`http://127.0.0.1:8003/mcp` when using the normal port.

```sh
npm ci
npm run dev
```

Open `http://localhost:3000`. Configure Supabase email confirmation, SMTP/recovery
and approved auth callback URLs. The existing callback is `/auth/callback`; the
recovery page is `/reset-password`. [Authentication](authentication.md) contains
the exact project/provider settings and Amazon sign-in limitations.

## Enable language interpretation deliberately

Set `BEDROCK_ENABLED=true` only on trusted Python services. Use the normal AWS
credential provider chain (for example, an existing authenticated AWS profile or
a deployment-provided workload credential source). Do not add AWS credentials to
frontend configuration. Verify access using existing tools:

```sh
python db/scripts/aws_preflight.py --verify-identity
python db/scripts/bedrock_smoke.py --live
```

The live smoke incurs a real configured-model request. Offline tests do not.
Configure a strong private `COUNTON_CLARIFICATION_SIGNING_KEY` identically on API
and MCP before compiler-backed conversation. Production also needs
`CONVERSATION_STORE_BACKEND=postgres` and a shared private
`CONVERSATION_ENCRYPTION_KEY` encoding 32 random bytes. OAuth provider credentials
use the separate `INTEGRATION_TOKEN_ENCRYPTION_KEY`. Generate/store keys privately;
never paste real values into documentation or commit them.

## Optional workers and provider setup

From `backend/` in its activated environment, after configuring each capability
on the same database:

```sh
python -m app.integrations.worker --once
python -m app.monitoring.worker --once
python -m app.notifications.worker --once
```

Remove `--once` for supervised long-running operation. These require respectively
`PROVIDER_SYNC_ENABLED`, `MONITORING_ENABLED` and `NOTIFICATION_EMAIL_ENABLED`.
Enabling a worker does not authorize a source; users still connect and approve
bindings. [Integrations](integrations.md) and [deployment](deployment.md) cover
consent, callbacks, independent worker supervision and safe rollout.

## Verify the setup

Sign up/sign in, open the dashboard and run the three explicitly simulated evidence
demos. Follow their normal record links and reload. Use [testing](testing.md) for
isolated test databases, MCP smoke and the full command set. ASK needs the separate
[Developer Console checklist](traditional-alexa.md); a local `/alexa` page is not
proof that a physical Echo or native Alexa+ onboarding is configured.
