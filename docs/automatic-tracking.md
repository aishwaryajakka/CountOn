# Automatic tracking and notification acceptance

Local implementation; real provider accounts and email delivery have **not** been verified.
This extends existing services, SQLAlchemy persistence, fenced workers, Supabase JWT
ownership and the in-app inbox. It does not change MCP tools, Bedrock routing or the
manual evaluator's contracts. AI interprets/explains; deterministic code decides results.

## Audit and architecture

Reused: expectation/evidence/evaluation history, one monitoring job per expectation,
SKIP LOCKED leases, run identity, retries/dead letters, atomic evaluation/inbox writes,
OAuth PKCE, encrypted refreshed credentials, read-only provider adapters, authenticated
push verification, durable paginated cursors, subscriptions and explicit source bindings.
The existing dashboard already showed evidence and evaluation history and acknowledged
notifications. Provider integration setup is in [the provider runbook](integrations-acceptance.md).

Gaps fixed in this pass: account sync did not wake monitoring; successful one-shot jobs
could miss later changes; polling could move bound-source evidence windows incorrectly;
source revocation could leave an old MATCH looking current; deadline absence had no
coverage proof; notifications could repeat for every changed observation in one mismatch
episode; email, quiet-hour preferences and tracking controls were absent.

```text
verified provider push (wake hint only) / periodic reconciliation
  -> durable provider_sync_states due time + wake marker
  -> official authorized fetch, pagination, encrypted checkpoint/projection
  -> explicit owner/account/source binding and rule
  -> normalized evidence + fenced monitoring job wake (one transaction)
  -> existing monitoring worker
  -> deterministic result + evidence UUIDs + expectation status
  -> atomic evaluation history and deduplicated in-app notification
  -> optional durable email outbox -> idempotent email API
  -> authenticated dashboard/inbox polls or refreshes
```

A crash after sync commit leaves the job due; a crash before evaluation commit rolls
back the evaluation and notification together. Fencing invalidates obsolete claims.
Publication is bounded to 1,000 bindings / 10,000 cached source facts per stream; an over-budget stream fails closed for operator attention. No provider webhook body becomes evidence and no user-provided URL is fetched. Pushes
received during multi-page sync retain a durable marker and force another round. Polling
still recovers lost pushes. Eight abandoned/failed sync attempts dead-letter the source.

## Matching, deadlines and certainty

Source selection is explicit, not AI-guessed. The connected account/owner, exact calendar
instance ID, sender and thread/order/message reference are checked. Optional recipient/message matching and IANA source timezone selection are supported by the API/UI. Date-only shipping estimates use that explicit timezone (default UTC).
The typed [source planner](orchestration.md) checks usable local read grants and previews authorized references, then
requires explicit confirmation before binding/scheduling. Up to four sources may
share an exact order ID or calendar UID/occurrence. Current calendar records are
authoritative over older email references; current contradictions or unavailable
sources stay UNKNOWN. Conflicting arrival timestamps or different current rescheduled
starts stay UNKNOWN even if both records independently fail the condition. Google
`originalStartTime` and Graph UTC `originalStart` identify recurring occurrences;
calendar titles do not. Unrelated bindings still return `UNKNOWN/ambiguous_sources`.
The evidence value/unit/timestamp must also agree with the current backend-only source projection; caller-supplied provenance cannot replace that grounding. Missing,
conflicting, future, malformed, stale or unavailable evidence stays UNKNOWN.

The existing boolean contract asserts True. Use these concrete conditions:

| Intent | Criteria / binding | Meaning |
| --- | --- | --- |
| Reply by Friday | boolean/temporal `reply_received`, absolute deadline; reply rule with exact sender/thread | First actual reply time is authoritative. Later replies cannot undo an on-time reply. |
| Appointment must remain scheduled | boolean `event_not_cancelled` or `event_scheduled`; exact event | Explicit cancellation produces False/MISMATCH; tombstones alone are UNKNOWN. |
| Meeting must not change | boolean `event_unchanged`; exact instance and aware `expected_start` | Compare actual current start; preserve recurring instance/series provenance. |
| Bill must not exceed $150 | numeric `total_cost`, `less_than_or_equal`, target 150, materiality 0 for a strict threshold; bill rule | Only a unique labeled USD total supports evaluation. |
| Package before 5 PM | `delivery_reported` with absolute deadline; order rule | Deadline evaluation requires an explicit offset-aware delivery timestamp in the report, not email receipt time. |

