# CountOn authentication

## Pre-change audit — October 13, 2026

Branch `feature/alexa-mcp`, starting HEAD `b7f8745`. Unrelated untracked
`docs/person1-execution.md` and `scripts/person1_preflight.py` are preserved.

- Browser: singleton supabase-js client; password signup/login, SDK local-storage
  restoration/automatic refresh, auth events and local logout. Workspace and Alexa
  client gates exist; no proxy, cookie SSR client, confirmation callback or recovery.
- Signup did not set a confirmation redirect. URL session detection was disabled.
- FastAPI/MCP share the Supabase JWT verifier: project issuer, authenticated audience,
  RS256/ES256 JWKS signatures, expiry/iat/nbf, UUID subject, role and anonymous/client
  restrictions. Legacy HS256 additionally calls Supabase `/user` with a public key.
- `profiles.id` is the authenticated Supabase UUID. PostgreSQL upserts on that PK;
  profile fields/history are preserved. Supabase-aware migration links it to
  `auth.users` and installs owner RLS/FKs. No password or credential columns.
- Alexa has native Supabase OAuth authorization/explicit consent, signed ASK request
  verification and the same UUID authorization. LWA sign-in is distinct from that
  Alexa OAuth client grant. MCP has six tools, ownership checks and bearer auth.
- Google/Microsoft integrations store encrypted provider credentials separately;
  authorizing mailbox/calendar access does not change the CountOn login identity.
- Existing JWT, ownership, simulator authorization, MCP, Alexa and profile tests cover
  these boundaries. Their behavior remains canonical.

## Protocol decision

Supabase custom OAuth2 and PKCE are supported by the installed JS SDK. Amazon uses
OAuth2 authorization codes/PKCE and a profile API, not an assumed OIDC discovery/ID
 token. Native direct UserInfo mapping is not safe to assume: inspected Supabase Auth
`custom_oauth.go` parses into typed Claims before mapping, dropping Amazon `user_id`.
A small backend UserInfo normalization endpoint is therefore used; it never issues
sessions or writes identities. Supabase owns code exchange, state, PKCE, identity
linking and sessions. Amazon-only scope `profile:user_id` returns no email/name and
prevents same-email automatic identity merging. Explicit linking keeps the existing
Supabase UUID; an already-owned Amazon identity must be rejected by Supabase.

