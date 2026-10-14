# CountOn data minimization and audit policy

## Product boundary

CountOn stores expectations and the smallest evidence needed to evaluate them. It
is not an email archive, calendar archive, shopping-history store, Ring media
store, Bee transcript store, or Alexa recording store. Provider content is
retrieved under a user grant, normalized, correlated to a confirmed expectation
or an explicitly reviewed source recommendation, and discarded unless a minimal
fact is required for monitoring.

The deterministic evaluator remains authoritative for `MATCH`, `UNKNOWN`, and
`MISMATCH`. Bedrock may compile language or explain a recorded mismatch; it does
not create evidence or set an evaluation result.

## Persistence audit

The following inventory reflects the SQLAlchemy models and runtime storage in the
current repository.

| Storage | Purpose | Permitted content | Privacy and retention boundary |
|---|---|---|---|
| `profiles` | CountOn identity | Supabase user ID and application profile fields | Deleted with the CountOn account. Passwords and Supabase sessions are not stored here. |
| `expectations` | User-confirmed monitoring intent | Claim, typed comparison, target/baseline, deadline, status, approved source names | Canonical product record; owner scoped. |
| `evidence` | Normalized observation | Expectation ID, source, metric, small typed `value`, confidence, observation time, safe record/idempotency reference, provenance | No provider body, transcript, attachment, media, credentials, or provider JSON. Retained with the expectation so historical evaluations remain explainable; erased with the expectation/account. |
| `evaluations` | Deterministic result history | Result, expected/observed snapshots, reason codes, evidence IDs, confidence | Never a model-authored verdict. Retained with the expectation. |
| `audit_events` | Minimal user-visible action ledger | Links to expectation/evidence/evaluation, source/provenance, result, action, safe allowlisted metadata | No copied provider content. Provider references are SHA-256 pseudonymous. Retained with the account; linked domain rows may be set null while the minimal action remains. |
| `notifications`, `notification_deliveries`, `notification_preferences` | Delivery and acknowledgement | Evaluation link, bounded message/status, idempotency key, encrypted destination payload where configured | Operational storage, not evidence. No provider source payload. |
| `monitoring_jobs` | Durable scheduling | Lease, due time, retry/error code, source binding reference | Safe error codes only; no exception text or provider payload. |
| `integration_connections` | User grant metadata | Provider/type/status/scopes, safe external-account identifier, sync status | Operational metadata. It does not imply access to unrelated Amazon, Ring, Bee, or Alexa data. |
| `integration_credentials`, `provider_oauth_states`, `provider_watches` | OAuth and push operation | Encrypted tokens/secrets, PKCE state, expiry and revocation metadata | Protected operational storage; never returned as evidence or audit history. Removed on disconnect. |
| `provider_sync_states` | Incremental synchronization | Encrypted checkpoint, coverage interval, lease and safe error code | Removed on disconnect. Checkpoints are not provider content. |
| `provider_source_events` | Short-lived source-selection and verification projection | Encrypted normalized facts plus external ID/version | Contains no message body or attachment. Bounded by `PROVIDER_RETENTION_DAYS` (default 30, allowed 1–90), deleted by each completed sync, and cascade-deleted on disconnect. It is not exposed in Audit History. |
| `expectation_source_bindings` | Explicit source consent | Expectation, sync, and exact deterministic matching rule | Owner constrained and cascade-deleted with the source/expectation. |
| `bee_cli_pairings`, `bee_cli_credentials` | Local bridge authority | Hashed one-use pairing code, hashed revocable bridge credential, checkpoint and expiry | Bee credentials stay local; CountOn stores only digests. Expired pairing rows are pruned on pairing activity. |
| `bee_import_candidates` | Consent preview | Bounded summary, category, one outcome flag and safe external reference | Pending previews expire after seven days on bridge/user activity. After import the summary/fact are cleared, leaving only a replay tombstone. Disconnect deletes candidates. |
| `bee_expectation_bindings` | Bee import consent | Owned connection-to-expectation link | No transcript or audio. |
| `compilation_sessions` | Clarification/replay control | Typed clarification state, digest, expiry, resulting expectation ID | No bearer token. Expiring workflow state, not provider evidence. |
| `conversation_records` | Agent/Alexa continuation | Encrypted bounded state, owner, digest, lease, expiry | No Alexa audio or full ASK envelope. Expiry cleanup is part of the conversation store. |

