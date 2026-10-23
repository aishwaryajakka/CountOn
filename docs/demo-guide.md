# Demo Guide

Sign into the web workspace and open `/demos`. The three cards operate on normal
CountOn records owned by that user. Use a demo account whose records may remain in
the normal dashboard. Each Run action approves the named demonstration sources.
There is no broad reset/delete action.

## Demo 1 — Electricity / MISMATCH

**Expectation:** “My next electricity bill should be below $150.” The recipe saves
a numeric `total_cost` comparison, `less_than`, target 150 and zero materiality
tolerance. It submits an explicit user-provided DEMO utility bill of **$180 USD**.
It does not impersonate a mailbox or a live utility provider.

**Backend behavior:** save the expectation, evidence and deterministic MISMATCH;
record an in-app notification when mismatch alerts are enabled; append real audit
events. The Why request follows the shared trusted orchestrator/MCP path. It uses
only the recorded bill and evaluation. If Bedrock is unavailable, the existing
grounded fallback can explain the comparison without inventing why rates changed.

**UI behavior:** show expected `< $150`, observed $180, actual MISMATCH and the
$30 presentation difference; evidence/provenance, notification status, evaluation
history, activity and the link to the created expectation.

**What this proves:** typed threshold evaluation and grounded explanation remain
separate. A model cannot silently reinterpret a mismatch as a match.

## Demo 2 — Package / MATCH

**Expectation:** “My package should arrive by Friday.” The recipe stores a boolean
`delivered` criterion with the upcoming Friday deadline in the browser's timezone.

**Evidence:** a positive **DEMO delivery confirmation**, followed by a positive
**SIMULATED Ring** package observation, explicitly associated with this new record.
They are not real carrier/device observations.

**Backend behavior:** normalized evidence is persisted; the existing boolean
evaluator returns MATCH for the positive delivery fact. No mismatch notification
is created. This demo supplies an observation before the saved deadline; it does
not implement general temporal/event evaluation. Monitoring's narrower deadline
rules are a separate service path.

**UI behavior:** actual MATCH, no mismatch alert and “Silence is success.” Evidence
retains the DEMO/user-submitted or `SIMULATED_RING` provenance.

**What this proves:** positive evidence can settle a supported expectation quietly.
Absence of Ring detection is never used as proof of nondelivery.

## Demo 3 — Plumber / UNKNOWN

**Expectation:** “My landlord said the plumber will arrive Friday.” The saved
boolean metric is `appointment_confirmed`, with a Friday deadline.

**Evidence:** the Bee simulator submits that same commitment summary, with a
confirmed promise and `context_only=true`. It supplies no observed arrival value.

**Backend behavior:** save `SIMULATED_BEE` evidence and deterministic UNKNOWN;
continue monitoring. Do not fulfill, contradict or issue a mismatch alert merely
because someone made a promise.

**UI behavior:** “Commitment observed”, “Arrival not yet confirmed”, and actual
UNKNOWN / still watching. The ordinary detail page retains the same evidence.

**What this proves:** uncertainty is explicit, and context is not outcome evidence.

## Demo integrity

Simulators generate evidence only. They do NOT calculate the final state. The
CountOn backend performs persistence, evaluation, notification and audit writes;
the trusted explanation boundary loads the saved result. A Run handler creates
the explicit structured demo expectation, then uses the existing evidence APIs.
It does not add a parallel compiler, evaluator or database.

Use **Evidence & provenance**, **Evaluation history** and **Activity timeline** on
each card. Follow **Open created expectation**, reload, and find the same row in
the normal dashboard. IDs are persisted backend IDs, not browser-only demo objects.
The timeline contains returned audit records, not inferred actions.

Run is guarded against double-clicks. Refresh only reloads saved records. An
ambiguous network failure is not automatically retried as a new save; inspect the
created record or owned list first. Navigation/re-running intentionally creates
a new normal record. The older CLI reset owns a different backend-tagged demo
profile and must not be used to delete these web-created records.

## Short judge walkthrough

1. Open `/alexa`: list owned expectations; create a complete grocery expectation
   or clarify an incomplete bill. Approve capture and follow the normal detail link.
2. Run Electricity Demo. Show target/evidence, MISMATCH, actual notification and Why.
3. Run Package Demo. Show the SIMULATED label, MATCH and lack of mismatch alert.
4. Run Bee Demo. Show the promise, UNKNOWN and unconfirmed arrival.
5. Reload a detail page and open Activity to show persistence and linked history.

Describe `/alexa` as the CountOn web simulator. Only demonstrate a physical Alexa
device after actual account-linking, Console and Echo acceptance. See
[traditional Alexa](traditional-alexa.md), [frontend demo mechanics](../frontend/docs/demo-scenarios.md)
and [testing](testing.md). Current execution results belong in the testing report,
not in a claim that an integration is live.
