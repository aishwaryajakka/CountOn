# Bedrock Mismatch Investigator

The deterministic evaluator answers **“Did the expectation fail?”** Bedrock answers
**“Given the evidence we actually have, how can we explain what happened?”**
The recorded result, comparison target, observed value, tolerance and evaluator
reason remain authoritative. Explanation never changes evaluation or writes expectation/evaluation/evidence
rows. The existing authenticated MCP explanation tool is consumed by `/alexa`.

## Service responsibilities

The similarly named modules are intentionally retained:

- `app/services/investigation_service.py` is the pure explanation boundary. It
  accepts already-loaded typed expectation/evaluation/evidence, delegates to the
  canonical investigator, and owns/closes a default client. It does no auth,
  database reads or persistence.
- `app/services/investigator_service.py` is owned database orchestration. It loads
  the owned expectation and latest evaluation, gates MISMATCH, bounds evidence
  reads, then delegates to the pure boundary. Non-mismatch/missing evaluation uses
  existing domain errors.

They are not duplicate implementations. The MCP explanation tool has its own
response-oriented outcome gate (MATCH/UNKNOWN/no evaluation are friendly results),
then calls the pure service with that same loaded snapshot and provenance. This
avoids reloading a different evaluation between gating and explanation. Neither
module changes evaluator outcomes, and neither is renamed in this cleanup.

## Service contracts

For an owned database read, use the existing orchestration module:

```python
from app.services.investigator_service import investigate_expectation_mismatch

explanation = investigate_expectation_mismatch(db, expectation_id, verified_user_id)
```

It delegates to existing ownership-enforcing services, loads the latest evaluation
using `created_at DESC, id DESC`, rejects MATCH/UNKNOWN before evidence reads or
inference, and uses the existing bounded historical evidence repository. Missing
evaluations and denied ownership use existing domain errors. It neither writes
rows nor changes routes; the pure service below remains the only AI implementation.

```python
from app.schemas.investigation import InvestigationContext
from app.services.investigation_service import investigate_mismatch

explanation = investigate_mismatch(
    expectation=expectation_response,  # existing ExpectationResponse
    evaluation=evaluation_response,    # existing EvaluationResponse
    evidence=evidence_responses,       # Sequence[existing EvidenceResponse]
    context=InvestigationContext(authenticated_user_id=verified_user_id),
)
```

Calls with MATCH/UNKNOWN, unrelated evaluation/evidence IDs or a mismatched
principal raise a fixed-message `InvestigationInputError` before AWS. Context is
optional for trusted internal callers; this function is **not** an authorization
endpoint. Transport orchestration must authenticate first, load rows using
existing ownership-enforcing expectation/evaluation/evidence services and pass
that verified principal. Never accept principal/ownership claims from a payload.
The optional `investigator` injection supports offline tests; default clients are
closed by the service. No provider SDK is introduced into transport/services.

## Selection and privacy

1. Normalize values from the **historical evaluation**, not the current mutable
   expectation's baseline or materiality threshold.
2. Pin E1 to `evaluation.observed.evidence_id` and verify its value against the
   snapshot. Missing or inconsistent pinned evidence produces a deterministic,
   uncorroborated fallback. Legacy snapshots without IDs use shared evaluator
   ordering: `observed_at`, then `created_at`, then UUID, descending.
3. Include only exact metric observations and explicitly allowlisted contributors:
   `energy_usage_change` and `rate_change` for `total_cost`. Contributors require
   an explicit numeric `percentage` and percent-compatible unit; bools and USD
   contributor amounts are not relabeled as percentages.
4. Evidence must belong to this expectation, have usable confidence, and have
   existed at evaluation time. Contributors cannot be observed after the pinned
   primary measurement. Same-time differing observations surface conflicts;
   these never justify choosing a causal source. Confidence is a usability gate,
   **not** causal confidence.
5. Assign deterministic E labels. Preserve provenance locally as UUID references,
   but send only E label, safe metric, numeric/boolean value and allowlisted unit.
   Do not send claims, user/row identifiers, source text, external IDs, raw_data,
   provider message bodies, compiler metadata, secrets or unrelated evidence.

Default selection is six records, configurable through `INVESTIGATOR_MAX_EVIDENCE`
(1–12). `INVESTIGATOR_MAX_PROMPT_BYTES` defaults to 12000 (2048–64000), budgeting
system instructions, schema, selected facts and repair headroom. Native structured
output's second schema copy is included. Tail evidence is removed deterministically
if needed; conflicts and truncation remain visible even when records are omitted.
If no evidence fits or is useful, AWS is skipped entirely. Already-loaded input
rows are not a database pagination strategy; transport integration should bound
owned reads and provide the pinned record explicitly.

## Output and grounding

`MismatchExplanation` contains immutable MISMATCH, deterministic summary,
structured expected/observed snapshots, evaluator reason, concise key factors,
caveats, confidence note, evidence-reference-to-UUID mapping, prompt version,
`grounded: true`, and generation `bedrock` or `deterministic`.
It also contains `insufficient_evidence` and a deterministic `confidence` indicator.
This is an uncalibrated, conservative evidence-support policy, not a causal
probability or model-generated score: supported contribution factors are capped
at 0.5 and by the selected records' minimum confidence. Conflicting fact factors
halve that cap/value (at most 0.25), and mark evidence insufficient. Fallbacks or
measurement-only factors have zero confidence and insufficient evidence. Conflicts
are explicit in the summary as well as caveats, even on fallback.

