# CountOn Frontend

## Purpose

The Next.js App Router application displays persisted CountOn expectations,
evidence, evaluations, notifications and audit history. React, strict TypeScript,
Supabase SSR/browser clients and shared CSS tokens provide the UI. Fonts are
[self-hosted](public/fonts/README.md); builds need no Google Fonts connection.

## Main routes/pages

| Route | Purpose |
| --- | --- |
| `/` | Redirect to the dashboard |
| `/login`, `/register` | Supabase email/password and optionally configured Amazon sign-in |
| `/forgot-password`, `/reset-password`, `/auth/callback` | Recovery, confirmation and PKCE callback |
| `/oauth/consent` | Supabase OAuth-server consent for the linked ASK client |
| `/dashboard`, `/expectations` | Shared owned records and current persisted results |
| `/expectations/new`, `/expectations/[id]` | Confirm structured criteria; inspect evidence, history and approved sources |
| `/demos` | Exactly three backend-persisted scenarios with DEMO/SIMULATED evidence |
| `/alexa` | Authenticated conversational web simulator; not an official Amazon simulator |
| `/integrations`, `/settings/integrations` | Connections, consent, sync and Ring/Bee simulator controls |
| `/notifications`, `/activity`, `/quality`, `/settings` | Inbox, persisted audit, quality summary and account/preferences |

The internal server routes are `/api/agent` for controlled conversation and
`/api/mcp` for MCP discovery. They are not browser-selected tool executors.

## Data responsibility

**The frontend renders backend evaluation results. It must not calculate
MATCH / UNKNOWN / MISMATCH.** `lib/api.ts` reads and mutates normal workspace data
through authenticated FastAPI APIs. The Supabase client manages authentication;
it does not write CountOn application tables directly.

Alexa-created and web-created expectations use the same owned API records.
Detail shows current criteria separately from historical evaluation snapshots,
evidence provenance, notifications and real audit events. Known trusted creation
sources get compact labels; Ring/Bee simulations remain visibly simulated.
The backend retains explanation receipts, not exact past speech: requesting a
grounded explanation obtains a fresh backend response. Rendering does not invoke
Bedrock automatically.

Successful mutations refresh relevant resources. Existing focus/30-second
revalidation and browser reload read persisted state; no separate Alexa store is
used. UNKNOWN remains distinct from unevaluated monitoring and stored lifecycle
status. Source selection/confirmation is separate from expectation capture.

## Environment setup

Use Node.js 24 and npm. From this directory:

```sh
cp .env.example .env.local
```

Replace placeholders with the same Supabase project's public values as the backend:

```dotenv
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<publishable-key>
NEXT_PUBLIC_APP_URL=http://localhost:3000
# Optional, server-only discovery destination:
COUNTON_MCP_URL=http://127.0.0.1:8003/mcp
```

The API base is an origin, without `/api/v1`. Production requires a remote HTTPS
origin and the canonical frontend URL. Public values enter the browser bundle;
rebuild after changing them. `.env.local` is ignored. Never put AWS credentials,
database URLs, service-role keys, provider secrets or private test tokens here.
`COUNTON_MCP_URL` is server-only; conversation actions reach FastAPI's shared
orchestrator, whose destination is backend `MCP_PUBLIC_URL`.

Supabase handles signup, confirmation, password recovery, session refresh and
logout. Next.js Proxy verifies protected pages with `getUser`; backend API/MCP
requests independently verify the current bearer and ownership. Amazon remains
optional and disabled until compatible provider setup and live acceptance.
Configure ASK public client/redirect values only when using native OAuth consent.
See [setup](../docs/setup.md), [authentication](../docs/authentication.md) and
[security](../docs/security.md).

## Install

```sh
npm ci
```

## Development

Start the configured FastAPI backend first; also run MCP and enable trusted
Bedrock access for language compilation. Then:

```sh
npm run dev
```

Open `http://localhost:3000`. The [demo guide](../docs/demo-guide.md) covers the
three evidence scenarios; these do not require live Ring/Bee hardware.

## Test

```sh
npm test
```

Normal Vitest tests use Auth/API fixtures. The live MCP case is opt-in, not proof
of cloud access when skipped. Existing browser scripts are documented in
[testing](../docs/testing.md), [Alexa demo](docs/alexa-demo.md) and
[MCP client](docs/mcp-client.md). Use dedicated users and private environment
credentials; do not export browser tokens or session artifacts.

## Lint

```sh
npm run lint
```

## Typecheck

```sh
npm run typecheck
```

## Build

```sh
npm run build
npm start
```

For a credential-free compile check only:

```sh
NEXT_PUBLIC_API_BASE_URL=https://api.counton.invalid npm run build
```

Do not deploy that validation artifact. A build does not verify API connectivity,
Supabase login, Amazon consent or Alexa/Echo behavior.

## Vercel production

Deploy this directory as a Next.js project with its default build/output settings;
no `vercel.json` is needed. Configure the public variables above and server-only
MCP destination as appropriate. Backend CORS uses `ALLOWED_ORIGINS` as a JSON array
of exact frontend origins. Authentication callbacks must also be approved in
Supabase. See [deployment](../docs/deployment.md) for the separate API/MCP/worker
services and verification gates. Existing deployment addresses are targets, not
live acceptance evidence from this documentation pass.
