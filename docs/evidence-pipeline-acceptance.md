# Evidence pipeline acceptance

CountOn uses one persisted workflow:

```text
Alexa or web statement
  -> typed Bedrock compilation and clarification
  -> explicit expectation confirmation
  -> persisted expectation
  -> source-plan preview
  -> explicit source confirmation
  -> encrypted provider synchronization or authenticated simulator/CLI import
  -> identifier-based evidence correlation
  -> deterministic MATCH / UNKNOWN / MISMATCH
  -> append-only Audit History
  -> one deduplicated notification for a supported MISMATCH
```

The compiler interprets language and the mismatch investigator can explain a recorded contradiction. Neither assigns evaluation status. `evaluation_service` and the deterministic evaluators remain authoritative.

## Capture and authorization

The compiler contracts validate the subject, metric, comparison, operand, deadline, and suggested source types. Missing material facts return one clarification question. Alexa and the trusted web agent require capture confirmation before calling the existing persistence path. The manual web form presents a final preview before its authenticated create request.

Creating an expectation does not authorize a provider. The source planner reads only the current user's connected projections and proposes exact source references. `ConfirmMonitoringPlan.confirmed` accepts only literal `true`; confirmation recomputes the plan under locks and rejects stale, cross-user, mixed-group, revoked, or caller-invented references. `ExpectationSourceBinding` then records the owned sync and typed `SourceRule`.

Source rules require strong identity:

- bills: exact sender plus thread/topic identity;
- Amazon order emails: exact sender plus `order_id`;
- replies: exact sender and thread;
- calendars: exact event ID, calendar UID, and occurrence where applicable;
- simulators and Bee imports: explicit expectation association through authenticated endpoints.

The on-demand evaluator now applies the same approved `expectation.evidence_sources` filter as scheduled monitoring. An unapproved newer record cannot override approved evidence, is not marked correlated, and does not wake automatic monitoring. It remains identifiable as user-submitted ingestion history. An empty source list continues to allow explicitly submitted user evidence, but it does not grant Gmail, Outlook, calendar, Ring, or Bee provider authority.

## Source behavior

| Source | Implemented behavior | Provenance and verification status |
| --- | --- | --- |
| Gmail | OAuth-owned connection, encrypted credentials/checkpoints/facts, paginated initial and incremental sync, sender/thread/order correlation, token refresh and revocation fencing | `OFFICIAL_API`; fixture and mocked-provider tested, live account not verified in this workspace |
| Outlook | Same ownership and synchronization contract through Microsoft Graph; delta cursor recovery and permission expiry handling | `OFFICIAL_API`; fixture and mocked-provider tested, live account not verified |
| Google Calendar | Exact event/occurrence correlation, recurring/all-day events, cancellations, updates, reschedules, time zones, sync-token reset | `OFFICIAL_API`; fixture and mocked-provider tested, live account not verified |
| Microsoft Calendar | Exact event/occurrence correlation and delta-link recovery with the same owned binding model | `OFFICIAL_API`; fixture and mocked-provider tested, live account not verified |
| Amazon orders | Extracted only from authorized Gmail/Outlook messages. Order confirmation, shipment, delivery, cancellation/refund facts retain the email provider and exact protected order correlation. | `source_type=AMAZON_ORDER_EMAIL`; no direct Amazon shopping API is claimed |
| Ring | Authenticated demo endpoint requires an expectation that explicitly allows `ring_simulator`. A positive associated observation can be evidence; no detection remains UNKNOWN. | `SIMULATED_RING`; no live Ring device/API claim |
| Bee simulator | Authenticated demo endpoint requires `bee_simulator`. A promise/commitment is context and cannot prove completion. | `SIMULATED_BEE`; no live wearable claim |
| Bee CLI | Short-lived single-use pairing, local connector credential, staged preview, explicit record selection and consent, stable external IDs, checkpointing, revocation, and minimal imported facts. | `LIVE_BEE_CLI` only for authorized imports; implementation is fixture-tested, not verified against a real Bee account here |

Provider records retain observation timestamps, stable encrypted projections, sync generation, and safe references. Full emails, calendar payloads, audio, and Bee transcripts are not copied into Audit History.

## Correlation and evaluation

Provider synchronization first stores an encrypted source projection keyed by `(sync_id, external_id)`. Replays with an unchanged version are suppressed. Older calendar updates cannot replace newer source timestamps. Completed sync rounds publish evidence only through current owned bindings and current OAuth generation.

Evaluation uses the latest `observed_at` for the exact metric and approved source. Same-time conflicts, cross-provider disagreement, missing facts, stale/future facts, insufficient confidence, revoked permissions, incomplete mailbox coverage, and ambiguous bindings yield UNKNOWN. Calendar authority and occurrence identity prevent a similarly named event from attaching to an expectation. Missing Ring detection and a Bee promise also yield UNKNOWN.

