# CountOn authentication acceptance

Status as of **2026-10-13** on `feature/alexa-mcp`. This report distinguishes
implemented behavior from externally verified behavior. No production Auth setting,
credential, deployment or database migration was changed.

## Acceptance result

| Capability | Implementation | Local validation | Real-account status |
| --- | --- | --- | --- |
| Email/password signup | Native Supabase `signUp`; 12-character client minimum; neutral duplicate response | PASS (SDK boundary/UI tests) | BLOCKED: no test signup or SMTP delivery performed |
| Email confirmation/resend | Exact CountOn callback and native Supabase confirmation/resend | PASS (callback and UI tests) | BLOCKED: email delivery not exercised |
| Password login | Native `signInWithPassword`; requires returned session, token and user | PASS | BLOCKED: no live password login performed |
| Password recovery | Native reset email, PKCE callback intent, owned-session password update | PASS | BLOCKED: no live recovery email performed |
| Session restore/refresh/logout | Official `@supabase/ssr`, cookie-backed PKCE, Auth events, local sign-out | PASS | PARTIAL: SDK-tested; deployed refresh/revocation not exercised |
| Protected pages | Next.js proxy calls `auth.getUser()` and fails closed | PASS | Not independently probed against Vercel in this pass |
| FastAPI authentication | Supabase issuer/audience/signature/expiry/role/UUID checks | PASS | Fixture-signed tokens; no new live token probe |
| Amazon sign-in | Native Supabase `custom:amazon` flow plus bounded UserInfo translator | PASS for contracts and fixtures | **BLOCKED: provider is not publicly advertised and no Amazon login produced a Supabase session** |
| Amazon link/unlink | Native `linkIdentity`/`unlinkIdentity`, current-user revalidation, safe recovery requirement | PASS for UI/SDK contracts | BLOCKED: no real identity linked or unlinked |
| Profile identity | `profiles.id` equals Supabase `auth.users.id`; idempotent bootstrap preserves data | PASS with PostgreSQL | No production write performed |
| RLS/tenant isolation | Owner policies for profiles, expectations, evidence, evaluations and operational tables | PASS in disposable PostgreSQL | Production policy deployment not changed or probed |
| MCP identity | Bearer token resolves through the same Supabase verifier; no payload `user_id` | PASS | Existing public MCP was not live-probed without a test token |
| Alexa identity | Linked Supabase access token is verified; OAuth client is allowlisted and restricted | PASS with signed ASK/token fixtures | BLOCKED: no ASK console/Echo account-link test |
| Ring/Bee simulator ownership | Normal authenticated evidence API and expectation owner checks | PASS | Simulated by design; grants no provider access |

## Implemented files and routes

Frontend auth behavior is in:

- `frontend/app/login/page.tsx` — password login, confirmation resend and Amazon entry.
- `frontend/app/register/page.tsx` — password signup and confirmation feedback.
- `frontend/app/forgot-password/page.tsx` and
  `frontend/app/reset-password/page.tsx` — recovery request and password update.
- `frontend/app/auth/callback/route.ts` — one-time PKCE code exchange, safe redirect,
  same-user linking check and recovery routing.
- `frontend/lib/supabase.ts`, `frontend/lib/auth/server.ts` and `frontend/proxy.ts` —
  official browser/server clients, cookie refresh and protected-route verification.
- `frontend/components/amazon-sign-in.tsx` and
  `frontend/components/account-security.tsx` — login, explicit linking and guarded unlink.

Backend identity behavior is in:

- `backend/app/core/auth.py` — strict Supabase JWT verification.
- `backend/app/api/dependencies.py` — principal/profile resolution and linked OAuth
  client restrictions.
- `backend/app/api/v1/amazon_auth.py` — `GET /api/v1/auth/amazon/userinfo`; it
  translates a validated Amazon subject for Supabase and never issues a session.
