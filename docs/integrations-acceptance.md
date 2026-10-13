# External evidence: implementation and acceptance

Status on 2026-10-11: **implemented locally, live acceptance blocked**. No Google
or Microsoft authorized test account/client configuration was available. No real
email or calendar event was sent, deleted, or modified. Fixtures exercise official
provider contracts; they are not live-success claims. This change has not deployed
services or migrated the production database.

## Audit and gap matrix

| Capability | Before this pass | Current local implementation | Live |
| --- | --- | --- | --- |
| Supabase login / owner isolation | Existing JWT identity | Reused unchanged; provider management denies delegated Alexa OAuth clients | Existing app auth; provider workflow unverified |
| Outlook OAuth | Encrypted PKCE, refresh, Mail.ReadBasic | Retained legacy subject-rule connector; new delegated Mail.Read account sync | Not verified |
| Gmail | Metadata-only records | Official read-only OAuth, message pages, history, token refresh | Not verified |
| Google Calendar | Metadata-only records | Authorized selection, expanded instances, sync tokens, cancellations | Not verified |
| Microsoft Calendar | Metadata-only records | Calendars.Read selection, default-calendar v1.0 delta, selected-calendar reconciliation, cancellations | Not verified |
| Push / checkpoints | Absent for account sync | Durable encrypted checkpoints, verified wake-ups, watch/subscription renewal | Not verified |
| Evidence linkage | Existing normalized evidence and Outlook job rule | Explicit owned source bindings; existing ingestion, evaluator and notification worker | Local PostgreSQL verified |
| Amazon orders | Generic user-entered evidence | Conservative authorized email order facts and documented manual input | No consumer API or carrier connection verified |
| UI | Metadata records, coming-soon modal | Real consent, reconnect, sync, calendar selection, source binding and disconnect actions | Production not redeployed |

The old branch is named `feature/bedrock-intelligence` (the requested hyphenated
name is absent). Its tree did not contain a reusable Gmail/Graph/calendar extraction
adapter. No old compiler, Bedrock client, clarification or SQL implementation was
copied. The stronger current intelligence remains canonical.

## Architecture and security

```text
Supabase authenticated user
  → owned integration record → provider OAuth consent + one-time PKCE state
  → existing encrypted integration_credentials
  → selected mailbox/calendar → provider_sync_states (durable lease/checkpoint)
  → official provider read → encrypted minimal provider_source_events
  → explicit expectation_source_bindings
  → existing Evidence service → existing monitoring worker
  → deterministic MATCH / UNKNOWN / MISMATCH → existing in-app notification inbox

verified provider push → wake account sync → official read (never webhook facts)
```

No new MCP tools, compiler or evaluator were introduced. Six existing MCP contracts,
Bedrock behavior and `/alexa` orchestration remain unchanged. AI does not decide
provider facts or deterministic outcomes. Email content is untrusted data; no raw
body, prompt or attachment content is stored or sent to Bedrock by these adapters.

Tokens, checkpoints, watch secrets and minimal cached projections use existing
AES-GCM with owner/connection or sync UUID as associated data. Backend-only tables
have RLS enabled and browser-role grants revoked. Composite owner foreign keys,
authenticated API queries and reconnect generation/lease fences enforce isolation.
Metadata alone cannot establish a full provider grant. Actual scopes and provider
account identity are validated before reads. Refresh is serialized; revoked grants
clear credentials and require reconnect. Changing the verified source account removes
old cursors/cache/bindings; reconnecting the same account resumes polling.

Requests use fixed official authorities/methods, no redirects or environment proxy,
10-second transport timeouts, bounded 2 MiB responses. No mail/event write endpoint
is allowed. Workers process bounded pages, use SKIP LOCKED and 30-minute leases,
fence stale completions, checkpoint atomically with projections/evidence, recover
expired leases, honor Retry-After and use exponential backoff. Eight failed attempts
stop in `error`; permission failures stop in `auth_required`. Sync now/reconnect
explicitly retries. Worker errors log allowlisted codes, not private provider payloads.

Only changed facts/rules create evidence. Stable source/version/rule keys suppress
repeated mail or calendar observations and duplicate mismatch notifications. Mail
observation time is the source receipt time; calendar observation time is the first
verified read of that version. Source modification and effective times remain in
provenance. A complete fresh calendar delta/reconciliation revalidates unchanged calendar state without duplicating evidence. Stale sources remain UNKNOWN. Reply absence now requires a covered deadline and trusted attestation; other missing events remain UNKNOWN. See [automatic tracking](automatic-tracking.md).

