# Background monitoring

The automatic multi-provider workflow, coverage-gated reply deadlines, tracking controls
and opt-in notification delivery are documented in [automatic tracking](automatic-tracking.md).
The sections below also describe the preserved legacy Outlook subject-rule connector.

The worker extends CountOn's existing jobs, services, evaluations and inbox. It
does not call Bedrock, change the six MCP tools, or write from the browser to
Supabase. All durable state is PostgreSQL; no Redis/Celery dependency is needed.
This implementation is verified locally with mocked Microsoft responses. Live
Microsoft app registration, mailbox consent and deployment acceptance are separate.

```text
Authenticated API / MCP capture → owned expectation + existing monitoring_jobs
                                                  ↓
                          PostgreSQL due-time queue → worker lease
                                                  ↓
                   existing evidence or delegated Outlook subject-rule connector
                                                  ↓
                     normalized evidence + deterministic monitoring policy
                                                  ↓
                   atomic evaluation/history + status + in-app notification
                                                  ↓
                   existing authenticated dashboard / notifications inbox
```

## Setup

Use the same backend settings, database and trusted DB role for API and workers.
Merge the non-secret [sample](../backend/monitoring.env.sample) into ignored
`backend/.env.local` or your deployment secret configuration. Do not put Microsoft
secrets, encryption keys, refresh tokens or database credentials in Vercel or
`NEXT_PUBLIC_*`. The trusted DB role must own these tables or have the necessary
RLS bypass/service permissions; browser roles cannot access credential/state tables.

Terminal 1, root:

