# Three persisted CountOn demos

Sign in and open `/demos`. The three scenario cards create normal owned records.
Running a card explicitly approves the listed demo sources for that expectation.
Existing simulator controls remain under **Advanced simulator controls**.

| Card | Saved expectation and evidence | Expected evaluator result |
| --- | --- | --- |
| Electricity Bill Surprise | Numeric `total_cost < 150`, zero tolerance; $180 user-submitted DEMO utility bill | MISMATCH; one unread in-app mismatch notification with default preferences |
| Package Arrived | Boolean `delivered`, upcoming Friday deadline; positive DEMO delivery confirmation plus SIMULATED Ring package observation | MATCH; no mismatch alert; “Silence is success.” |
| Plumber Commitment | Boolean `appointment_confirmed`, upcoming Friday deadline; SIMULATED Bee commitment with `context_only=true` | UNKNOWN; continue monitoring; no mismatch alert |

Friday is the end of the upcoming Friday in the browser timezone, saved as an
absolute timestamp. The package recipe demonstrates a positive observation before
that deadline using the existing boolean evaluator. It does not add temporal
evaluation semantics. Ring no-detection is never used as proof of nondelivery.
The Bee promise never supplies an observed arrival boolean.

## Request and persistence path

1. `POST /api/v1/expectations` creates the normal owned expectation. These fixed
   recipes are explicit demo inputs, not a second natural-language compiler.
2. Electricity and delivery DEMO facts use
   `POST /api/v1/expectations/{id}/evidence`, with `simulated=true`, `category=DEMO`
   and user-submitted provenance. No mailbox access is implied; no authorized
   provider record has been selected for these newly created demo expectations.
3. Electricity invokes `POST /api/v1/expectations/{id}/evaluate` with a stable
   per-run idempotency key. Ring and Bee use the existing authenticated
   `/api/v1/simulators/{ring|bee}/expectations/{id}/events` endpoints, which
   normalize, persist, and evaluate through existing services.
4. Every card reloads the expectation, evidence, latest evaluation, evaluation
   history, notification inbox and expectation-filtered audit events from normal
   APIs. Only backend results determine the displayed actual verdict.
5. Confirmed electricity MISMATCH requests Why through `/api/agent`, the same
   trusted orchestration/MCP path as `/alexa`. Explanations use recorded facts;
   the $180 bill alone cannot establish a tariff, usage or market explanation.
   The existing grounded fallback remains available when inference is disabled.

The standard expectation detail link and dashboard read the same SQL records.
Reloading the browser preserves the records there. Cards retain run receipts for
the current page visit; navigating back and running again explicitly creates a
new expectation. **Refresh saved result** only reads existing records.

Actual evidence IDs, evaluation IDs, notification statuses and safe provenance are
shown after execution. The activity timeline consists exclusively of returned
audit events. No notification or audit event is synthesized in React. In-app
notification creation respects the user's existing notification preferences.

Double-clicks are guarded synchronously. Saves are not automatically retried after
network failure; the created expectation link is retained whenever its ID was
received. Check that record or the Expectations list before starting another run.
No new reset/delete operation is added. The existing CLI reset is restricted to
its backend-tagged demo profile and does not own these normal web-created rows.

## Local validation (2026-10-23)

Backend: **35 passed**, real local PostgreSQL, normal HTTP routes, deterministic
evaluator, audit and notification persistence, simulator replay and cross-user
isolation. Cloud inference was explicitly disabled; the electricity Why test uses
the existing grounded fallback through orchestration/MCP.

```sh
cd backend
# Configure ENVIRONMENT=test, DATABASE_TARGET=local, a valid local application
# URL and separate loopback TEST_DATABASE_URL ending in _test. Use valid test
# conversation configuration; production provider credentials are unnecessary.
BEDROCK_ENABLED=false AWS_EC2_METADATA_DISABLED=true .venv/bin/python -m pytest -q tests/test_frontend_demo_scenarios.py tests/test_simulator_ingestion.py tests/test_simulator_authorization.py tests/test_adapters_and_simulators.py --tb=short
.venv/bin/ruff check tests/test_frontend_demo_scenarios.py
```

Frontend: **81 passed** across six targeted files; touched-file ESLint, full
TypeScript checking and `git diff --check` passed.

```sh
cd frontend
npm test -- tests/demo-scenarios.test.tsx tests/merge-regressions.test.tsx tests/simulators.test.ts tests/presentation.test.ts tests/api.test.ts tests/expectation-explanation.test.tsx
npx eslint components/demo-scenarios.tsx lib/demo-scenarios.ts tests/demo-scenarios.test.tsx tests/merge-regressions.test.tsx 'app/(workspace)/demos/page.tsx'
npm run typecheck
```

Frontend tests use isolated Auth/API fixtures. Backend tests verify the recipes
against PostgreSQL. This pass does not claim a live browser-to-cloud, Bedrock,
mailbox, Ring hardware or Bee hardware acceptance run.

## Manual demonstration

1. Run Electricity Demo. Open the saved evidence, confirm $180 vs `< $150`, the
   backend MISMATCH, notification status and real audit timeline. Read the returned
   grounded Why or its honest availability message.
2. Run Package Demo. Inspect both the DEMO delivery fact and SIMULATED Ring
   observation. Confirm backend MATCH and no mismatch alert.
3. Run Bee Demo. Inspect the SIMULATED commitment, backend UNKNOWN and continued
   monitoring. A recorded promise is not completed work.
4. Follow each **Open created expectation** link, reload the detail page, then open
   the normal dashboard. The same persisted records and statuses remain visible.