Reply absence is synthesized **only** after a completed authorized sync covers creation
through the deadline, within retained continuous source coverage. A first snapshot cannot retrospectively prove absence before its cursor anchor: connect/synchronize the mailbox before capturing a reply expectation. If initial sync starts later or a cursor expires, a missing or late-only reply stays UNKNOWN because earlier deleted replies cannot be ruled out. Full pagination proves coverage
through the first pull, not its last page. A post-deadline incremental round is required
if the full round started earlier. Incomplete sync, unavailable/deleted candidate messages
or unidentified tombstones cannot establish absence. Late sync discovery of an on-time reply supersedes an earlier absence assessment; obsolete provider versions do not compete with the current source version. The internal coverage attestation is
keyed and bound to the exact rule/generation/deadline; caller assertions cannot replace it.
It is rechecked against current connection health and coverage when evaluated.

Gmail covers retained received messages outside sent/draft/spam/trash; Outlook covers the
selected Inbox. A reply moved/deleted before an initial scan cannot be proved absent from
all folders. The claim/source must explicitly concern this observed mailbox scope; do not
promise universal email delivery/read receipts. Arbitrary missing external events, including
package delivery, never become a confirmed mismatch solely because a deadline passed.

A shipping email that revises an estimate beyond the deadline creates
`potential_delivery_delay` with `certainty: predicted`, while actual delivery remains
UNKNOWN. The evidence is an email report, not carrier-independent confirmation. Supported
receipt text requires explicit ISO dates; no Friday-to-Monday dates or percentages are
hardcoded in production.

All deadlines/expected starts use offset-aware instants (existing compiler timezone/DST
reasoning is retained). Quiet hours use IANA zones and actual UTC instants across DST
folds/gaps. Fixed recurring polling supports continuous calendar instance checks, not
RRULE expansion into new expectations or automatic per-period deadlines. Unbound recurring
numeric/boolean jobs retain their existing advancing window policy. Bound sources keep
one condition window and continue after MATCH until paused/cancelled/resolved. A fresh
complete calendar delta/reconciliation can revalidate an unchanged cached fact without
creating duplicate evidence. Stale sync cannot. Old bill/reply timestamps are not refreshed.

## Notifications and dashboard

- One mismatch alert per contradiction episode. Further mismatches and intervening
  UNKNOWNs do not repeat it; a deterministic MATCH ends the episode and closes outstanding mismatch alerts without fabricating user acknowledgement. Closed alerts remain in history. Manual evaluation
  keeps its existing per-evaluation semantics. Evidence UUIDs/reason/evaluation ID support
  provenance; no arbitrary provider prose is inserted into notification speech.
- Connection/staleness warnings are deduplicated by source/last success. Upcoming deadline
  reminders (within 24 hours, still UNKNOWN) require explicit preference opt-in.
- `GET/PUT /api/v1/notification-preferences`: owned mismatch/connection/deadline/email
  toggles and quiet hours. No recipient, token or user_id payload is accepted. Email
  targets only the confirmed Supabase identity fetched server-side with its current token.
- `GET /api/v1/notification-preferences/delivery-history`: owned safe delivery status,
  attempt/error code and timestamps. No encrypted payload or recipient returned.
- The existing inbox supports unread/read/dismissed history and acknowledgement time.
  Warning notifications have `evaluation_id: null` and keep any triggering evaluation ID
  in metadata, so source and deadline warnings can coexist. Mismatch rows retain real FKs.
- Expectations filter by status/provider; details show schedule health, latest result,
  evidence and history. Conditions/deadlines can be edited, tracking paused/resumed/cancelled,
  sources selected and accounts reconnected. Visible dashboard/details/inbox views refresh
  every 30 seconds and on focus. No WebSocket/Supabase browser writes were introduced.

