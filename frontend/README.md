# CountOn Frontend

Next.js App Router, React, strict TypeScript, plain CSS with shared design tokens,
Lucide icons, and Supabase Auth. Space Grotesk and Inter use `next/font/google`
and are served locally after the build. There was no existing application or
package manifest in this repository's frontend directory; no framework was replaced.

## First-time setup

Prerequisites: Node.js 24 LTS, npm, and the existing FastAPI backend with migrations
applied. Google Fonts must be reachable during the initial build.

```sh
git pull
cd frontend
npm install
cp .env.example .env.local
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

Open **http://localhost:3000**. Backend CORS already allows this origin. FastAPI
must be available at the configured API URL. The same frontend works when the
backend selects `DATABASE_TARGET=supabase`; the browser never selects a database.
See the [database README](../backend/db/README.md) for migration and seed commands.

## Authentication and demo user

Login uses Supabase email/password authentication. The [supported Auth client](https://supabase.com/docs/reference/javascript/auth)
persists and refreshes the session. Its [Auth subscription](https://supabase.com/docs/reference/javascript/auth-onauthstatechange)
updates the app on sign-in/sign-out and is removed on unmount. Protected pages
redirect to login; FastAPI verifies the actual JWT and enforces ownership. A 401
clears the local session. No Google OAuth or registration UI is advertised.

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
| `/login` | Email/password sign-in |
| `/dashboard` | Actual expectations, latest results, evidence context and dynamic counts |
| `/expectations` | Cards and filters by presentation status |
| `/expectations/new` | Conversational claim → explicit manual criteria → confirmation → API create |
| `/expectations/[id]` | Expectation, all evidence/history, latest evaluation, sources and timeline |
| `/integrations` | Real account metadata; modeled accounts labeled; provider modal marked coming soon |
| `/notifications` | Actual notifications; mark read or dismiss through FastAPI |
| `/activity` | Limited activity derived from creation/latest evaluation timestamps |
| `/settings` | Read-only authenticated identity and timezone |

`lib/api.ts` is the single authenticated client. It attaches Bearer authorization,
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

No compiler endpoint exists: manual interpretation is explicitly labeled and
isolated in `lib/manual-expectation.ts`. No natural-language inference is faked.
Temporal/event expectations can be saved but cannot yet be deterministically
evaluated. Utility usage and rate changes are contextual observations, not proof
of causation. The app does not add scheduling, ingestion adapters, notification
delivery, OAuth, editing APIs, or backend business logic.

Dashboard/list data is shared in a workspace provider. Creation refetches it;
notification updates refetch only after a successful PATCH. A failed update keeps
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
for Next's plugins on ESLint 10, without disabling rules. npm currently reports
non-blocking peer warnings from those plugins; TypeScript is pinned to 6 because
the lint parser does not yet support 7.

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
local FastAPI process for database-target verification. Both targets were tested
with the actual demo account; tagged demo records remain seeded for review.
`COUNTON_E2E_QUICK=1` runs the same functional checks at desktop width only.
`COUNTON_E2E_AUTH_ONLY=1` isolates the session/expiry checks on the seeded account.
API requests in this rapid audit are paced at 300ms intervals to respect the
backend's existing rate limit. The application does not bypass that limit.
The audit also checks every protected route while signed out, per-route refresh,
back/forward navigation, drawer keyboard focus, logout, and a real SDK token refresh.
Controlled API 401 and invalid-refresh responses test expiry recovery separately;
those injected failures are not production data or authentication fallbacks.

Verified on 2026-10-02: **32 unit tests**, type checking, ESLint, and production
build passed. Chromium verified empty and seeded accounts, real Auth/JWT → API,
responsive layouts, normal console output, creation and notification mutations
on both backend database targets. Test-created expectations were removed; the
canonical Auth account and seeded dataset remain available. Private credentials
were absent from repository-visible files and the compiled browser bundle.

## Second-pass audit

The starting baseline passed all **32 tests**, TypeScript, lint, and production
build. No schema, migration, or evaluator was changed in this pass.
The final unit suite has **42 passing tests**; TypeScript, lint, and production
build pass with no build bundle warnings. Existing npm peer warnings are described
above. Baseline checks and the final build used the existing npm lockfile.
The current Stitch export remains the reference, including Create Expectation,
as requested. Styles remain in `app/globals.css`; there is no separate `styles/`
directory or second frontend.

Targeted fixes:

- Activity uses shared readable result labels instead of raw evaluator enums.
- Gmail source labels no longer assume a personal account. Meeting titles only
  shorten claims that actually express the stated time boundary.
- Auth events take precedence over a delayed session restore, preventing stale
  identity from reappearing after sign-out or token refresh.
- API errors normalize malformed JSON, hide upstream server details, explain
  rate limits, and retain request references.
- Calendar labels use the profile timezone across year and daylight-saving boundaries.
- Mobile drawers make background content inert, restore focus, and provide larger
  controls. Short viewports can scroll navigation; long values wrap safely.
- Input placeholders use the existing accessible secondary text color. Shared
  tokens cover control borders, primary hover, and attention backgrounds.

The source audit found no production billing amounts, percentage observations,
demo account names, or fake connection arrays. Integration names are API fields;
identity comes from Auth. The dedicated demo portrait association remains explicit
and does not supply application data. Mock datasets stay in tests.

The live audit identified a blocking Auth defect: a freshly issued Supabase JWT
had an `iat` one second ahead of the local clock and was rejected with 401. The
backend change is limited to a five-second JWT clock-skew allowance using
[PyJWT leeway](https://pyjwt.readthedocs.io/en/stable/usage.html#expiration-time-claim-exp),
with Python regression tests. Signature, issuer, audience, role and required
claims remain enforced; time claims allow at most the documented five seconds.
The audit also observed one remote 500 on an evaluation-history read; failed runs
are not counted as complete end-to-end passes. The full backend suite passes
**245 tests** against the dedicated local test database, including eight new
clock-skew tests. Its existing Starlette/HTTPX deprecation warning remains.
After the fix, complete desktop functional/auth journeys passed against both
local and Supabase PostgreSQL, with zero normal-flow console or JavaScript errors
and cleanup of each temporary expectation. All five widths were also checked;
the earlier full responsive screenshot sweep remains valid because the backend
Auth fix changes no layout. The earlier remote 500 did not recur in the final
run, but its underlying service cause was not established.

Changed application files: `app/globals.css`, `app/(workspace)/activity/page.tsx`,
`components/app-shell.tsx`, `components/auth-provider.tsx`, `lib/api.ts`, and
`lib/presentation.ts`. Verification changes are in `tests/api.test.ts`,
`tests/auth.test.tsx`, `tests/presentation.test.ts`, `tests/screens.test.tsx`, and
`tests/live-validation.mjs`, plus this README. Backend changes are limited to
`backend/app/core/auth.py` and `backend/tests/test_auth.py`. Earlier unrelated
workspace changes were preserved. Root README startup instructions remain concise.

Screenshots from the second pass are saved locally under ignored
`test-results/second-pass-local` and `test-results/second-pass-supabase`. These include
all six core screens at desktop and mobile sizes. Activity and Settings retain the
limited behavior described above; live providers and automatic interpretation are
not implemented. npm's existing ESLint plugin peer warnings remain non-blocking.