Sources:
[Supabase custom providers](https://supabase.com/docs/guides/auth/custom-oauth-providers),
[Supabase linking](https://supabase.com/docs/guides/auth/auth-identity-linking),
[Supabase provider implementation](https://github.com/supabase/auth/blob/master/internal/api/provider/custom_oauth.go),
[Amazon scopes](https://developer.amazon.com/docs/login-with-amazon/customer-profile.html),
[Amazon PKCE](https://developer.amazon.com/docs/login-with-amazon/javascript-sdk-reference.html),
[Supabase SSR](https://supabase.com/docs/guides/auth/server-side/creating-a-client).

## Implemented changes

Email signup/login now use exact redirects, neutral duplicate feedback and a
12-character minimum. Added resend, forgot/reset and server callback handling,
server-validated protected routes, canonical-origin redirects, sanitized failures,
recovery/email onboarding and explicit Amazon linking/unlinking. Added the narrow
stateless Amazon UserInfo translator and typed/default-off backend configuration.
The existing FastAPI/MCP JWT verifier, Alexa adapter, provider integrations, database
models and migrations remain unchanged. New tests cover protocol/security boundaries;
existing login fixtures now represent an actual successful SDK session.

## Setup and deployment gates

Nothing was deployed and no project provider, user or production schema was modified.
The UserInfo adapter defaults off; the Amazon buttons are visibly disabled until
configured. Read-only public project settings were checked: email enabled, signup
allowed, email confirmation required. Amazon was not advertised; admin custom-provider
configuration and real login remain unverified.

### Supabase email and browser/SSR settings

Use the existing project `https://ctpvhospspchgtquvalc.supabase.co`. Enable email
signup, **Confirm email**, secure email change and manual identity linking. Set the
production Site URL to `https://counton-frontend.vercel.app`. Keep exact callback
origins; no wildcard Vercel preview domains. Configure authenticated SMTP, sender
verification, SPF/DKIM and deliverability through Supabase; credentials stay there.
Use the standard confirmation/recovery templates with `{{ .ConfirmationURL }}` and
preserve RedirectTo. These PKCE links must be opened in the initiating browser.
Expired, reused or other-browser links fail closed; request a fresh link there.

Production callback endpoints are:

- Amazon → Supabase: `https://ctpvhospspchgtquvalc.supabase.co/auth/v1/callback`.
- Supabase → CountOn: `https://counton-frontend.vercel.app/auth/callback`.
- Local CountOn: `http://localhost:3000/auth/callback` (local testing only).

The app passes `next=%2Fdashboard`, `next=%2Fsettings`, and optional `mode=link` as
callback routing metadata. Register these exact variants for local testing; production
Site URL same-origin redirects also admit the native Alexa consent return. The app
validates destinations against its own narrow route allowlist, accepts no identity
from those parameters, and rejects access/refresh tokens and duplicate parameters.
Amazon's registered redirect is always the exact Supabase callback above, never an
app page or the UserInfo endpoint. See [Supabase redirect validation](https://github.com/supabase/auth/blob/master/internal/utilities/request.go).

Set password policy to at least 12 characters and enable leaked-password protection
if available. Configure Supabase's server-side signup/token/email rate limits and
SMTP sending quotas; UI disabled/loading controls are not rate limits. Errors are
sanitized, signup/reset feedback is enumeration-resistant, and 429 responses explain
that the user should wait. If enabling Supabase CAPTCHA, integrate its supported
widget/token flow before rollout; the present forms do not supply CAPTCHA tokens.

### Amazon Security Profile and native custom provider

In Amazon Developer Console, create a Login with Amazon Security Profile for CountOn,
with your actual company/app name, privacy notice and authorized production origin.
Under Web Settings register the exact **Supabase** callback as an Allowed Return URL.
The profile's client ID and secret configure Supabase, not the browser. Suggested
operator secret names are `LWA_CLIENT_ID` and `LWA_CLIENT_SECRET`; they are console/
provisioning inputs, not frontend runtime variables. Rotate the client secret there.
Do not change provider identifier or migrate existing identities without review.

Create this custom provider in Supabase Auth (substitute the real client ID/secret
privately; do not save a filled-in JSON document to Git):

```json
{
  "provider_type": "oauth2",
  "identifier": "custom:amazon",
  "name": "Amazon",
  "client_id": "<Amazon Security Profile client ID>",
  "client_secret": "<Secret entered only in Supabase>",
  "authorization_url": "https://www.amazon.com/ap/oa",
  "token_url": "https://api.amazon.com/auth/o2/token",
  "userinfo_url": "https://counton-api.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com/api/v1/auth/amazon/userinfo",
  "scopes": ["profile:user_id"],
  "pkce_enabled": true,
  "email_optional": true,
  "attribute_mapping": {},
  "custom_claims_allowlist": [],
  "enabled": true
}
```

Do not use OIDC auto-discovery, invent an Amazon ID token, set email_verified=true,
or request profile/email/postal/order/device scopes. The adapter returns only `sub`;
no email participates in automatic linking. Supabase receives Amazon's stable subject
but issues its own UUID and access/refresh tokens. The adapter independently checks
Amazon token introspection audience/issuer/positive remaining expiry and matches
UserInfo subject. It rejects foreign audiences, JWTs, invalid/oversized bodies and
redirects, with 5-second per-call bounds and no retries. It never writes profiles,
passwords, OAuth identities or CountOn sessions. urllib is used for introspection
because Amazon requires a query credential and HTTPX logs complete request URLs.
Neither request URLs, headers nor upstream exception/response contents are logged.
[Amazon token verification](https://developer.amazon.com/docs/login-with-amazon/implicit-grant.html#verify-access-tokens)
is used for introspection semantics only; the actual login uses code/PKCE, not implicit.

The backend must already be publicly reachable over HTTPS before configuring this
UserInfo URL. Its existing per-peer request limits also apply; tune shared Auth-server
traffic budgets at deployment without trusting arbitrary forwarded IP headers.
Supabase holds the secret and owns code exchange, signed CSRF state, upstream PKCE,
manual linking, single-use callback codes and session refresh. CountOn adds application
PKCE-cookie exchange, exact destination validation and same-user checks for link mode.

### Environment variables

`frontend/.env.local` locally; Vercel environment for future production builds:

```dotenv
NEXT_PUBLIC_APP_URL=https://counton-frontend.vercel.app
NEXT_PUBLIC_SUPABASE_URL=https://ctpvhospspchgtquvalc.supabase.co
NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY=<project publishable key>
NEXT_PUBLIC_API_BASE_URL=https://counton-api.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com
NEXT_PUBLIC_AMAZON_AUTH_ENABLED=true
```

Use `NEXT_PUBLIC_APP_URL=http://localhost:3000` and the local API origin in local
`.env.local`; keep Amazon false until the same native provider/UserInfo path is ready.
No AWS credentials, service-role key, LWA secret or database URL belongs in Vercel
public variables. A privileged key in the public-key field is rejected without echoing it.

Backend `.env.local` / Lightsail service environment (in addition to existing config):

```dotenv
AMAZON_AUTH_ENABLED=true
AMAZON_CLIENT_ID=<same Amazon Security Profile client ID>
```

`backend/amazon-auth.env.sample` is disabled by default. The LWA secret is not needed
by this backend because Supabase exchanges codes. No new database migration is needed.
Deploy/rebuild only after separately reviewing these changes; this task did neither.

## User journeys and identity safety

- Signup/login: native Supabase password methods. Confirmation is handled by server
  `/auth/callback`; resend and forgot/reset pages are available. Verified sessions
  open the existing dashboard and use the same bearer client to FastAPI and MCP.
- Sessions: official `@supabase/ssr` clients use PKCE and SameSite=Lax cookies (Secure
  in production). Proxy calls `getUser`, never trusts SSR `getSession`, forwards
  refreshed request cookies, and returns private/no-store responses. Browser Auth
  events remain synchronous and handle refresh/logout without stale restores.
- SDK cookies are intentionally browser-readable for the existing bearer clients;
  they are **not** described as HttpOnly. XSS prevention and CSP remain necessary.
  No protected server data should use unchecked browser/session metadata.
- Storage changes require existing users to sign in again after rollout. Their
  Supabase UUID, profile and expectations are unchanged; no identity/data migration.
- New Amazon login can have no email/name. The dashboard prompts for a verified
  recovery address in Settings. Supabase verifies that address; existing-email
  conflicts do not merge accounts or move expectations. Password setup/recovery
  also remains a Supabase operation.
- Existing account: sign in with the existing method first, then **Link Amazon**
  in Settings. Supabase enforces identity uniqueness; CountOn rechecks the current
  account and callback identity. If Amazon is already owned by another account,
  stop: no destructive merge, data transfer or identity reassignment is provided.
- Unlink: explicit confirmation plus a fresh owned-user read; unavailable when
  Amazon is the only identity or no verified email recovery method exists. Supabase
  performs the unlink. Test the alternate password method before confirming.
- Logout uses the existing native local signOut. As with Supabase JWT authentication
  generally, already-issued API JWTs remain valid until expiry; configure a short
  access-token lifetime. No competing revocation/session database was added.
- LWA grants identity only, not shopping orders, Ring, Alexa devices or Bee recordings.
  Google/Microsoft read permissions and Alexa OAuth grants remain separate.

## Manual acceptance (required before claiming real Amazon sign-in)

1. Start local backend/dependencies using the existing README; do not apply production
   migrations. Start frontend with `cd frontend && npm ci && npm run dev`.
2. Register a fresh test email, open its confirmation in the same browser, login,
   create a tagged expectation through CountOn, refresh and verify it remains owned.
3. Sign out; try protected `/dashboard`, `/alexa` and detail URLs. Verify redirect to
   login. Request reset, open link in the initiating browser, set password, test new
   login. Reuse/expire the old link and verify safe failure.
4. With Amazon configured, **new account**: Continue with Amazon → Amazon code/PKCE
   → Supabase → app callback. `profile:user_id` may not show a consent screen because
   it requests no profile PII. Confirm a real Supabase session via SDK `auth.getUser`
   without logging tokens. Verify the UUID matches the backend profile/expectation
   owner; sign out/repeat Amazon login and ensure the UUID/profile are unchanged.
5. **Existing account**: sign in to that email account, record its UUID/expectation
   IDs, choose Link Amazon. Complete Amazon authentication and verify the same UUID
   and expectations. With two accounts, attempt to link an already-owned Amazon
   identity and confirm denial; never merge based on matching email.
6. Add/verify a recovery email and password, test the alternate login, explicitly
   unlink Amazon, verify data preservation and correct recovery. An Amazon-only
   identity must not offer unlink. Test callback replay/changed-user/denied auth.
7. Confirm protected Ring/Bee submissions, six MCP tools and Alexa linking still
   use only Supabase tokens. Amazon tokens must fail normal API/MCP auth.
8. Inspect server/browser logs and URLs for credential leakage; never paste token
   values or credentials into screenshots/chat. Record live acceptance outcomes.

## Validation completed on 2026-10-13

- Backend clean Linux/Python 3.12 validation: 1,297 tests passed; Ruff, general
  mypy, strict intelligence mypy, production smoke, synthetic orchestration,
  Bandit, pip-audit and `pip check` passed.
- Frontend clean Linux/Node 24 validation: 234 tests passed and one opt-in live
  test skipped; lint, typecheck, production build and both npm audits passed.
- The repository's redacted Gitleaks source/history scan reported zero findings.
- Disposable PostgreSQL migration/RLS tests passed. No production migration ran.
- Public Supabase Auth settings were read only: email signup is enabled and email
  confirmation is required. This does not verify SMTP delivery.
- No real Amazon login, identity link/unlink, email delivery or deployed browser
  callback was exercised. The Amazon provider was not advertised by the public
  project settings at audit time.

No real Amazon login, Supabase user creation/linking, SMTP delivery or live deployment
was performed by this task. Public Auth settings do not prove custom-provider admin
configuration, email deliverability, deployed RLS or live Alexa/device acceptance.