### Runtime-only storage

- The provider extraction cache is process memory only, holds normalized facts,
  is capped at 256 entries, expires after 15 minutes, and is cleared on process
  exit. Its key hashes the authorization generation, source identity, operation,
  normalizer version, and input. It never stores credentials or model prompts.
- Alexa certificate and replay caches are bounded process-memory security caches.
- Next.js API requests use `cache: 'no-store'`; bearer tokens are forwarded only
  to the trusted backend/MCP route and are not returned.
- Provider and monitoring errors record safe codes. Worker exception handling does
  not log provider bodies. No application path writes provider payloads to a
  temporary file.
- Simulator command-line helpers print only a success label. They no longer print
  generated raw events or normalized evidence.

## Retrieval and processing rules

1. A connection belongs to one authenticated CountOn user. OAuth generation,
   status, scope, credential presence, and ownership are rechecked before a sync,
   source plan, publication, or evaluation.
2. Source enrollment is explicit. Calendar selection is exact; email uses the
   authorized inbox. Provider writes are forbidden.
3. Raw email bodies are held in memory only long enough for deterministic,
   bounded extraction. Attachments are not downloaded and attachment names,
   types, or sizes are not retained.
4. Before writing a new projection, the worker requires a supported active
   expectation metric or an exact active binding. Records with no fact usable by
   those expectations are discarded. A content-free tombstone is retained only
   when it is needed to prevent an incomplete reply sync from becoming false
   proof of absence.
5. The temporary provider projection contains normalized facts used to offer an
   exact source choice and later verify evidence. Source application recomputes
   the plan and requires explicit user confirmation.
6. Published evidence does not duplicate that projection. It stores the typed
   value plus safe IDs/version/provenance. Verification decrypts the current
   backend-only projection when needed.
7. Revocation fences in-flight synchronization, removes credentials, sync state,
   watches, bindings, and encrypted projections. Previously recorded evidence is
   kept by default so completed evaluations remain auditable; the existing
   disconnect option may erase owned evidence explicitly.

## Provider-specific boundaries

### Gmail and Outlook

CountOn transiently parses a bounded message body to extract explicit facts such
as a labeled total, exact order ID/status, calendar UID, or commitment status.
The body and attachment metadata are discarded. Stored provider projections use
safe message references and only the normalized matching fields. Evidence records
contain the final value and true provider provenance (`GMAIL` or `OUTLOOK`).

### Google and Microsoft Calendar

CountOn stores only a selected calendar's normalized event identity, status,
start/end/occurrence information, and update timestamp during the bounded sync
window. It does not store a calendar export, attendees, notes, conferencing data,
or unrelated provider JSON. Evidence retains only the relevant status/time fact.

### Amazon order evidence

The implemented path is an order-related email read through an authorized Gmail
or Outlook connection. Audit source is therefore `GMAIL` or `OUTLOOK`, with source
type `AMAZON_ORDER_EMAIL`; Login with Amazon does not grant purchase-history
access. Order correlation requires an exact extracted order identifier and sender.

### Ring

The current demo source is simulated. Evidence is labeled `SIMULATED_RING` and
retains only the normalized observation and simulation flag. Arbitrary event
fields and video URLs are discarded. No detection is not proof of nondelivery.

### Bee

Simulator evidence is labeled `SIMULATED_BEE`. The optional local CLI stages a
bounded summary for explicit review; CountOn never imports audio or a full
transcript. Only an explicitly completed todo can support an outcome. A recorded
promise remains context and cannot prove fulfillment. Imported CLI evidence is
labeled `LIVE_BEE_CLI`, and staged private text is cleared after import.

### Alexa

CountOn retains the confirmed expectation, bounded encrypted conversation state,
replay digest, and resulting actions. It does not retain audio or a full ASK
request envelope. Alexa account linking grants CountOn access only; it is not
permission to import Alexa history or other Amazon data.

## Evidence write boundary

Every evidence write passes through `evidence_service.add_evidence`. The service
allowlists operational `raw_data` keys and discards unknown fields. This applies
to HTTP submissions, provider workers, Bee imports, and simulators. In particular,
`body`, `attachments`, `transcript`, `audio`, `video`, authorization values,
credentials, raw provider payloads, and arbitrary nested data cannot be stored in
`raw_data` by a new adapter accidentally.