```sh
docker compose up -d
cd backend
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Terminal 2, root, after setting `MONITORING_ENABLED=true` in backend configuration:

```sh
cd backend
source .venv/bin/activate
python -m app.monitoring.worker
```

For one polling attempt: `python -m app.monitoring.worker --once`. An empty queue
is a successful idle poll; inspect the owned job's status/error to determine a
provider operation's outcome. SIGTERM/SIGINT stop polling after the current run.
Use a process supervisor/restart policy in deployment, not Uvicorn reload to run
the worker. The existing backend image supports the same command override:
`python -m app.monitoring.worker`. Supply backend environment privately.

Multiple **worker processes** are safe with the same database. The API's existing
conversation/rate-limit stores remain process-local; its single-worker deployment
limitation is unchanged. Apply all migrations through `ac746eb3f145` before rolling out this code.
Downgrade removes the new monitoring/OAuth state: use only disposable databases
or an explicitly planned rollback with backup. No production migration was run.

## Scheduling and lifecycle

Expectation creation already creates one pending job. Starting an enabled worker
processes eligible existing jobs as well as newly captured expectations. The
default polling interval is one hour, evidence maximum age one day, and retry
budget five. Monitoring is disabled by default until an operator enables workers.
Incomplete compilation/clarification never creates an expectation/job.

Authenticated `GET /api/v1/expectations/{id}/monitoring` inspects the owned schedule.
`PUT` configures/requeues/pauses it; no client `user_id` is accepted:

```json
{
  "next_run_at": "2026-10-12T12:00:00Z",
  "interval_seconds": 3600,
  "recurring": false,
  "max_evidence_age_seconds": 86400,
  "max_attempts": 5,
  "status": "pending"
}
```

Optional `window_start_at` sets the first evidence window; otherwise observation
must be at/after expectation creation. Scheduling changes invalidate in-flight
leases. `status: paused` suspends polling. Requeue a `failed` job with a complete
valid PUT; it resets attempts/run identity, preserving evaluation history.

- `recurring: false`: poll one expectation until MATCH, resolution/cancellation,
  or explicit operator pause (unbound one-shot jobs). Bound provider expectations keep monitoring after MATCH. A meaningful mismatch does not prove the user has
  resolved it, so polling continues without repeating the same notification.
- `recurring: true`: numeric/boolean criteria repeat at fixed intervals; successful
  runs advance evidence windows and due times. Old period evidence cannot satisfy
  a new period. Missed intervals are coalesced, avoiding catch-up storms. This is
  a fixed cadence, not calendar/timezone-aware cron or an aggregate spending sum.
- The evaluator retains authority. Monitoring UNKNOWN resets a nonterminal
  expectation to monitoring; manual legacy evaluation behavior remains unchanged.
- Resolved/cancelled expectations atomically cancel active jobs. In-flight work
  cannot notify after cancellation. Unbound one-shot fulfilled expectations stop; bound provider expectations remain eligible for changes.
- Temporal/event monitoring needs an explicit metric/deadline and real positive
  boolean occurrence evidence. Observation on/before deadline MATCHes, observation
  after deadline MISMATCHes. Missing evidence and negative/ambiguous event claims
  remain UNKNOWN, even after deadline, except a covered, authenticated reply-absence attestation. See the automatic tracking runbook. Recurring temporal deadlines are rejected:
  the current expectation model has only one absolute deadline.

## Leasing, retries and atomicity

Claims use database time and `FOR UPDATE SKIP LOCKED`. Each claim commits a random
fencing token, expiry, and attempt increment before I/O. The default lease is 300
seconds, minimum 120. Provider requests have 3-second connect and 10-second I/O
timeouts; mailbox reads are bounded to five pages of 100 metadata rows. If work
outlasts its lease, results are discarded and a new worker can safely reclaim it.
There is no heartbeat or promise of exactly-once provider reads.

Provider I/O is read-only and outside the evaluation transaction. The final
transaction locks the owned expectation/job, revalidates the lease and connected
account, ingests idempotent evidence, evaluates, inserts the inbox exception,
updates lifecycle/schedule, and commits together. A crash or rollback cannot leave
a committed evaluation without its notification or advance an uncommitted run.
Stable job/run keys prevent retry duplication; evidence IDs derive from connected
account plus immutable Graph message ID. Repeated polling of the same fact yields
history but suppresses the same mismatch notice using an observation/criteria hash.
Continuous monitoring suppresses repeated alerts within one mismatch episode, including across UNKNOWN interruptions; a subsequent MATCH resets it. Manual API evaluation
also supports optional `Idempotency-Key`, returning the original result on replay.

Transient failures retry with `30 * 2^(attempt-1)` seconds, capped at one day;
provider `Retry-After` can lengthen the wait. OAuth/permission failures fail closed
without retries. Exhausted or abandoned attempts become durable `failed` rows.
They retain safe codes/attempts and require explicit requeue. Worker/database
restarts reclaim expired leases; logs never include exception strings, tokens,
email contents, OAuth codes or DB URLs. Provider errors do not become fabricated
facts or successful evaluations. During failures, the latest evaluation remains
historical; inspect `last_run_at`/job error before interpreting it as current.

## Deterministic evidence policy

Monitor only the exact metric, approved sources and observation window. Bound
Outlook jobs also filter stored facts by connection and current mailbox account;
permission/account changes during a read invalidate its commit. Latest
`observed_at` wins, independent of arrival time. Equal-time peers must agree on
normalized value/unit; conflicting, malformed, low-quality, future, stale, missing
or oversized peer sets are UNKNOWN and silent. Different observation times are
successive observations, not automatically a conflict. Numeric materiality and
boolean semantics reuse the existing evaluators. A numeric/boolean observation
after an explicit deadline cannot fulfil the claim and is UNKNOWN; deadlines
are not silently advanced when recurring windows change. Evaluation reasoning retains
evidence UUIDs, checked time, window and age policy. AI never chooses a verdict.

The initial connector does not aggregate transactions, infer facts from arbitrary
mail, or prove absence from an empty mailbox. Unsupported receipt formats remain
unknown. Existing user-submitted evidence remains usable without an external
connection; workers apply freshness/window/source checks to it.

## Microsoft setup and consent

1. Register an Entra **Web/confidential** app for the intended account types.
2. Register the exact callback URI:
   `https://YOUR_API_HOST/api/v1/integrations/oauth/microsoft/callback`.
   Development permits loopback HTTP; production requires HTTPS.