In-app persistence is delivery and remains visible during quiet hours. Email is disabled by
default and requires an explicit user opt-in plus operator configuration. Enabling email does
not email earlier inbox history. Acknowledging/cancelling before dispatch suppresses pending
email. Opt-out prevents new dispatches; an already in-flight network send cannot be recalled.
The channel interface allows future implementations without claiming Alexa proactive support.

## Setup and operation

Use the same trusted backend settings/DB for all three processes. Provider configuration is
in `backend/providers.env.sample`; optional email options in
`backend/notifications.env.sample`. Keep credentials in ignored `.env.local` or runtime secret
storage. Apply migration `ac746eb3f145` after `9b635da2e034` with Alembic. It adds coverage/wake
fields, two backend-only RLS tables, a notification owner key and nullable warning evaluation
references; no core expectation schema/enum/tool was replaced.

```sh
# Terminal 1, from backend (start docker compose from root first if needed)
source .venv/bin/activate
python -m pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload

# Terminal 2, backend; configure PROVIDER_SYNC_ENABLED=true plus real OAuth settings
source .venv/bin/activate
python -m app.integrations.worker

# Terminal 3, backend; configure MONITORING_ENABLED=true
source .venv/bin/activate
python -m app.monitoring.worker

# Optional terminal/service 4, after configuring and opting into email
source .venv/bin/activate
python -m app.notifications.worker
```

Each worker supports `--once`; idle exit is not proof of successful processing. Inspect owned
sync/monitoring rows and delivery history. Supervise processes with restart policies, use
synchronized clocks, and alert on dead letters, overdue pending jobs, stale `last_success_at`,
auth_required sources and failed deliveries. Workers can scale horizontally against PostgreSQL.
There are no new infrastructure/dependency packages.

