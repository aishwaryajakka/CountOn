# Unified CountOn integration

This document describes the code on `feature/alexa-mcp` as inspected on
2026-10-13. “Implemented” means that a code path and automated tests exist.
“Live verified” is reserved for a successful call to the real provider in the
current environment.

## System boundary

CountOn has one application identity: the `sub` in a verified Supabase access
token. FastAPI resolves that subject to `profiles.id`; expectations, evidence,
evaluations, notifications, provider connections, source bindings, Bee imports,
audit events, Alexa sessions, and MCP calls use that same UUID. Browser code
never receives the Supabase secret key, provider client secrets, provider refresh
tokens, AWS credentials, or the integration encryption key.

```text
Next.js / Alexa ASK / MCP client
               |
       Supabase bearer token
               v
 FastAPI identity and ownership checks
               |
       PostgreSQL / Supabase
      /          |           \
 connections  expectations  audit history
      |          |  |  |
 OAuth sync  evidence | notifications
                 evaluation
                    |
          deterministic MATCH / UNKNOWN / MISMATCH
                    |
          Bedrock interpretation/explanation only
```

Alexa account linking authorizes the Alexa skill to act as the linked CountOn
user. Login with Amazon is a separate optional sign-in provider. Neither grants
Amazon orders, Alexa history, Ring, or Bee access. Amazon order evidence is
derived only from a user-authorized Gmail or Outlook source with an exact order
identifier.

## Integration status

| Capability | Code status | Verification in this workspace | External requirement |
|---|---|---|---|
| Supabase email/password | Implemented with cookie-backed PKCE, signup, confirmation, login, reset, refresh, logout, and protected routes | Frontend auth tests; backend JWT tests | Live email delivery and production Supabase settings were not exercised in this pass |
| Login with Amazon | Supabase custom OAuth2 bridge implemented; Amazon token introspection returns only a stable `sub` | Mocked callback/config tests | Disabled locally; requires Supabase custom-provider and Amazon Security Profile configuration, then a real login producing a Supabase session |
| FastAPI/PostgreSQL ownership | Implemented with owner-scoped queries and composite owner foreign keys | Integration and cross-user tests | Production database migration remains an operator action |
| MCP | Six tools over Streamable HTTP: capture, get, list, compile, continue compilation, explain mismatch | MCP protocol/ownership tests | Current local config has no public MCP URL; no live public probe in this pass |
| Alexa Custom Skill | ASK signature/timestamp verification, account linking, conversation state, confirmation, MCP orchestration | ASK adapter tests | Alexa skill ID/account-linking config absent locally; ASK console/Echo not live verified |
| Bedrock | Runtime compiler, clarification, source interpretation seam, and grounded mismatch investigation | Mocked structured-output, timeout, grounding, and fallback tests | Disabled locally; real AWS invocation not performed |
| Gmail | Read-only OAuth, PKCE, initial/incremental history, push wake-up, refresh/revocation, encrypted checkpoint | Provider fixtures and worker tests | Google credentials, encryption key, and provider worker disabled locally |
| Google Calendar | Read-only OAuth, explicit calendar selection, incremental events and watches | Provider fixtures and worker tests | Same Google/provider configuration blocker |
| Outlook | Read-only OAuth, PKCE/form-post callback, delta sync, refresh/revocation | Provider fixtures and worker tests | Microsoft credentials, encryption key, and provider worker disabled locally |
| Microsoft Calendar | Read-only OAuth, explicit calendar selection, delta sync and subscriptions | Provider fixtures and worker tests | Same Microsoft/provider configuration blocker |
| Amazon order email | Exact order-ID correlation and conservative shipping facts from authorized mail | Normalization/correlation tests | Requires a live Gmail or Outlook connection; no direct consumer-order API is claimed |
| Ring | Authenticated simulator using confirmed expectation source permission; stable event IDs and explicit simulated provenance | Simulator/evaluator tests | Simulated only; no live Ring integration is claimed |
| Bee | Authenticated simulator with promise-versus-fulfilment separation | Simulator/evaluator tests | Simulated only |
| Bee CLI | Local pairing, short-lived connector credential, preview/consent/import, checkpoint, dedupe, revoke | Sanitized fixture and bridge tests | `bee` binary and authenticated Bee account unavailable; no real data read |
| Monitoring | Durable leases, restart recovery, bounded retries, source freshness, deterministic evaluation and notification dedupe | Worker, recovery, correlation, and notification tests | Provider worker must be deployed separately and enabled |
| Dashboard | Persisted expectations, evidence timeline, evaluations, notifications, connected services, simulators, Bee CLI, and redacted audit history | Frontend unit, lint, type and build checks | Production environment and provider consent must be configured |