3. Configure backend-only `MICROSOFT_GRAPH_ENABLED=true`, `MICROSOFT_CLIENT_ID`,
   `MICROSOFT_CLIENT_SECRET`, `MICROSOFT_TENANT_ID` (common/organizations/consumers
   or tenant UUID), `MICROSOFT_REDIRECT_URI`, and
   `INTEGRATION_TOKEN_ENCRYPTION_KEY` (URL-safe base64 of 32 random bytes).
4. Generate/store the encryption key securely once, shared by API and workers.
   Never print it in logs or overwrite an existing key casually. Rotation currently
   requires planned re-encryption or reconsent; replacing it makes old credentials
   safely unavailable. Separate DB and key backups/access policies.
5. With the current Supabase bearer, create an existing Microsoft email connection:
   `POST /api/v1/integrations` with `{"provider":"microsoft","connection_type":"email"}`.
6. POST `/api/v1/integrations/{id}/oauth/microsoft/authorize`; open the returned
   authorization URL and consent the intended test mailbox. Do not log/share it.
7. Microsoft form-posts the code/state to the backend callback. It uses one-time,
   ten-minute, user/account-bound server state and PKCE S256. No bearer is required
   on this callback: identity comes from the authenticated initiation's stored
   state, never callback-supplied user IDs. Only a simple confirmation is returned.
   Form-post keeps codes out of access-log query strings.
8. The authenticated `/oauth/microsoft/complete` endpoint also accepts `{state,code}`
   for a trusted custom callback client. Do not supply `user_id`, tokens or secrets.
9. Confirm the existing integration API reports connected/configured. Disconnect
   through POST `/integrations/{id}/oauth/microsoft/disconnect`; local encrypted
   tokens and pending state are removed. Remove consent at Microsoft as well if
   external revocation is desired. Generic pending/disconnected updates also remove
   local credentials; deleting a connection cascades its bound jobs/credentials.

Only delegated `offline_access User.Read Mail.ReadBasic` is requested. No application
permissions, shared-mailbox impersonation, sending, deleting, bodies or attachments.
The account is verified through `/me`, and refresh is serialized with DB locks;
rotated refresh tokens are encrypted and committed before mailbox reads. Invalid
grants require reconsent; transient refresh failures preserve encrypted credentials.
Redirects/foreign pagination hosts and truncated/invalid responses fail closed.
Credential/state tables have RLS and no browser-role access. No live Microsoft
credentials were used during the local test pass.

