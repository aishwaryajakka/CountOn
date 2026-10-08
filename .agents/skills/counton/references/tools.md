# CountOn MCP contracts and examples

Use the host-configured endpoint. The current public deployment is
`https://counton-mcp.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com/mcp`.
Transport is Streamable HTTP, with the current user's Supabase bearer session.
The skill supplies instructions, not credentials or a connection implementation.

## Contracts

| Tool | Input inside `request` | Structured output |
| --- | --- | --- |
| `list_expectations` | Optional `limit` (1–100, default 50), `offset` (>=0, default 0), `status`, `type` | `expectations` array, `limit`, `offset` |
| `get_expectation` | `expectation_id`: real UUID from user or owned list result | Compact expectation |
| `capture_expectation` | Existing `ExpectationCreate` fields below | Saved compact expectation |

Compact fields are `id`, `claim`, `type`, `status`, `metric`, `created_at`.
Current tools do not expose baseline, target, evidence, evaluation results or
causal reasoning. Page length is not a total count unless all pages were read.
Hosts may namespace names; choose the matching discovered CountOn tool.

Capture accepts nonempty `claim`, `type`, and optional `metric`, `comparison`,
`baseline`, `target_value`, timezone-aware `deadline`, `evidence_sources`, and
`materiality_threshold` (0–1, default 0.05). Numeric comparisons require metric,
comparison, and baseline or target. Extra fields, including identity, are rejected.

- Types: `numeric_comparison`, `boolean`, `temporal`, `event`.
- Comparisons: `less_than`, `less_than_or_equal`, `greater_than`,
  `greater_than_or_equal`, `equal`, `not_equal`.
- Stored statuses: `monitoring`, `fulfilled`, `contradicted`, `unknown`,
  `resolved`, `cancelled`. Status is neither capture input nor evaluation result.

Discover live schemas first. Repository contracts are in
`backend/app/mcp/schemas.py`, `backend/app/schemas/expectation.py`,
`backend/app/db/models/expectation.py`, and `frontend/lib/types.ts`.

## List

“What am I counting on?” → `list_expectations`:

```json
{"request":{"limit":50,"offset":0}}
```

Summarize actual claims and stored statuses. An empty complete list means
“You're not counting on anything yet.” Never generate demonstration rows.

## Detail

“Tell me about my electricity bill expectation.” → list first and match actual
claim/metric. If exactly one matches, get its returned UUID. For illustration
only, if an owned list result supplied this UUID, use:

```json
{"request":{"expectation_id":"12345678-1234-4234-8234-123456789abc"}}
```

Do not reuse this illustrative ID unless actually returned. Clarify multiple
matches; report no match honestly. Show returned fields without inventing amounts
or evaluations.

## Capture

“I'm counting on my grocery bill staying under $120 this week.”

Established context for this example: USD, local date 2026-10-08, timezone
`America/Chicago`, week ending Sunday. The existing grocery demo uses metric
`total_cost`. “Under” is strict: `less_than`, zero tolerance. No source was given.
Call `capture_expectation` with:

```json
{
  "request": {
    "claim": "I'm counting on my grocery bill staying under $120 this week",
    "type": "numeric_comparison",
    "metric": "total_cost",
    "comparison": "less_than",
    "target_value": 120,
    "deadline": "2026-10-12T04:59:59.999Z",
    "evidence_sources": [],
    "materiality_threshold": 0
  }
}
```

Recompute the deadline for the real reference time and established timezone/week
boundary. Do not copy the example date. If currency, timezone, week boundary or
intended metric is unknown, clarify rather than assume this example's context.
On success: “Got it. I saved that expectation in CountOn.” Link the returned ID
to the host-configured frontend's `/expectations/{id}`. Do not claim evidence,
evaluation, automatic ingestion or a notification was created.

## Clarify and disclose limits

“I'm counting on my bill being lower.” → “Which bill, and lower than what amount
or previous bill? What period should CountOn track?” Wait for missing facts;
do not infer `total_cost`, baseline or provider from other examples.

“Why did it fail?” → Read the identifiable stored record. If marked contradicted,
report that status and disclose that current tools do not expose evidence or
evaluation reasoning. Offer its CountOn detail page; do not guess a cause.

Missing/rejected auth → host sign-in. Unavailable server → disclose connection
failure. Validation error → clarify inputs without raw upstream errors. An
inaccessible UUID is not permission to enumerate another user's records.