## Automatic evaluation

Account synchronization now wakes/reopens the existing monitoring job atomically with evidence publication. No manual evaluation or schedule reconfiguration is required after source setup. Run both workers. Bound calendars keep continuous monitoring after MATCH; provider health gates evaluation. [The automatic runbook](automatic-tracking.md) contains A–G acceptance, notifications and exact startup/recovery commands.

## Configuration and consent

Merge [providers.env.sample](../backend/providers.env.sample) into the **backend**
service environment or ignored `backend/.env.local`. Do not put client secrets,
refresh tokens or encryption keys in frontend/Vercel public variables. Defaults
keep both provider connectors and the sync worker disabled.

Required for the provider you enable:

- Shared `INTEGRATION_TOKEN_ENCRYPTION_KEY`: base64url encoding of 32 random bytes,
  identical for API and workers; securely back up it. Rotation needs decrypt/re-encrypt
  or deliberate reconnect, not simply replacing the key.
- Google: `GOOGLE_INTEGRATIONS_ENABLED=true`, `GOOGLE_CLIENT_ID`,
  `GOOGLE_CLIENT_SECRET`, `GOOGLE_REDIRECT_URI`.
- Microsoft: `MICROSOFT_GRAPH_ENABLED=true`, `MICROSOFT_CLIENT_ID`,
  `MICROSOFT_CLIENT_SECRET`, `MICROSOFT_TENANT_ID`, `MICROSOFT_REDIRECT_URI`.
- Worker: `PROVIDER_SYNC_ENABLED=true`, existing database configuration;
  optional `PROVIDER_SYNC_INTERVAL_SECONDS=900`, `PROVIDER_RETENTION_DAYS=30`.
- Evaluation worker: existing `MONITORING_ENABLED=true` and owned schedule.

Register exact backend callback URLs (replace the host with your API deployment):

```text
Google GET:    https://<API_HOST>/api/v1/integrations/oauth/google/callback
Microsoft POST form_post:
               https://<API_HOST>/api/v1/integrations/oauth/microsoft/callback
```