Email uses the fixed Resend `/emails` HTTPS API with a sending-only key and verified-domain
sender. Configure backend-only `NOTIFICATION_EMAIL_ENABLED=true`,
`NOTIFICATION_EMAIL_API_KEY`, `NOTIFICATION_EMAIL_FROM`, `FRONTEND_PUBLIC_URL` (HTTPS origin)
and the existing 32-byte `INTEGRATION_TOKEN_ENCRYPTION_KEY`. The recipient/frozen payload is
AES-GCM encrypted with identity-specific AAD. Email contains safe notification text and a
tracked-expectation link, not private claims/raw evidence/tokens. Requests are bounded to
10 seconds and 64 KiB. Retries use an identical payload and key. Resend retains
[idempotency keys for 24 hours](https://resend.com/docs/dashboard/emails/idempotency-keys);
CountOn stops recovery after 23 hours or eight attempts and records a dead letter. An ambiguous
expired-window delivery must be inspected against provider records, never blindly requeued
with a new key. API acceptance is `sent`, not a claim of inbox receipt; bounce/delivery webhook
tracking is not implemented.

Recovery: source transient failures back off and polling resumes; reconnect clears coverage
and forces full reconciliation. Requeue owned dead-letter sources with the existing `/run`
endpoint; requeue monitoring with a complete authenticated schedule PUT. Do not override live
lease tokens by hand. Changing binding/conditions fences old work. Disconnect removes credentials
and cached account authority; retained historical evidence cannot prove current health.

Backup before rollback. `alembic downgrade 9b635da2e034` removes new preferences/delivery state
and coverage. It deliberately refuses if any evaluation-free warning rows exist; explicitly
export/archive those rows before a planned rollback. No automatic deletion occurs. A full rollback
of provider sync further removes cursors/bindings/credentials support as documented in its runbook.
No production migration/deployment was performed in this pass.

## Automated and live acceptance

`backend/tests/test_automatic_tracking.py` uses real isolated PostgreSQL, existing services,
workers and HTTP webhook routes with mock official-provider/email responses. It covers:

| Scenario | Local verification | Real account/device status |
| --- | --- | --- |
| A Gmail reply absent after covered deadline | MISMATCH, evidence attestation, one inbox alert | NOT RUN |
| B Outlook appointment rescheduled | Verified Graph callback → sync → exact instance → MISMATCH | NOT RUN |
| C Amazon email Friday estimate changes to Monday | ISO-date report → predicted warning, actual outcome UNKNOWN | NOT RUN |
| D Calendar cancellation | Explicit provider cancellation → MISMATCH with evidence | NOT RUN |
| E Repeated webhook | Idempotent evidence, one mismatch alert | NOT RUN |
| F OAuth expiry | UNKNOWN/impaired monitoring + connection warning | NOT RUN |
| G Crash/restart | Atomic evaluation/inbox rollback; lease recovery; email accepts one key | NOT RUN |

Additional regressions cover incomplete/multi-page coverage, stale sources, deleted replies,
late/on-time first replies, ambiguous accounts, forged absence proofs, pause preservation,
calendar revalidation, delivery occurrence timestamps, channel failure privacy, quiet-hour DST,
owned opt-in/acknowledgement, email crash/concurrency/dead letters and guarded migration rollback.
The pre-existing provider suite verifies real protocol parsing/signatures/refresh/ownership.
Mocks do not establish real mailbox scope, production OAuth, Pub/Sub or Graph delivery.

Validation on October 12, 2026, on `feature/alexa-mcp`:

| Check | Actual result |
| --- | --- |
| Full backend `pytest -q --tb=short` | 1,150 passed; 104 upstream Alexa SDK deprecation warnings |
| Frontend `npm run test` | 140 passed; one pre-existing credential-gated live MCP test skipped |
| Frontend `npm run lint`, `npm run typecheck`, `npm run build` | Passed |
| Ruff, app-wide mypy, configured strict intelligence/MCP mypy | Passed (140 / 37 source files for mypy) |
| Bandit medium/high severity, `pip check` | Passed |
| Gitleaks source and history scans | Passed, zero findings |
| `git diff --check` | Passed |
| Offline production smoke | All four groups passed: API/six MCP contracts, Streamable HTTP ownership, signed Alexa dialogue, durable conversations/monitoring |
| Provider, monitoring and email worker `--help` | Passed import and CLI startup checks |

The backend suite ran through a private local wrapper supplying an isolated loopback
`TEST_DATABASE_URL`; no production database was used. All A–G assertions ran in that
suite. Locally, Google/MS OAuth configuration, integration token encryption, provider
sync, monitoring and email delivery are disabled/unconfigured. These checks establish
local code behavior, not production provider acceptance. No credentials were added and
no deployment or production migration was performed.

With `TEST_DATABASE_URL` set privately to an isolated loopback `*_test` database:

```sh
cd backend
.venv/bin/python -m pytest -q --tb=short
.venv/bin/ruff check app db/scripts tests alembic ../scripts
.venv/bin/mypy app --ignore-missing-imports
.venv/bin/bandit -q -r app -ll
# Frontend, from its directory
npm run test
npm run lint
npm run typecheck
npm run build
# Root
git diff --check
```

Live checklist: configure scoped Google/MS consent and push authorities; connect a dedicated
test account; bind exact identifiers to tagged test expectations; run both workers; send real
reply/cancellation/rescheduling/order-report events while signed out; verify owned API results,
evidence and one inbox alert after process restart/repeated push. Test Inbox scope, moved/deleted
mail and cursor loss explicitly before promising absence detection. Opt into email with a
verified Supabase test address and configured verified sender; confirm provider acceptance AND
recipient receipt. Repeat DST/deadline, expired-token, cross-user and reconnect tests. Clean up
only tagged expectations/accounts. Record actual provider/device results separately.

Remaining limits: real Google/Microsoft/Resend credentials and deployment are still required;
provider semantics/delivery must be accepted live. Arbitrary-language receipt extraction,
carrier consumer APIs, calendar-series rule generation, aggregate sums, universal email absence,
email bounce webhooks and Alexa proactive voice delivery are not claimed.

The latest resumed-orchestration validation and external release gates are recorded
in [orchestration validation](orchestration-validation.md). Earlier counts above describe
the earlier pass; they do not replace the latest validation record.