The current local settings report Supabase URL/public/server credentials present,
while Amazon sign-in, Alexa, Bedrock, Google, Microsoft, provider sync, public MCP,
and the provider-token encryption key are disabled or absent. This report does
not treat code presence or mocked tests as live provider verification.

## Connection and credential model

`integration_connections` is safe user-facing metadata:

- `provider`, `user_id`, `connection_type`, and `status`
- approved read-only `scopes` and constrained metadata categories
- `connected_at`, `last_synced_at`, `failure_status`, and `revoked_at`
- a safe external account reference and display name

OAuth tokens are encrypted in `integration_credentials`. OAuth state/verifiers,
encrypted sync checkpoints/facts, webhook secrets, and Bee connector credential
digests use separate backend-only tables. The API returns only
`credential_state=configured|not_configured`, never token material. Provider
worker failures persist bounded codes such as `AUTH_REQUIRED` or
`PROVIDER_UNAVAILABLE`; exception text and provider payloads are not stored as
connection status.

Migration `c592d04e8f41_connection_lifecycle_metadata.py` adds the lifecycle
fields and backfills timestamps for existing connected/disconnected records.
It was exercised only against the dedicated local test database. It was not run
against production.

## Routes used by the unified experience

All `/api/v1` routes below are bearer protected unless explicitly described as a
provider callback/webhook with its own one-time-state or signature validation.

| Area | Routes |
|---|---|
| Expectations | `POST/GET /expectations`, `GET/PATCH/DELETE /expectations/{id}` |
| Evidence/evaluation | `POST/GET /expectations/{id}/evidence`, `POST /expectations/{id}/evaluate`, `GET /expectations/{id}/evaluations`, `GET /expectations/{id}/evaluations/latest` |
| Connections | `POST/GET /integrations`, `GET/PATCH/DELETE /integrations/{id}`, `GET /integrations/providers` |
| Provider OAuth/sync | `POST /integrations/{id}/oauth/authorize`, Google and Microsoft callbacks, `POST/GET /integrations/{id}/sync`, `POST /provider-sync/{id}/run`, `POST /integrations/{id}/disconnect` |
| Source approval | `POST /expectations/{id}/monitoring-plan/preview`, `POST /expectations/{id}/monitoring-plan/confirm`, and owned source-binding routes |
| Simulators | `POST /simulators/ring/expectations/{id}/events`, `POST /simulators/bee/expectations/{id}/events` |
| Bee CLI | `/integrations/bee-cli/pairings`, `/pair`, `/bridge/candidates`, `/status`, `/candidates`, `/imports`, `/disconnect` |
| Notifications/audit | `/notifications`, `/notifications/{id}`, `GET /audit-events` |
| Orchestration | `POST /agent/converse`, `POST /alexa`, Streamable HTTP `/mcp` |

Provider webhook routes validate provider-specific secrets, audiences, channel
tokens, or signed payloads and only wake an existing owned sync; they do not
accept user identity or evidence facts from an untrusted request.

## Evidence and source authorization

Normalized evidence retains `expectation_id`, source, exact metric, minimal typed
value, unit, confidence, provider observation time, ingestion time, stable
external event ID, and safe provenance. Provider source records and incremental
checkpoints are encrypted. Email normalization does not retain full bodies or
attachments. Calendar matching uses selected event IDs/UIDs and occurrence
identity. Email rules require an exact sender plus a thread, topic, or order ID;
an equal source type alone cannot correlate a record.

The flow is:

1. Compiler returns a typed expectation or one clarification question.
2. User explicitly confirms capture; the expectation is persisted once.
3. Source planner proposes only configured, authorized sources.
4. User confirms a monitoring plan; CountOn stores an owned source binding.
5. Provider worker reads the selected stream incrementally and normalizes facts.
6. The binding rule correlates an exact record to the expectation.
7. Evidence is inserted idempotently and retains provider time/provenance.
8. Deterministic evaluation writes MATCH, UNKNOWN, or MISMATCH history.
9. MATCH stays quiet; UNKNOWN continues monitoring; a new supported MISMATCH
   creates one deduplicated notification.
