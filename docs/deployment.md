# Deployment

## Verified deployment shape

The repository supplies a Python 3.12 backend Dockerfile, local PostgreSQL Compose
service and GitHub Actions workflow. The frontend is a Next.js project suitable
for Vercel. Existing runbooks name Lightsail API/MCP and Vercel frontend addresses;
those addresses are deployment references, not proof that the current code is live.
No provider or production endpoint was exercised by this documentation rewrite.

Use separately supervised processes from the existing backend image/codebase:

| Process | Command | Role |
| --- | --- | --- |
| FastAPI | `uvicorn app.main:app --host 0.0.0.0 --port 8000` | API, ASK adapter, trusted conversation route |
| MCP | `python -m app.mcp` with container `MCP_HOST=0.0.0.0` | Streamable HTTP on configured port, default 8003 |
| Provider sync | `python -m app.integrations.worker` | Enabled, authorized account synchronization |
| Monitoring | `python -m app.monitoring.worker` | Due evaluation jobs and recovery |
| Email outbox | `python -m app.notifications.worker` | Optional enabled delivery channel |

The image's default command starts FastAPI only. Workers are not scheduled by the
frontend or automatically launched by that command. Each requires its enable flag
and appropriate configuration. All must select the same database. API/MCP must
share the clarification signing key; API replicas share conversation encryption
configuration. Provider/delivery workers use the protected integration encryption key.

## Database migrations

**Inspect the live database migration revision before running production migrations.**

From the intended backend image, with privately injected database configuration:

```sh
alembic heads
alembic current
alembic history
```

Review backup/restore, actual schema and the approved release migration path before
applying `alembic upgrade head`. Do not blindly stamp head, import another branch's
chain or assume an older image can use the newest database. Local migration-cycle
tests do not authorize a production downgrade; review data loss and restore first.
`backend/db/README.md` and the operational runbook describe diagnostics and isolated
backup/restore smoke. No production migration is executed by this documentation task.

## Environment handling

Use `backend/production.env.sample` as a checklist, not a ready credential file.
Production validation requires Supabase database selection with TLS, configured
Auth project/public key, explicit HTTPS CORS origins and PostgreSQL conversation
storage with a valid private key. Enabling ASK adds registered client/Skill,
confirmation and MCP URL requirements. Keep provider and notification services
disabled until their dependencies are provisioned and consent is established.

The Python image excludes `.env*` and local environments via `.dockerignore`.
Inject secrets at runtime through the platform's protected environment/store.
Database URLs, AWS keys, OAuth client secrets and encryption/signing keys never
belong in browser variables or image/source layers. Provision AWS credentials via
a verified SDK provider source; do not assume a Lightsail container has an IAM role.

For non-streaming Converse, the deployment principal needs `bedrock:InvokeModel`
on approved model/profile resources and any required profile destinations.
Confirm account/model access separately with the existing preflight/smoke scripts.
The application does not need broad Bedrock agent-deployment permissions.

## MCP edge and authentication

Expose canonical HTTPS `/mcp`; preserve Host, Authorization, method and path.
`MCP_PUBLIC_URL` configures the exact SDK Host allowlist. Configure explicit
`MCP_ALLOWED_ORIGINS` only for actual browser clients; normal server clients omit
Origin. TLS termination, edge body limits/timeouts and proxy policy are platform
responsibilities. `python -m app.mcp` does not trust forwarded headers by default.
Every `/mcp` request, including initialization/discovery, requires a bearer token.
Health/readiness remain public. See [MCP deployment](mcp.md#remote-deployment).

## Frontend deployment

Use `frontend` as the project root; install with `npm ci`, build with
`npm run build`. No `vercel.json` currently exists or is required by this guide.
Configure these at build time using the existing Supabase project:

```dotenv
NEXT_PUBLIC_API_BASE_URL=https://<api-host>
NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<publishable-key>
NEXT_PUBLIC_APP_URL=https://<frontend-host>
```

`COUNTON_MCP_URL=https://<mcp-host>/mcp` is a server-only discovery destination.
Conversational actions use the API base and the backend's `MCP_PUBLIC_URL` instead.
Optional Amazon sign-in and Alexa consent have separate public enable/client/
redirect configuration, documented in [authentication](authentication.md) and
[traditional Alexa](traditional-alexa.md). OAuth client secrets remain protected.
Changing public build variables requires rebuilding the frontend.

Configure API `ALLOWED_ORIGINS` as a JSON list of exact frontend HTTPS origins.
Its parser rejects paths, trailing slash, credentials, queries and wildcard origins.
API CORS and MCP Origin policy are separate controls. Supabase auth callback and
OAuth redirect allowlists must also match actual deployed routes.

## Health and readiness

Both Python services expose `/health` and `/ready`. FastAPI health identifies
`counton-api`; MCP health identifies `counton-mcp`. Readiness verifies registered
tables/columns and the expected Alembic revision, returning safe failures.
Readiness does not certify AWS, Supabase OAuth, mail-provider access, a running
worker or external delivery. FastAPI `/metrics` requires its operations token.

Rate limiting and aggregate metrics are process-local. Account for replica counts
and edge controls; this is not a shared distributed quota/telemetry system.

## Production verification checklist

1. Approve the exact code/image, backup and migration revision; verify `/ready`.
2. Verify real Supabase sign-in and issued JWT contract, then cross-user denial.
3. Initialize MCP, discover all six tools and perform owned calls through real HTTP.
4. Run approved live Bedrock smoke and language/grounding acceptance; validate ASK's
   short response budget with the deployed model/network.
5. Confirm provider consent, source bindings, sync coverage and worker supervision;
   exercise permission expiration and restart recovery.
6. Run the three explicitly simulated evidence demos and verify SQL/notification/
   audit identifiers through the normal dashboard after reload.
7. Verify actual email delivery only if enabled; an inbox row is not an email receipt.
8. Complete ASK Console linking and actual Echo acceptance before claiming real voice
   integration. Native Alexa+ onboarding is a separate unverified integration.
9. Check safe logs, TLS, key rotation, retention and backup restoration. Re-run hosted
   CI after review; local results alone are not hosted CI or deployment evidence.

[Production readiness](production-readiness.md) retains detailed operational checks;
[testing](testing.md) records this checkout's executed local commands.