Google requests Gmail `gmail.readonly`, or calendar `calendar.readonly` plus `openid`
for calendar account identity. Enable Gmail and Calendar APIs, configure a web OAuth
client and approved test users/consent. Gmail readonly is restricted: public rollout
may require Google verification/security assessment and compliant privacy/retention
policies. See [Google OAuth](https://developers.google.com/identity/protocols/oauth2/web-server)
and [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes).

Microsoft requests `offline_access User.Read Mail.Read` for mailbox bodies, or
`offline_access User.Read Calendars.Read` for calendars. The legacy Outlook rule still
uses Mail.ReadBasic; use Reconnect through the new generic consent route for full
account sync. Register an Entra web app matching the configured tenant/account type;
organization policies may require administrator consent. No application-wide mailbox
permission or write permission is requested.

Supabase login is unchanged and remains separate from provider consent. Provider
callbacks resolve the user only from durable one-time OAuth state. Browser-provided
user IDs and credentials are rejected. Callbacks return a safe completion page;
return to `/integrations` and refresh the account list. Google uses a standard query
callback: configure edge/access logs to redact query parameters (the application's
structured Uvicorn formatter already avoids them).

### Optional push

Set `PROVIDER_WEBHOOK_URL=https://<API_HOST>/api/v1/integrations/webhooks`.
Polling is the recovery mechanism even when push is enabled.

Gmail requires an existing Google-project Pub/Sub topic, Gmail publisher permission
for `gmail-api-push@system.gserviceaccount.com`, and an authenticated push subscription
targeting `/gmail`. Configure all three `GMAIL_PUBSUB_TOPIC`,
`GMAIL_PUBSUB_AUDIENCE`, `GMAIL_PUBSUB_SERVICE_ACCOUNT`; the subscription OIDC audience
must exactly match. The handler verifies Google's RS256 signature, issuer, expiry,
audience, verified email and configured push service identity. It never accepts
history IDs as new facts/cursors. Gmail watch expiration is persisted and renewed
before expiry. See [Gmail push setup](https://developers.google.com/workspace/gmail/api/guides/push).

Google Calendar `/google-calendar` verifies channel ID, random token, resource ID
when registration is complete, and expiration; notifications only wake the selected
source. New channels overlap until older ones expire; watch metadata is persisted
before the initial Google sync notification. See [Calendar push](https://developers.google.com/workspace/calendar/api/guides/push).

Microsoft `/microsoft` reflects bounded plain-text validationToken for subscription
validation. Notifications require known subscription, unexpired registration and
constant-time clientState match. Missed/lifecycle events wake polling; removed/
reauthorization subscriptions are renewed/recreated. Event subscriptions watch the
signed-in mailbox's events; the pull remains limited to the selected calendar.
Renewal uses PATCH; no rich resource payload is trusted. See
[Graph webhook delivery](https://learn.microsoft.com/en-us/graph/change-notifications-delivery-webhooks)
and [subscription renewal](https://learn.microsoft.com/en-us/graph/api/subscription-update?view=graph-rest-1.0).

## Local operation and migration

Use the existing local PostgreSQL setup and environment. From the repository root:

```sh
docker compose up -d
cd backend
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Separate terminals, same backend environment:

```sh
cd backend
source .venv/bin/activate
python -m app.integrations.worker
```

```sh
cd backend
source .venv/bin/activate
python -m app.monitoring.worker
```

Frontend: `cd frontend && npm ci && npm run dev`. Use `/integrations`, Connect,
complete consent, return/refresh, then Sync inbox or Select calendar. The account
shows credential authorization separately from durable sync status and last success.
Sync now queues work; it does not claim immediate completion. Use the expectation
page's Sources used panel to bind the exact source and topic/thread/order/event.

Provider migration `9b635da2e034` adds four backend-owned tables after `8a524c91df23`. The later automatic tracking head is `ac746eb3f145`; see its migration/rollback runbook.
The provider migration retains core table contracts; the later migration permits evaluation-free warning notifications. Use Alembic, never manual CREATE TABLE.
For a disposable validation DB, downgrade to `8a524c91df23`, upgrade head and compare
metadata. Downgrade removes only these synchronization tables; it does not erase
existing expectation/evidence/evaluation history. Take a database backup and stop
provider workers before any production rollback. No production migration was applied.

## Matching and supported facts

Email is read from a bounded recent mailbox window (default 30 days); Outlook is
inbox-only. Gmail excludes sent/drafts/spam/trash. Exact sender plus subject substring,
thread, or order ID is required. Reply bindings also require a thread. Sender names
are not cryptographic authentication: provenance says `sender_authenticated=false`.

Only one unique, explicitly labeled `Total: $...`, `Amount due: $...` or invoice total
becomes `total_cost` USD. Multiple totals/currencies, unlabeled prices and unsupported
formats abstain. A relevant matching message can establish `reply_received=true`.
Cancellation/rescheduling/confirmation/delay/deadline labels are bounded extracted
reports; ambiguous, negated, conditional, policy-only or future statuses do not establish truth. Attachment metadata is available;
attachment bytes, PDF/OCR, arbitrary body interpretation and sending replies are absent.

Calendar selection is checked against the authorized calendar list. Pulls begin with
30 days past/180 days future, expand recurring instances, retain series/instance and
original start identity, then use opaque incremental tokens where supported. Microsoft default-calendar delta uses
the documented v1.0 `/me/calendarView/delta`; other selected Microsoft calendars use
paginated v1.0 calendarView reconciliation. Per-calendar delta is documented in beta,
which this production adapter does not enable. See [Graph event delta](https://learn.microsoft.com/en-us/graph/api/event-delta?view=graph-rest-1.0). The future window is
rotated as its end approaches. Gmail expired history IDs and Google expired sync
tokens/Graph expired delta cursors trigger full reconciliation. Removed entries are
unavailable, not falsely cancelled. Explicit `status=cancelled`/`isCancelled=true` is
cancellation. UTC comparisons handle aware instants; ambiguous/nonexistent local DST
wall times abstain, all-day dates are not silently converted to clock times.

Binding metrics supported without inventing evaluator semantics:

| Binding | Metric | Meaning |
| --- | --- | --- |
| bill | total_cost | Explicit reported USD total |
| reply | reply_received | Message from exact sender and conversation |
| commitment | commitment_confirmed / commitment_cancelled | Explicit status report; ambiguity is unknown |
| calendar | event_scheduled / event_cancelled | Current selected event status |
| calendar | event_unchanged | Exact expected_start comparison; requires aware timestamp |
| order | delivery_reported | Email explicitly reports delivery; absence isn't false |
| order | order_update | Structured order facts; existing evaluator may return UNKNOWN |

The expectation must have compatible existing type/metric. Source binding opts its
provider source name into `evidence_sources`. It does not create a new expectation,
change its baseline/type, or fabricate evaluation. Calendar “Did it move/cancel?”
facts are inspectable through the event/evidence API and existing deterministic
boolean expectations; no new broad voice routing was added.

## Amazon: permitted evidence, not a fake account connector

[Amazon SP-API onboarding](https://developer-docs.amazon.com/sp-api/docs/onboarding-overview)
describes authorized selling partners; it is not evidence of unrestricted consumer
purchase-history access. No official consumer order grant is configured or verified
for CountOn. No private Amazon API, scraping, password collection or CAPTCHA bypass
was added. Carrier APIs remain unavailable until an authorized carrier configuration
exists; no carrier status is fabricated.

Authorized email parses exact `123-1234567-1234567` order IDs, merchant sender,
explicit ISO expected/revised dates, unambiguous shipping/delivery reports and labeled
tracking identifiers. `report_basis=email_reported` is always retained. Missing or
ambiguous values stay absent. Natural-language date estimates are not guessed.

User-entered order facts use the existing authenticated evidence endpoint, e.g. an
owned expectation with `metric=order_update`:

```json
{
  "source": "user_entered_order",
  "metric": "order_update",
  "value": {"order_id":"123-1234567-1234567", "expected_delivery_date":"2026-10-17"},
  "observed_at": "2026-10-11T12:00:00Z",
  "confidence": 0.7,
  "raw_data": {"provenance":"user_entered", "report_basis":"self_reported"}
}
```

POST to `/api/v1/expectations/{owned_id}/evidence` with the current Supabase bearer.
This is a reported fact, not independent carrier verification.

## Disconnect and retention

Disconnect fences workers and clears encrypted tokens, pending OAuth state, watches,
checkpoints, cached source events and bindings. Existing saved expectation evidence
is retained for audit; authenticated API `erase_evidence=true` removes only evidence
with this owned connection ID. Normal expectation deletion remains the way to remove
its history. Cache retention is controlled by `PROVIDER_RETENTION_DAYS`; mail source
receipt time is independently filtered, so a later pull cannot freshen old email.

The backend attempts to stop its watches/subscriptions. Google refresh-token revocation
is attempted through the official endpoint and its success is reported separately.
Microsoft delegated grant removal requires provider account permissions/My Apps;
no least-privilege per-grant revoke endpoint is assumed, and CountOn never invokes a
broader revoke-all-sessions action. Revocation failure never restores local access.

## Read-only live acceptance (not yet executed)

For EACH of Gmail, Outlook, Google Calendar and Microsoft Calendar:

1. Use an authorized dedicated test account with existing test messages/events.
2. Supabase-login to CountOn; Connect and consent the exact read-only scopes.
3. Return/refresh; confirm `credential_state=configured`. Select and sync a source.
4. Start provider worker. Verify last successful sync and only that user's source events.
5. Bind a compatible owned expectation to an exact sender/thread/order/calendar instance.
6. Verify normalized evidence includes account, event ID, source/effective/observation
   times and provenance. Run existing monitoring and inspect actual evaluation/inbox.
7. Re-sync twice; verify unchanged sources don't duplicate evidence/notifications.
8. Observe an independently authorized provider update, then verify incremental cursor
   movement, cancellation/rescheduling or delivery date facts. Do not modify messages
   or events merely to run this procedure without explicit authorization.
9. Exercise missed push recovery through polling; refresh expiry/revocation and reconnect.
10. Log in as a different CountOn user; deny source/event/binding access.
11. Disconnect; prove cached events/tokens/bindings are gone and future pushes have no authority.
12. Record account type, granted scopes, UTC time and PASS/FAIL codes only. Never record
   authorization codes, access/refresh tokens, email bodies or private account content.

Live status: all four account workflows **BLOCKED: provider credentials/consent absent**.
No mocked result is labeled live. Production also needs this migration and API/provider
worker/frontend rollout plus existing readiness/deployment blockers addressed.

## Automated validation

Tests use official-response fixtures for external HTTP and disposable **local**
PostgreSQL for OAuth state/credentials, leasing, concurrency, evidence and notification
persistence. Tests never require Google, Microsoft or AWS credentials.

```sh
# backend; TEST_DATABASE_URL must name a separate loopback database ending _test
pytest -q --tb=short
ruff check app db/scripts tests alembic ../scripts
mypy app --ignore-missing-imports
# frontend
npm run test
npm run lint
npm run typecheck
npm run build
# root
git diff --check
```

Provider foundation command record (2026-10-11). The subsequent monitoring/delivery
pass and current validation results are in [automatic tracking](automatic-tracking.md).

| Executed check | Result |
| --- | --- |
| `.venv/bin/python /tmp/counton_test_suite.py -q --tb=short` (backend) | PASS: 1,099 tests; no skipped backend tests; 104 upstream ASK deprecation warnings |
| `.venv/bin/ruff check app db/scripts tests alembic ../scripts` | PASS |
| `.venv/bin/mypy app --ignore-missing-imports` | PASS: 134 files |
| Configured strict mypy AI/agent/Alexa/MCP subset from CI | PASS: 37 files |
| `.venv/bin/bandit -q -r app -ll` | PASS |
| `npm run lint` | PASS |
| `npm run typecheck` | PASS |
| `npm run test` | PASS: 132 tests; one pre-existing credential-gated live MCP test skipped |
| `npm run build` | PASS |
| `python3 scripts/secret_scan.py` | PASS: history and source, zero findings; Docker permission required |
| `git diff --check` | PASS |
| `.venv/bin/python -m app.integrations.worker --help` | PASS: CLI imports and argument parsing |
| `.venv/bin/python db/scripts/production_smoke.py` with private loopback TEST_DATABASE_URL | PASS: API startup/six MCP contracts, Streamable HTTP/ownership, signed Alexa dialogue, durable conversations/monitoring |
| Provider migration downgrade to 8a and upgrade head, metadata equality and RLS | PASS: automated disposable PostgreSQL test |
| Real Gmail/Outlook/calendar account-to-evidence workflow | BLOCKED: provider credentials, callbacks, encryption key and authorized test consent absent |

The temporary backend test wrapper privately selects `counton_test` from the local
DB configuration and runs standard pytest. Reproduce with a securely configured,
separate loopback `TEST_DATABASE_URL` and `pytest -q --tb=short`; never run these
migrations against production. The offline smoke initially reported missing test DB
environment, then passed all four groups with that private test configuration.
The scanner initially could not reach Docker in the filesystem sandbox; the approved
isolated Docker run completed with no findings. No cloud/device success is claimed.

55 provider tests cover conservative extraction, malformed/untrusted inputs, official
OAuth callbacks, PKCE/state replay/expiry, encrypted refresh and invalid_grant,
owned scopes/bindings, cursor expiry and large history batches, rates/backoff,
concurrent workers/lease recovery, disconnect fencing and legacy cleanup,
calendar cancellation/recurrence/DST, default identity changes and non-default Graph
reconciliation, push signatures/secrets/validation/renewal, order estimates, migration
rollback/RLS and real evidence-to-evaluation notification deduplication. Nine new
frontend tests cover real request shapes, source opt-in, consent URL safety, disabled
configuration, account health, calendar selection, disconnect confirmation and missing
legacy Outlook permissions. Existing regression tests remain enabled.

## Exact change inventory

No files were removed. No commits, pushes, production deployments or production
migrations were performed. Existing migrations, Bedrock/clarification, deterministic
evaluator and MCP tool implementation were preserved.

Added files:


- `backend/alembic/versions/9b635da2e034_provider_synchronization.py`
- `backend/app/api/v1/provider_sync.py`
- `backend/app/db/models/provider_sync.py`
- `backend/app/integrations/accounts.py`
- `backend/app/integrations/adapters.py`
- `backend/app/integrations/normalization.py`
- `backend/app/integrations/watches.py`
- `backend/app/integrations/worker.py`
- `backend/app/schemas/provider_sync.py`
- `backend/app/services/provider_sync_service.py`
- `backend/providers.env.sample`
- `backend/tests/test_provider_sync.py`
- `docs/integrations-acceptance.md`
- `frontend/components/provider-account.tsx`
- `frontend/components/source-binding.tsx`
- `frontend/lib/providers.ts`
- `frontend/tests/providers.test.tsx`

Modified files:

- `README.md`
- `backend/app/api/v1/provider_oauth.py`
- `backend/app/api/v1/router.py`
- `backend/app/core/config.py`
- `backend/app/db/models/__init__.py`
- `backend/app/integrations/microsoft.py`
- `backend/app/integrations/provider.py`
- `backend/app/services/integration_service.py`
- `backend/tests/test_deployment_readiness.py`
- `docs/monitoring.md`
- `docs/production-readiness.md`
- `frontend/README.md`
- `frontend/app/(workspace)/expectations/[id]/page.tsx`
- `frontend/app/(workspace)/integrations/page.tsx`
- `frontend/components/integration.tsx`
- `frontend/tests/screens.test.tsx`