10. Bedrock may explain the recorded mismatch from cited evidence. It cannot
    assign or override the evaluator result.

Ring `package_not_detected` contains no asserted delivery value, so insufficient
evidence remains UNKNOWN. A Bee conversation or promise is context and does not
prove the promised event happened. Live Bee CLI and both simulators use distinct
provenance values (`LIVE_BEE_CLI`, `SIMULATED_BEE`, `SIMULATED_RING`).

## Frontend truth and audit behavior

The dashboard API client attaches the current Supabase access token and reads
persisted backend state. Connected Accounts distinguishes account authorization
from a successful sync, displays safe failure codes, and labels simulator/demo
records. The Activity page reads evidence and the new owner-scoped
`GET /api/v1/audit-events` endpoint. That endpoint allowlists user-visible audit
metadata; arbitrary metadata, tokens, provider payloads, and transcripts are
not returned.

The audit table records safe action names, actor/user ownership, resource and
expectation references, request correlation, timestamps, and allowlisted status
metadata. It does not store passwords, bearer tokens, refresh tokens,
authorization codes, cookies, whole emails, Bee transcripts, raw Alexa requests,
or audio.

## Manual provider setup still required

Set values only in the trusted backend runtime; use the frontend public variables
only for the Supabase project URL/publishable key and public API origin.

- Supabase: project URL, publishable key, trusted backend secret/JWKS/database
  configuration, approved site/redirect URLs, email templates and SMTP as needed.
- Amazon sign-in: enable the backend feature, configure the Amazon Security
  Profile and Supabase custom OAuth2 provider, and enable the frontend button.
  Complete an actual login and verify the resulting Supabase `sub` before calling
  it live.
- Alexa: skill ID, CountOn OAuth client registration/account-linking URLs,
  confirmed capture mode, public HTTPS ASK endpoint, public MCP URL, and durable
  PostgreSQL conversation storage. Validate in ASK console and on a linked device.
- Bedrock: enable it on the backend, select region/model, and supply AWS runtime
  credentials through the normal credential provider chain and least-privilege
  IAM.
- Google/Microsoft: client IDs/secrets, exact callback URIs, provider encryption
  key, read-only consent grants, optional webhook/Pub/Sub configuration, and the
  provider sync worker.
- Bee CLI: install the official CLI, authenticate locally, run the local bridge,
  pair with a one-time CountOn code, preview records, and explicitly approve an
  import. Bee credentials remain local.

## Validation evidence

Commands were run against the dedicated loopback `counton_test` database; no
application or production database was migrated.

| Check | Result |
|---|---|
| Full backend `pytest -q` | PASS — 1,304 tests |
| Focused integration matrix | PASS — 236 tests |
| Backend Ruff, using the CI scope | PASS |
| Backend app-wide mypy with missing third-party stubs ignored | PASS — 158 files |
| Configured strict AI/agent/Alexa/MCP mypy scope | PASS — 37 files |
| Production smoke | PASS — API/six MCP tools, Streamable HTTP ownership, signed Alexa, durable conversations, monitoring, source correlation |
| Synthetic orchestration evaluation | PASS — 26/26 synthetic cases; human review and live provider/model accuracy remain blocked |
| Alexa native crypto import smoke | PASS — default and ctypes backends |
| Bandit medium/high gate | PASS — no medium/high findings |
| `pip-audit` / `pip check` | PASS — no known vulnerabilities / no broken requirements |
| Frontend lint / typecheck | PASS / PASS |
| Frontend Vitest | PASS — 237 tests, one intentional skip |
| Next.js production build | PASS — 18 routes generated |
| npm production/high audit | PASS — zero vulnerabilities |
| Pinned Gitleaks history and source scan | PASS — zero findings |
| `git diff --check` | PASS |

The all-severity Bandit report contains only existing low-severity assertions,
the fixed-argument/no-shell Bee CLI subprocess call, and a deliberate blank
single-use token digest used to prevent replay. The repository's release gate is
the passing medium/high check above. The Bee bridge resolves only the installed
`bee` binary and supplies a fixed command allowlist; imported record content can
never become a command or argument.

No real Google, Microsoft, Amazon, Alexa, Bedrock, Ring, Bee hardware, or Bee CLI
account call was performed. No production migration, deployment, commit, or push
was performed.
