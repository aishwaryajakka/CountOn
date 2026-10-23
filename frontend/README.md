# CountOn Frontend

Next.js App Router, React, strict TypeScript, plain CSS with shared design tokens,
Lucide icons, and Supabase Auth. Space Grotesk and Inter use `next/font/local`
with licensed, pinned assets in [public/fonts](public/fonts/README.md).

## First-time setup

Prerequisites: Node.js 24 LTS, npm, and the existing FastAPI backend with migrations
applied. Builds do not fetch Google Fonts. Set `NEXT_PUBLIC_API_BASE_URL` before
building; production requires an HTTPS origin. CI uses a credential-free validation
origin for its build artifact, which is never deployed.

```sh
git pull
cd frontend
npm ci
touch .env.local
```

Replace the two Supabase placeholders with the team's **public** configuration:

```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_SUPABASE_URL=<team-provided-url>
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<team-provided-public-key>
```

`.env.local` is ignored. Never put database credentials, administrative keys, or
demo credentials in frontend environment files. `NEXT_PUBLIC_*` values are built
into the browser bundle; rebuild/restart after changing them. Production API base
URLs should use HTTPS. The base URL is the API origin, without `/api/v1`.

## Vercel production

The server-side MCP integration and manual verification procedure are documented
in [docs/mcp-client.md](docs/mcp-client.md). Set `COUNTON_MCP_URL` in Vercel
Production before deploying that route. This is separate from the dashboard's
public FastAPI configuration below.

Configured frontend address: **https://counton-frontend.vercel.app**.
This guide does not verify the current live deployment. Deploy the `frontend`
directory as a Next.js project; use `npm run build` and the default Next.js
output settings. No `vercel.json` is required.

Configure these variables for the `counton-frontend` Vercel Production environment
and verify their presence before deployment:

```env
NEXT_PUBLIC_API_BASE_URL=https://counton-api.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com
NEXT_PUBLIC_SUPABASE_URL=<existing Supabase project URL>
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<existing public publishable key>
```

These three public values belong in the browser configuration. Server-only
`COUNTON_MCP_URL` configures the internal MCP route; no private backend key belongs
in either browser or Vercel configuration. Backend credentials remain on
Lightsail. `.env.local` and `.vercel/` are ignored. Production rejects missing,
non-HTTPS, or localhost API configuration. Environment changes require a rebuild.

From the repository root, with an authenticated Vercel CLI:

```sh
cd frontend
npm ci
npm run build
vercel link --project counton-frontend
vercel --prod
```

If the CLI is unavailable, install it with `npm install -g vercel` and run
`vercel login`. The API's `ALLOWED_ORIGINS` must include
`https://counton-frontend.vercel.app`; preserve its other origins. A different
custom domain or preview origin needs its own explicit CORS entry.

The stable project alias is also supported. For the documented API, frontend and stable alias, configure this JSON-array
`ALLOWED_ORIGINS` value (enter it directly, without extra shell quotes):

```env
ALLOWED_ORIGINS=["https://counton-api.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com","https://counton-frontend.vercel.app","https://counton-frontend-aishwaryajakkas-projects.vercel.app"]
```

Pydantic Settings parses the environment variable as a `list[str]` from JSON;
comma-separated text is not the supported format. Origins must match exactly,
without a trailing slash. Updating Lightsail environment settings requires a
new API deployment. No origin is hardcoded in backend source.

For connection failures, the browser console reports `CountOn API request failed`
with failure category, method, API origin, route, status, duration, and request
reference when available. It omits tokens, headers, bodies, query values and
upstream error details. Status `0` means the browser could not obtain a response;
check CORS preflight, connectivity and the actual page origin. HTTP `401` means
the API responded and rejected the session; HTTP `5xx` needs backend investigation.
The expectations request is `GET /api/v1/expectations?limit=100&offset=0`, with
`Authorization: Bearer <Supabase access token>`.

For automatic GitHub deployments,
add the GitHub login connection in Vercel, connect `aishwaryajakka/CountOn`, and
set its Root Directory to `frontend`. Supabase email/password authentication
continues to use the existing project and session flow.

## Run locally

Backend terminal, from the repository root:

```sh
cd backend
source .venv/bin/activate
DATABASE_TARGET=local uvicorn app.main:app --reload
```

Frontend terminal:

```sh
cd frontend
npm run dev
```

Open **http://localhost:3000**. Backend development CORS defaults allow this origin; verify any overrides. FastAPI
must be available at the configured API URL. The same frontend works when the
backend selects `DATABASE_TARGET=supabase`; the browser never selects a database.
See the [database README](../backend/db/README.md) for migration and seed commands.

## Authentication and demo user