Bedrock proposes a strict `InvestigatorDraft` with **closed factor kinds**, not
arbitrary prose. The renderer uses trusted wording for recorded measurement,
usage change, rate change, possible rate contribution or conflicting observations.
This deliberately limits supported explanations; a model cannot invent a fuel
surcharge even if it cites a valid evidence ID. Supporting other domains requires
an explicit fact allowlist and corresponding validated renderer, not free-form
claims or passing raw provider data.
The model draft has no result/outcome/verdict field; such fields are rejected,
including a model-provided MISMATCH. Only trusted application code supplies the
immutable result on the public explanation. Existing `summary`, factor
`description` and `evidence_refs` names are preserved for current consumers.

Each proposed factor must reference existing unique E labels, supply exactly
those numeric/boolean values, match them without treating `false` as zero, and
satisfy metric/time/factor-specific checks. Expected/observed snapshots must be
identical to the normalized evaluation. Unexpected fields, fabricated kinds,
external knowledge and chain-of-thought are rejected by schema validation.
Causal contribution requires primary bill plus negative usage and positive rate,
with no conflicts and a bill above a less-than/less-than-or-equal target. This is a
direction check on recorded facts, not a new evaluation. It is expressed as **could have contributed**; no net effect,
shared billing period or definitive causal conclusion is asserted.

`grounded` means accepted facts are supported by the supplied records; it does
not claim an explanation proves causality or that the upstream data is true.
Sparse evidence returns “not enough supporting evidence.” All responses include
causality uncertainty. Unavailable historical fields are explicitly marked rather
than inferred. A zero-target absolute threshold is not converted to a percentage.

## Resilience, cost and telemetry

Prompt version: `v2`; temperature: zero. Reuses the existing feature-gated Converse
adapter, bounded infrastructure retries/timeouts and at most **one JSON/schema
repair**. Semantic grounding failures immediately downgrade; they do not trigger
another inference. Bedrock disabled/unavailable, malformed output or repair
failure returns a deterministic evaluation-derived explanation with no model text.

Existing telemetry records operation/model, token totals, AWS request ID, latency,
retry/repair counts, validation and correlation ID. Investigator completion adds
safe result status and duration. No JWTs, prompts, raw evidence, response text or
exception payloads are logged. `BEDROCK_ENABLED` remains off by default; configure
AWS region/model and least-privilege access as in [the foundation guide](README.md).

No cache infrastructure or evaluation-field persistence was added. A future cache
could use evaluation ID, prompt version, model ID **and selected-facts fingerprint**;
the extra fingerprint matters when evidence availability changes. An authorized
owner check must precede any cache return, with bounded retention/invalidation.

## Reference audit

`CountOn-main.zip` was read as a behavioral reference, not extracted into or merged
with the application. Its investigator service's owned/latest-evaluation idea
fits this orchestration boundary. Its AI client/compiler/models are not used:
the current implementation has strict parsing, bounded retries and repair,
grounding, private-data minimization, clarification and safe telemetry already.
The reference investigator uses automatic mock selection, hard-coded demo
percentages and unsupported causal claims; its result schema has no evidence-ID
grounding. None of that implementation is copied. The archive contains compiler
service tests but no dedicated investigator tests to port. Electricity evidence
is retained as a test concept with additional non-demo-value coverage.

## Electricity example

For recorded target `< 142.10`, observed `162`, relative threshold `0.05`, and
supplied utility bill (USD), usage `-18%` and rate `+22%`:

- Summary: “CountOn recorded MISMATCH: expected < $142.10; observed $162.00.
  Recorded materiality threshold: 5% (relative).”
- E1: “The recorded total_cost measurement was $162.00.”
- E1/E2/E3: “Usage fell 18% while the rate rose 22%. The higher rate could have
  contributed to the bill mismatch; these observations do not establish a net
  effect or cause.”
- Caveat: observations do not prove causality or matching billing periods.

This output is verified by an **offline mocked Converse** test, not a live AWS
model invocation. With Bedrock disabled/down, the same immutable summary is
returned with insufficient-cause wording and no invented factors.

## Validation and current integration

From `backend`, with the existing `.venv` activated:

```sh
pytest -q tests/test_bedrock.py tests/test_expectation_compiler.py \
  tests/test_clarification.py tests/test_mismatch_investigator.py
pytest -q  # requires private TEST_DATABASE_URL for isolated loopback *_test DB
ruff check app/ai app/schemas/investigation.py app/services/investigation_service.py \
  tests/test_mismatch_investigator.py
mypy --strict --follow-imports=silent --ignore-missing-imports app/ai \
  app/schemas/compiler.py app/schemas/clarification.py app/schemas/investigation.py \
  app/services/compiler_service.py app/services/investigation_service.py app/mcp/compiler.py
```

The existing MCP integration authenticates, fetches the owned latest evaluation
and relevant historical evidence, and calls this service only for MISMATCH.
`/alexa` speaks the concise server message while keeping expectation/evaluation/
evidence IDs, Bedrock usage and fallback usage available as structured provenance.
MATCH, UNKNOWN and missing evaluation do not invoke this investigator.

Current validation is recorded in the task report. Tests use mocked model outputs
and isolated PostgreSQL for real persistence/evaluation/MCP acceptance. They do not
claim live model quality or completed Alexa/Echo integration.
