# Audit History contract

CountOn keeps a small, owner-scoped history of actions that affect an expectation. The audit log links to existing expectation, evidence, and evaluation records. It does not copy provider messages, calendar payloads, Bee transcripts, Alexa request envelopes, credentials, or tokens.

## Data model

`audit_events` remains the append-only event table. Revision `d6a71c9e24f0` extends it with:

| Field | Purpose |
| --- | --- |
| `id` | `audit_event_id` returned by the API |
| `user_id` | authenticated CountOn owner |
| `expectation_id` | owned expectation, when applicable |
| `event_type` | stable event name such as `EVIDENCE_INGESTED` |
| `created_at` | event occurrence/commit time returned as `occurred_at` |
| `source_provider`, `source_type`, `source_provenance` | normalized source attribution |
| `source_reference` | SHA-256 pseudonymous correlation reference; never a raw provider ID |
| `evidence_id`, `evaluation_id` | links to existing immutable facts/results |
| `result_status` | evaluator-produced `MATCH`, `UNKNOWN`, or `MISMATCH` |
| `action` | concrete application action returned as `action_taken` |
| `actor_type` | `USER`, `SYSTEM`, or `PROVIDER` |
| `metadata` | allowlisted operational fields only |
| `idempotency_key` | stable replay key, unique per owner |

The migration adds foreign keys with `ON DELETE SET NULL`, actor/result checks, and indexes for owner/time, owner/source/time, owner/result/time, evidence, and evaluation queries. `(user_id, idempotency_key)` is unique. Existing rows are backfilled to the closest stable event type. Alembic remains the deployment source of truth; apply the revision with `alembic upgrade head` in each environment's normal migration process.

No snapshot column is added. Evidence and evaluations have no update API and remain the historical facts. Mutable expectations are linked and the action remains after expectation deletion; the foreign key becomes null. This avoids copying claims or provider content into a second personal-data store. Account deletion cascades through the owner's audit history.

## Events

The application emits these events in the same transaction as their corresponding operation:

- `EXPECTATION_CREATED`, `EXPECTATION_CONFIRMED`, `EXPECTATION_UPDATED`, `EXPECTATION_CANCELLED`
- `SOURCE_CONNECTED`, `SOURCE_AUTHORIZED`, `SOURCE_DISCONNECTED`, `SYNC_COMPLETED`
- `EVIDENCE_INGESTED`, `EVIDENCE_CORRELATED`
- `EVALUATION_COMPLETED`, `MISMATCH_DETECTED`
- `NOTIFICATION_CREATED`, `NOTIFICATION_SENT`, `NOTIFICATION_ACKNOWLEDGED`

The event mapper also reserves `RECOMMENDATION_APPROVED` and `RECOMMENDATION_DISMISSED`. No event is fabricated when a recommendation workflow did not persist either action.

Alexa capture records a confirmation with `source_provider=ALEXA`, `source_type=VOICE`, and `source_provenance=SIGNED_ASK`. It stores safe orchestration labels rather than utterances or request envelopes. Gmail, Outlook, and calendar events retain the normalized provider and an immutable evidence link. Amazon order evidence stays attributed to Gmail or Outlook while `source_type=AMAZON_ORDER_EMAIL`. Simulator events use `SIMULATED_RING` or `SIMULATED_BEE`; authorized Bee CLI evidence uses `LIVE_BEE_CLI`.

`EVALUATION_COMPLETED` and `MISMATCH_DETECTED` copy only the deterministic evaluator result, its reason code, and linked evidence IDs. Bedrock and frontend code cannot create evaluator result rows through this API.

## API

`GET /api/v1/audit-events` requires the existing Supabase bearer token and always scopes records to the authenticated user. It returns a JSON array ordered newest first. Query parameters are:

- `expectation_id`
- `source_provider`
- `result_status` (`MATCH`, `UNKNOWN`, or `MISMATCH`)
- `occurred_after` and `occurred_before` as timezone-aware timestamps
- `limit` from 1 to 100 and nonnegative `offset`

Each item includes the required audit fields plus a current expectation summary and an immutable evidence summary when those rows still exist. Evidence output contains normalized `value`, unit, and observation time; it never contains `raw_data`. There are no HTTP create, update, or delete routes for audit records.

The Activity page calls this endpoint, supports all four filters, links to an existing expectation, shows normalized evidence and evaluator status, and uses the provider observation time when evidence is present. Reloading the page reads the same PostgreSQL rows.

## Security, retention, and idempotency

- FastAPI applies owner filtering, and PostgreSQL RLS permits authenticated users to select only their own rows. Application writes remain backend-only.
- Metadata is reconstructed from an allowlist. Authorization headers, OAuth material, database URLs, provider bodies, and raw transcripts are never serialized.
- Provider and order correlation values are stored only as stable hashes.
- Audit writes share the business transaction; a failed audit write rolls the operation back.
- Evidence IDs, evaluation IDs, notification IDs, connection IDs, and capture IDs form stable idempotency keys. PostgreSQL conflict handling suppresses retry/replay duplicates.
- Rows are retained with the CountOn profile. Deleting an account removes its history. Deleting linked domain data nulls the link while preserving the minimal event until account deletion. A future retention policy may shorten this period, but must preserve owner isolation and documented deletion behavior.

## Sanitized examples

```json
{
  "audit_event_id": "8be7…",
  "counton_user_id": "1000…",
  "expectation_id": "d541…",
  "event_type": "EVALUATION_COMPLETED",
  "occurred_at": "2026-10-13T17:05:21Z",
  "source_provider": "GMAIL",
  "source_type": "AMAZON_ORDER_EMAIL",
  "source_provenance": "OFFICIAL_OAUTH",
  "source_reference": "sha256:…",
  "evidence_id": "198c…",
  "evaluation_id": "222e…",
  "result_status": "MISMATCH",
  "action_taken": "expectation.evaluated",
  "actor_type": "SYSTEM",
  "action_metadata": {
    "reason": "observed_value_exceeds_threshold",
    "evidence_ids": ["198c…"]
  }
}
```

```json
{
  "event_type": "EVIDENCE_INGESTED",
  "source_provider": "RING",
  "source_type": "RING_EVENT",
  "source_provenance": "SIMULATED_RING",
  "result_status": null,
  "action_taken": "evidence.ingested",
  "actor_type": "PROVIDER"
}
```

## Validation

`backend/tests/test_audit_history.py` covers linked evaluator results, source attribution, missing evidence remaining `UNKNOWN`, Ring/Bee provenance, replay suppression, notification creation/acknowledgement, privacy, persistence across repeated reads, and the absence of raw provider fields. Existing operational tests cover transaction rollback, concurrent retries, worker delivery, restart recovery, and RLS ownership. Frontend screen tests cover persisted timeline rendering; lint, type checking, tests, and production build validate the client contract.