- `backend/app/mcp/http.py` and `backend/app/mcp/auth.py` — the same bearer identity
  for all six MCP tools.
- `backend/app/api/v1/alexa.py` — `POST /api/v1/alexa`; signed ASK requests use the
  linked Supabase access token and the same owner UUID.
- `backend/alembic/versions/3a874e01bb52_supabase_identity_rls.py` and later RLS
  migrations — Auth FK, owner policies and backend-only operational writes.

User-facing routes are `/register`, `/login`, `/forgot-password`,
`/reset-password`, `/auth/callback` and `/settings`. Protected application routes
include `/dashboard`, `/expectations`, `/integrations`, `/activity`,
`/notifications`, `/settings`, `/alexa` and `/oauth/consent`.

## Identity contract

Supabase Auth is the only password, identity and session authority. A verified
Supabase access token supplies one UUID `sub`. That UUID becomes `profiles.id` and
the owner key for expectations, provider connections, evidence through its parent
expectation, evaluations, monitoring jobs, notifications, conversation state and
audit history. Profile creation uses `INSERT ... ON CONFLICT DO NOTHING`, so a
second login method cannot overwrite an existing profile.

Email and Amazon can reach the same CountOn data only when Supabase has linked both
identities to the same Supabase user. Matching email is never used for merging.
Amazon's `profile:user_id` scope grants identity only. It grants no access to
orders, Ring, Alexa history, Bee data, Gmail, Outlook or calendars.

Alexa account linking is separate from Login with Amazon. ASK receives a CountOn
Supabase access token from the Supabase OAuth server; it does not use an LWA token.
MCP likewise accepts only a CountOn Supabase bearer token.

## Amazon compatibility decision

Login with Amazon is OAuth 2 authorization code capable and supports PKCE, but it
must not be treated as OIDC: CountOn assumes no discovery document or ID token.
The compatible path is Supabase's custom OAuth2 provider with:

- authorization: `https://www.amazon.com/ap/oa`
- token: `https://api.amazon.com/auth/o2/token`
- scope: `profile:user_id`
- stable identity: Amazon `user_id`, translated to `sub`
- callback registered in Amazon:
  `https://ctpvhospspchgtquvalc.supabase.co/auth/v1/callback`
- UserInfo:
  `https://counton-api.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com/api/v1/auth/amazon/userinfo`

The translator verifies token audience, Amazon issuer, positive remaining expiry,
and matching subjects from token introspection and profile. It returns only `sub`.
The LWA client secret stays in Supabase. `AMAZON_CLIENT_ID` is used by the trusted
backend for audience validation. The frontend receives neither value.

This architecture is compatible in code and fixture tests. It is not accepted as
live until Amazon redirects successfully, Supabase exchanges the code, the app
callback obtains a valid Supabase session, `auth.getUser()` returns the expected
user, and that user can read the correct owned CountOn records.

## Required configuration

Supabase Auth:

- enable email signup and **Confirm email**;
- set Site URL to `https://counton-frontend.vercel.app`;
- allow the exact production and local `/auth/callback` URLs;
- configure authenticated SMTP, sender verification, SPF/DKIM and rate limits;
- use at least a 12-character password policy and leaked-password protection;
- enable manual identity linking;
- create the `custom:amazon` OAuth2 provider described in
  [authentication.md](authentication.md), with PKCE enabled and email optional;
- never map or request Amazon email for implicit account merging.

Amazon Security Profile:

- configure the real app/company name and privacy URL;
- add the exact Supabase callback above as an Allowed Return URL;
- store the client ID/secret only in Supabase/operator secret storage;
- request only `profile:user_id`.

Frontend/Vercel variable names:

```dotenv
NEXT_PUBLIC_APP_URL=https://counton-frontend.vercel.app
NEXT_PUBLIC_SUPABASE_URL=https://ctpvhospspchgtquvalc.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<publishable key>
NEXT_PUBLIC_API_BASE_URL=https://counton-api.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com
NEXT_PUBLIC_AMAZON_AUTH_ENABLED=true
```