Provider evidence keeps `connection_id`, binding/version IDs, safe source record
reference, timestamps, provenance, and a two-field calendar correlation snapshot
when needed. The provider account ID, granted-scope copy, full facts object, and
source title are not duplicated into evidence.

## User-visible Audit History

The Activity page renders exactly these columns from persisted backend records:

| Expectation | Evidence | Source | Result | Action | Timestamp |
|---|---|---|---|---|---|
| Electricity bill below $142.10 | amount: 162 USD | Gmail · Official API | MISMATCH | Notification created | 2026-10-13 12:00 UTC |
| Package arrives Friday | package detected: true | Ring · Simulated Ring | MATCH | Continued monitoring | 2026-10-13 13:10 UTC |
| Plumber arrives Friday | commitment recorded; outcome unknown | Bee · Simulated Bee | UNKNOWN | Continued monitoring | 2026-10-13 14:00 UTC |

These examples are sanitized illustrations. Actual rows link existing records
instead of copying provider content. The audit repository allowlists metadata,
hashes source references, uses stable idempotency keys, and scopes every query to
the authenticated owner. A `MISMATCH` event and notification action appear only
after the deterministic evaluator and notification service actually persist them.
`MATCH` creates no notification; `UNKNOWN` remains in monitoring.

## Retention and deletion policy

- **Provider projections:** 1–90 days, default 30; pruned after completed sync and
  deleted immediately on local disconnect through cascading sync deletion.
- **Extraction cache:** 15 minutes or process exit, whichever comes first.
- **Bee pending previews:** seven days, pruned during bridge/status/candidate
  activity; immediate deletion on disconnect. Imported preview text is cleared
  immediately after evidence creation.
- **OAuth state/pairing codes:** short lived and single use; obsolete pairing rows
  are pruned during pairing activity. Credentials are deleted/revoked on disconnect.
- **Conversation and compilation state:** bounded by their stored expiry and replay
  lifecycle; never promoted to audit evidence.
- **Evidence, evaluations, notifications, and minimal audit events:** retained with
  the expectation/account to preserve historical correctness and notification
  deduplication. Account/expectation deletion follows database cascades. Provider
  record removal does not rewrite an evaluation that was correct at its recorded
  time.

Operations should run regular expiry cleanup even when an inactive user does not
open the application. That scheduled housekeeping and a formal user-configurable
retention period are deployment controls still to be completed before a long-term
production launch.

## Existing-data remediation plan

No destructive migration or production data change was performed in this pass.
Earlier rows may contain adapter payloads in `evidence.raw_data`, attachment
metadata in encrypted provider projections, or imported Bee preview text. An
operator-approved remediation should:

1. Take and verify an encrypted backup and record row counts by owner/source.
2. Stop provider and monitoring workers and fence active leases.
3. Rewrite `evidence.raw_data` through the current allowlist in owner-bounded
   batches, preserving idempotency, provenance, source version, and correlation
   fields.
4. Clear `summary`/`fact` for imported Bee candidates and delete expired pending
   candidates and expired pairings.
5. Purge existing `provider_source_events` and re-synchronize from current grants,
   rather than attempting to inspect or transform encrypted private projections in
   SQL. This preserves the encryption boundary and applies the current normalizer.
6. Verify evaluation/evidence references, audit counts, notification deduplication,
   cross-user isolation, and rollback from the backup before resuming workers.
7. Produce aggregate counts only; do not log migrated values or decrypted facts.

This plan intentionally requires explicit approval because purging projections or
rewriting existing evidence is destructive. No Alembic schema migration is needed
for the new-write boundary.

## Verification map

The regression suite covers normalized Gmail/Outlook/calendar extraction, exact
source correlation, Amazon order email provenance, Ring/Bee simulation labels,
Bee consent/import/replay/disconnect, evidence minimization, deterministic
`MATCH`/`UNKNOWN`/`MISMATCH`, notification deduplication, audit idempotency and
reload, cross-user denial, worker restart/lease recovery, safe errors, MCP/Alexa
contracts, Bedrock grounding, and frontend rendering/build checks.