References: [authorization code and PKCE](https://learn.microsoft.com/en-us/entra/identity-platform/v2-oauth2-auth-code-flow),
[least-privilege message metadata](https://learn.microsoft.com/en-us/graph/api/user-list-messages?view=graph-rest-1.0),
[throttling and Retry-After](https://learn.microsoft.com/en-us/graph/throttling).

## Bind an Outlook receipt rule

Create a numeric expectation with `evidence_sources: ["outlook_email"]`, a metric
(for example total_cost), and real user-provided comparison/target/baseline. PUT its
schedule with the connection ID plus:

```json
{
  "next_run_at": "2026-10-12T12:00:00Z",
  "interval_seconds": 3600,
  "connection_id": "CONNECTED_ACCOUNT_UUID",
  "outlook_rule": {
    "sender": "billing@example.com",
    "subject_prefix": "Electricity bill total",
    "currency": "USD"
  }
}
```

Both sender and from must match the explicit address. Only a whole subject such
as `Electricity bill total: USD 162.00` normalizes into `{amount: 162}`. Arbitrary
mail/body instructions are ignored. Source time is **receipt time**, not inferred
billing-period time. Provenance retains account/connection, hashed immutable event
ID, parser, delegated permission and source time; no raw subject/body is stored.
This is an intentionally narrow metadata-total parser, not universal utility
invoice extraction. Sender address matching is not cryptographic sender
authentication: provenance explicitly records `sender_authenticated: false`.
Choose approved senders/rules accordingly; DKIM verification and provider-specific
invoice-period parsing require additional work before stronger trust claims.

## Inbox and verification

The existing `/api/v1/notifications` inbox is the delivery channel. MATCH/UNKNOWN
are silent. New observation-backed MISMATCH creates an unread `pending` row.
PATCH read/dismissed acknowledges it with a stable timestamp; permissions remain
owner-scoped. `NotificationChannel`/`InAppChannel` provide the extension seam.
An optional encrypted delivery outbox and worker already support Resend/SMTP;
see [automatic tracking](automatic-tracking.md) for confirmation, retries and delivery
limits. Actual recipient delivery requires live verification. Alexa proactive
notification permission and Echo delivery are not implemented.

From backend, with private dedicated loopback `TEST_DATABASE_URL` ending `_test`:

```sh
python -m pytest -q tests/test_monitoring.py tests/test_microsoft_provider.py
python -m pytest -q
ruff check app db/scripts tests alembic
mypy app --ignore-missing-imports
```

Concurrency tests create/drop only uniquely named test databases (CREATEDB needed).
Coverage includes schedules, six simultaneous workers, SKIP LOCKED, lease expiry,
crash/replay fencing, atomic rollback, backoff/dead letters, source/freshness/conflict
checks, recurring windows, temporal occurrences, cancellation, ownership, PKCE,
state expiry/replay, encrypted token binding, concurrent refresh, revocation,
callback exchange, hostile pagination, partial responses and Graph → worker →
evaluation → inbox deduplication. Provider responses are mocked; PostgreSQL is real.

Live acceptance: consent a dedicated test mailbox; configure a test expectation
and owned rule/window; send an authorized sender's matching receipt; start a worker;
verify the owned API evidence/evaluation/provenance and inbox; poll again for no
duplicate; acknowledge; exercise refresh/revocation; clean only exact test IDs.
Verify Supabase RLS and deployment roles, callback HTTPS, clock/lease budgets,
secret rotation procedures and process supervision. Automated tests do not prove
live mailbox access, sender authenticity, Alexa/Echo delivery or cloud deployment.


## Local verification record — 2026-10-11

- `python -m pytest -q --tb=short`: **972 passed** against dedicated local PostgreSQL,
  including disposable concurrency databases and Alembic upgrade/downgrade cycles.
  There are 104 upstream Alexa SDK datetime/certificate deprecation warnings.
- `ruff check app db/scripts tests alembic`: passed.
- `mypy app --ignore-missing-imports`: passed, 119 source files. The existing strict
  AI/agent/Alexa scope also passed, 37 files.
- `npm run test`: 112 passed, one opt-in live test skipped; `npm run lint`,
  `npm run typecheck`, and `npm run build` passed.
- Alembic metadata comparison on the dedicated test database: no drift.
- `python -m app.monitoring.worker --once`: passed as an idle test-database poll
  with the process-only monitoring flag enabled; does not establish live ingestion.
- `git diff --check`: passed.

An Alexa regression fixture's audit sink was also isolated to the actual test
transaction: audit persistence remains real and asserted, without opening the
application-configured database. Microsoft app ID/secret/callback/encryption key
are not configured locally, so no live consent or Graph request was attempted.
The worker is disabled by default. No production migration, deployment, commit
or push was performed.

## Shared account sync

The legacy Mail.ReadBasic subject-rule path above remains compatible. New Gmail,
Outlook Mail.Read and calendar account synchronization runs in a separate durable
provider worker and publishes through explicit owned source bindings into the same
Evidence service. See [provider setup and acceptance](integrations-acceptance.md).