Login uses Supabase email/password authentication. The [supported Auth client](https://supabase.com/docs/reference/javascript/auth)
persists and refreshes the session. Its [Auth subscription](https://supabase.com/docs/reference/javascript/auth-onauthstatechange)
updates the app on sign-in/sign-out and is removed on unmount. Protected pages
redirect to login; FastAPI verifies the actual JWT and enforces ownership. A 401
clears the local session. Registration, email confirmation/recovery, and explicit Amazon linking are implemented. Amazon remains disabled until provider setup and live acceptance. See [authentication setup](../docs/authentication.md).

The dedicated demo account is **Ashley Mccormick**, **demo@counton.app**. Obtain
its password through the team's secure shared channel. Login is normal Auth,
with no special frontend database. Seed the selected backend using its existing
`setup_demo_user.py` and `seed_demo_data.py` tools. With local PostgreSQL, configure
the demo Auth UUID as `COUNTON_DEMO_USER_ID` in backend configuration so the signed-in
user owns the seeded rows; an unrelated local UUID will correctly show an empty account.
The supplied portrait is used only for this demo account; other users get initials.

## Routes and behavior

| Route | Behavior |
| --- | --- |
| `/` | Redirects to `/dashboard` |
| `/login` | Supabase email/password and configured Amazon sign-in |
| `/register` | Supabase signup and confirmation feedback |
| `/forgot-password`, `/reset-password` | Supabase recovery and password update |
| `/auth/callback` | Server PKCE exchange; no tokens in redirect URLs |
| `/alexa` | Authenticated Alexa+ hackathon conversation through the controlled backend orchestrator, real MCP discovery/actions, stateful clarification and grounded Why explanations; see [demo guide](docs/alexa-demo.md) |
| `/dashboard` | Actual expectations, latest results, evidence context and dynamic counts |
| `/expectations` | Cards and filters by presentation status |
| `/expectations/new` | Conversational claim → explicit manual criteria → confirmation → API create |
| `/expectations/[id]` | Expectation, all evidence/history, latest evaluation, sources and timeline |
| `/integrations` | Provider OAuth actions, sync health, calendar selection; modeled accounts labeled; live acceptance required |
| `/notifications` | Actual notifications; mark read or dismiss through FastAPI |
| `/activity` | Persisted redacted audit history, evidence stream, and expectation lifecycle timestamps |
| `/settings` | Identity, verified recovery email and explicit Amazon link/unlink |

`lib/api.ts` is the authenticated FastAPI client for normal workspace data.
`lib/mcp/client.ts` is the separate authenticated internal-route client for `/alexa`. It attaches Bearer authorization,
handles errors/request IDs, paginates backend array responses, and bounds concurrent
latest-evaluation reads. `lib/types.ts` mirrors the existing OpenAPI contracts.
FastAPI `/docs` and `/openapi.json` are the source of truth. Coordinate contract
changes before altering backend schemas; evaluator logic belongs only in Python.
The UI never queries application tables using the Supabase client.

Status presentation distinguishes `UNKNOWN` from unevaluated `monitoring`, uses
latest results, and preserves resolved/cancelled states. Values, evidence, counts
and timelines come from FastAPI, not the Stitch sample dataset. Date formatting
uses the Auth profile timezone when available, otherwise the browser timezone.

## Scope and design

Implemented from the supplied calm Stitch screenshots, `calm_clarity/DESIGN.md`,
brand image, and portrait. The older export was not available; at the user's
direction, Create Expectation follows the current design. HTML was layout guidance
only. Unsupported prototype claims about live sync, enclaves, causal AI, uptime,
plans and delivery preferences were omitted.

The normal Create Expectation form uses explicitly labeled manual criteria in
`lib/manual-expectation.ts`. `/alexa` instead uses the implemented backend compiler
and stateful clarification through the six-tool MCP surface; it never uses browser
regexes to build arbitrary capture payloads. See [the conversational demo](docs/alexa-demo.md).
Temporal/event monitoring uses explicit criteria and real occurrence evidence; reply absence additionally requires verified source coverage. Utility usage and rate changes are contextual observations, not proof
of causation. The UI uses existing backend APIs for provider consent/source binding, scheduling, condition edits and owned notification preferences. Business logic stays in the backend. See [automatic tracking](../docs/automatic-tracking.md).

Dashboard/list data is shared in a workspace provider. Creation refetches it;
visible dashboard/detail/inbox data also refreshes every 30 seconds and on focus. Notification updates refetch only after a successful PATCH. A failed update keeps
the current notification. No full-page reload is used for mutations. Lists load
all API pages up to 5,000 records; a large-scale cursor/aggregate dashboard needs a
future coordinated API change. Filters are client-side because waiting status is
derived from latest evaluations rather than stored `monitoring` status alone.

Mobile uses an accessible drawer, focus trap/Escape dismissal, single-column
cards, stacked comparisons, and visible focus styles. The connection dialog uses
native modal focus behavior. Reduced-motion preferences disable animation.

## Build, lint and tests

```sh
npm run typecheck
npm run lint
npm test
npm run build
npm start
```

Normal Vitest tests mock Auth/API and need no live services. Tests cover session
restoration/sign-out, login, authorization, pagination, statuses, manual creation,
screen rendering, empty/error states and notification mutation recovery.
ESLint uses its [official compatibility utilities](https://eslint.org/blog/2024/05/eslint-compatibility-utilities/)
for Next's plugins without disabling rules. The current package/lockfile uses
ESLint 9 and TypeScript 6; the final audit records the actual install/lint/type
results rather than assuming historical peer warnings still apply.

Optional **live browser** verification requires a seeded demo account, the backend,
and a running production frontend. Supply `COUNTON_E2E_EMAIL` and
`COUNTON_E2E_PASSWORD` only through the test process environment, never committed files:

```sh
npx playwright install chromium
node tests/live-validation.mjs
```

The test checks sign-in/reload, the seeded journey, manual creation, invalid IDs,
and 1440/1280/1024/768/390px layouts. It also creates/evaluates evidence on its own
temporary expectation to test real notification read/dismiss, leaving the seeded
alert unchanged. It deletes only the expectation it creates, cascading its
evidence/evaluation/notification/job rows; the backend retains normal audit history. It
does not export session storage, traces or credentials. Screenshots go to ignored
`test-results/live`. `COUNTON_E2E_EXPECT_EMPTY=1` checks an unseeded account;
`COUNTON_E2E_API_BASE_URL` optionally points the same browser bundle to a separate
local FastAPI process for database-target verification. Use a dedicated account; seeded data availability must be checked separately.
`COUNTON_E2E_QUICK=1` runs the same functional checks at desktop width only.
`COUNTON_E2E_AUTH_ONLY=1` isolates the session/expiry checks on the seeded account.
API requests in this rapid audit are paced at 300ms intervals to respect the
backend's existing rate limit. The application does not bypass that limit.
The audit also checks every protected route while signed out, per-route refresh,
back/forward navigation, drawer keyboard focus, logout, and a real SDK token refresh.
Controlled API 401 and invalid-refresh responses test expiry recovery separately;
those injected failures are not production data or authentication fallbacks.

For the Alexa conversation, run the unit suite above and the opt-in browser
acceptance described in [alexa-demo.md](docs/alexa-demo.md). Backend tests cover
JWT clock skew, ownership and deterministic evaluation. Current test counts and
live deployment readiness must come from a fresh run; historical layout/Auth
audits do not certify the current intelligence rollout. Real Alexa/Echo account
linking, speech-to-text and live provider ingestion remain incomplete.

For traditional ASK account linking, `/oauth/consent` uses the same Supabase login
and native OAuth server. Set public `NEXT_PUBLIC_ALEXA_OAUTH_CLIENT_ID` and
`NEXT_PUBLIC_ALEXA_REDIRECT_URIS` (comma-separated exact console callbacks), then
rebuild. No client secret, AWS credential or service-role key belongs in these
variables. The login return path is restricted to this consent flow. See
[production setup](../docs/production-readiness.md).

Provider Connect/Reconnect/Sync/Disconnect and expectation source bindings use the
existing authenticated FastAPI client. Configure only trusted backend provider secrets;
see [integration acceptance](../docs/integrations-acceptance.md). No provider token
or client secret is returned to the browser.

Source review on expectation detail uses the typed owned monitoring plan. Suggested
references show a reason and sync status; confirmation requires explicit selection.
Editing a source filter or a rejected/stale confirmation clears prior choices. Existing
manual binding remains available. Voice capture currently saves complete expectations;
account/order source selection must then be confirmed in the web detail view. See
[source orchestration](../docs/orchestration.md) and [validation](../docs/orchestration-validation.md).

Supabase sessions now use the official `@supabase/ssr` cookie/PKCE clients. Next.js
Proxy verifies protected pages with `getUser`; browser API/MCP requests still
forward the Supabase bearer token. Existing local-storage sessions require signing
in again after rollout; account UUIDs and data are unchanged. Production additionally
requires exact `NEXT_PUBLIC_APP_URL`. [Setup and live acceptance](../docs/authentication.md).

## Consolidated UI

The canonical frontend preserves Supabase authentication and the FastAPI/MCP
paths. `/settings/integrations` reuses `/integrations`; settings expose existing
notification preferences. The expectation builder still requires an explicit
preview/confirmation. Result and resolution panels display persisted evaluator
results, and Ring/Bee simulations use authenticated source-bound simulator APIs.
`/alexa?expectationId=<owned-uuid>&starter=Why%20did%20it%20fail%3F` opens an
explanation in the existing orchestrator. The ID is untrusted and MCP validates
ownership. AI advice and provider recommendations are not fabricated in the UI.
See [source decisions](../docs/consolidation-report.md).