- **MATCH:** evaluation is persisted; no mismatch notification is created.
- **UNKNOWN:** evaluation is persisted, expectation returns to `monitoring`, and the durable job remains pending when eligible.
- **MISMATCH:** evaluation and evidence references are persisted; one in-app notification is created for the contradiction episode. A grounded Bedrock explanation is generated only on the existing explanation path and falls back safely if the model is unavailable.

Audit events for ingestion, correlation, evaluation, mismatch, notification, source authorization/disconnection, and completed sync share the business transaction. See [Audit History contract](audit-history-contract.md).

## Recovery guarantees

- PostgreSQL `FOR UPDATE SKIP LOCKED` leasing permits concurrent workers without duplicate claims.
- Lease tokens and run keys fence stale workers after a restart.
- Failed jobs retry with bounded exponential backoff and become durable failed/dead-letter rows after their attempt budget.
- Provider cursors are encrypted and committed only with the processed page; expired cursors use the provider's bounded reconciliation path.
- Stable evidence, evaluation, audit, and notification idempotency keys suppress retries and replays.
- Out-of-order calendar facts cannot overwrite newer authoritative facts.
- Disconnect/revocation deletes provider authority and sync state. A worker that read provider data before revocation cannot publish it afterward.
- Multiple sources are reconciled conservatively; disagreement produces UNKNOWN rather than a fabricated verdict.

## Acceptance scenarios

| Scenario | Expected result | Automated evidence |
| --- | --- | --- |
| Electricity bill below $150, bill fact $180 | MISMATCH, contradicted, one notification, linked audit event | `test_evidence_pipeline_acceptance.py` |
| Electricity bill below $150, bill fact $125 | MATCH, fulfilled, no notification | `test_evidence_pipeline_acceptance.py` |
| No bill yet | UNKNOWN, monitoring continues, no notification | `test_evidence_pipeline_acceptance.py`, `test_monitoring.py` |
| Newer unapproved bill source | ignored; approved source decides | `test_operational_data.py::test_on_demand_evaluation_ignores_newer_unapproved_source` |
| Authorized Amazon order email | exact sender/order correlation; estimates alone remain UNKNOWN | `test_automatic_tracking.py`, `test_source_correlation.py` |
| Calendar appointment rescheduled | latest authoritative occurrence used; conflicting reschedules UNKNOWN | `test_provider_sync.py`, `test_source_correlation.py` |
| Associated Ring package observation | MATCH when the persisted fact supports the expectation | `test_simulator_ingestion.py`, `test_simulator_authorization.py` |
| Ring reports no detection | UNKNOWN, no mismatch notification | `test_simulator_ingestion.py` |
| Bee plumber commitment | context only; UNKNOWN until outcome evidence exists | `test_simulator_ingestion.py`, `test_bee_cli_bridge.py` |
| Real Bee record | import requires paired connector, staged candidate, explicit consent/source binding | `test_bee_cli_bridge.py`; real account remains unverified |
| Cross-user access | expectation/evidence/source access denied or absent | provider, simulator, Bee, ownership, and RLS tests |
| Duplicate replay | one evidence row/evaluation episode/notification as applicable | operational, provider sync, simulator, Bee, and monitoring tests |
| Worker restart | expired lease reclaimed; stale worker fenced | `test_monitoring.py`, `test_automatic_tracking.py` |
| Audit refresh | PostgreSQL history returns the same owner-scoped timeline | `test_audit_history.py` |
| Source disconnected during read | collected data cannot be published; future connector calls denied | `test_provider_sync.py`, `test_microsoft_provider.py`, `test_bee_cli_bridge.py` |

## Local verification

Use only the dedicated local database whose name ends in `_test`:

```bash
cd backend
TEST_DATABASE_URL=postgresql+psycopg://counton:counton_dev_password@127.0.0.1:5432/counton_test .venv/bin/pytest -q
.venv/bin/ruff check app db/scripts tests alembic ../scripts
.venv/bin/mypy app --ignore-missing-imports

cd ../frontend
npm run lint
npm run typecheck
npm run test
npm run build
```

## Unresolved external acceptance

- No authorized live Gmail, Outlook, Google Calendar, or Microsoft Calendar account was synchronized during this pass.
- No real Bee CLI account/data import was performed. The connector remains fixture-tested and optional.
- Ring and Bee demo evidence is intentionally simulated.
- No physical Alexa/Echo interaction was performed; signed ASK requests and shared persistence are automated locally.
- A real Bedrock compiler/investigator call requires configured AWS credentials and model access. Model failure paths are tested without allowing AI to decide status.
- Production workers, OAuth callbacks, encryption keys, and provider watch URLs still require deployment-specific secrets and provider-console configuration.

No production migration, provider credential change, deployment, commit, or push is part of this acceptance pass.