Backend/Lightsail variable names:

```dotenv
AMAZON_AUTH_ENABLED=true
AMAZON_CLIENT_ID=<Amazon Security Profile client ID>
SUPABASE_URL=https://ctpvhospspchgtquvalc.supabase.co
SUPABASE_PUBLISHABLE_KEY=<publishable key>
```

Alexa account linking additionally requires the existing Supabase OAuth server,
registered confidential Alexa client, `OAUTH_ALLOWED_CLIENT_IDS`,
`ALEXA_OAUTH_CLIENT_ID`, `ALEXA_SKILL_ID`, durable conversation settings and the
exact ASK redirect URLs shown by the Alexa Developer Console. See
[traditional-alexa.md](traditional-alexa.md).

## Minimal authentication audit

Supabase Auth remains authoritative for signup, sign-in, password recovery, token
refresh/revocation and identity link/unlink audit records. CountOn does not accept
browser-authored "successful sign-in" records because those would be forgeable.
The application creates one backend-owned `profile.created` audit event when a
verified Supabase UUID first reaches CountOn. Application actions, integrations,
evidence, evaluations, notifications and orchestration already write redacted,
owner-bound audit events. Audit payloads contain no passwords, password hashes,
tokens, codes, cookies or OAuth responses.

Before production acceptance, configure retention/access for Supabase Auth audit
logs and verify that account creation, success/failure, recovery, refresh/revocation
and identity link/unlink events are present. If centralized CountOn copies are later
required, ingest signed server-side Auth hooks or exported Supabase audit events;
do not add an unauthenticated/client-asserted audit endpoint.

## Validation results

Validation used credential-free source snapshots and disposable local databases:

- Backend: **1,297 passed**, 104 warnings; Python 3.12 clean Linux environment.
- Ruff: PASS.
- Mypy: PASS for 149 application files; strict configured scope PASS for 37 files.
- Alexa dependency/startup smoke: PASS.
- Production smoke: PASS, including API startup, six MCP contracts, Streamable
  HTTP ownership, signed Alexa verification, confirmed capture and persistence.
- Synthetic orchestration evaluation: 26/26 PASS, zero Bedrock calls.
- Bandit, pip-audit and `pip check`: PASS.
- Frontend: **234 passed**, one existing opt-in live test skipped.
- Frontend lint, typecheck and production build: PASS.
- npm runtime/full audits: PASS, zero vulnerabilities.
- Redacted Gitleaks source and history scans: PASS, zero findings.
- `git diff --check`: run again at final handoff.

Important covered cases include invalid callbacks, forged cookies, safe redirects,
PKCE cookies, rate-limit/error normalization, signup confirmation, recovery,
same-user callback linking, duplicate identity protection, guarded unlink, JWT
issuer/audience/signature/expiry/role checks, OAuth client restrictions, RLS owner
reads/writes, FastAPI cross-user denial, MCP ownership and Alexa linked identity.

## Remaining blockers and manual acceptance

1. Enable and configure `custom:amazon` in Supabase and the Amazon Security Profile.
   The public Supabase settings did not advertise Amazon during this audit.
2. Perform a real Amazon new-user login and existing-user explicit link. Verify the
   Supabase UUID before/after, owned expectations, refresh, logout and guarded unlink.
3. Exercise email confirmation and recovery through production SMTP and confirm
   delivery, expiry, replay and rate-limit behavior.
4. Configure and test the confidential Alexa OAuth client in ASK. A real ASK/Echo
   interaction has not been accepted.
5. Verify Supabase Auth audit-log retention and the production RLS deployment.

Until steps 1–2 succeed, the accurate Amazon status is **implemented and locally
tested, not live verified**. No Supabase token is fabricated, no service-role
impersonation is used, and no production identity migration is proposed.
