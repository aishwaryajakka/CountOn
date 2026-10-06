# CountOn MCP handoff

## Architecture

Alexa+ client → MCP/orchestration → existing CountOn services → repositories →
PostgreSQL/Supabase. The standalone server uses official Python MCP SDK 2.x,
stateless **Streamable HTTP** and JSON responses. It does not replace FastAPI,
compile natural language, or change deterministic evaluation.

## Run Locally

Keep configuration and secrets in ignored `backend/.env.local`. Both processes
must select the same database. From the existing repository root:

```bash
docker compose up -d
cd backend
source .venv/bin/activate
python -m pip install -r requirements.txt
DATABASE_TARGET=local alembic upgrade head
DATABASE_TARGET=local uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal, from the repository root:

```bash
cd backend
source .venv/bin/activate
DATABASE_TARGET=local uvicorn app.mcp.server:app --host 127.0.0.1 --port 8003
```

MCP endpoint: **http://127.0.0.1:8003/mcp**. FastAPI:
**http://127.0.0.1:8000**. Each exposes `/health` and `/ready`; MCP readiness
checks DB/schema, not external Auth availability. Localhost Host/Origin
protections remain enabled. Every MCP HTTP response includes `X-Request-ID`.

## Auth

Send `Authorization: Bearer <Supabase access token>` with every tool call.
CountOn reuses its existing JWT signature/issuer/audience/expiry verification.
Identity comes from injected HTTP context; `user_id`, `owner_id`, and
`profile_id` are never accepted as tool inputs. Repository ownership filters
apply unchanged. Missing and cross-user IDs return the same not-found error.
Initialization, schema discovery, and health paths expose no private rows and
are public. Tool failures are MCP `isError: true` results, usually carried by
HTTP 200; clients must check `isError`, not just the HTTP status.

There is no development auth bypass. The smoke client's optional
`--demo-login` obtains a **real** token from configured demo credentials and is
restricted to development/test. This is not a complete MCP OAuth discovery or
Alexa account-linking implementation.

## Tools

Exactly these three tools are registered. All arguments use one `request`
object; extra fields and outer arguments are rejected.

| Tool | Description | Input | Output |
| --- | --- | --- | --- |
| `capture_expectation` | Stores a structured expectation the current user wants CountOn to monitor. | Actual `ExpectationCreate` | Compact expectation |
| `get_expectation` | Returns one expectation and its current status. | `expectation_id`: UUID | Compact expectation |
| `list_expectations` | Lists the current user's expectations. | Optional `status`, `type`, `limit` (1–100, default 50), `offset` (≥0) | `expectations`, `limit`, `offset` |

Capture accepts `claim`, `type`, optional `metric`, `comparison`, `baseline`,
`target_value`, timezone-aware `deadline`, `evidence_sources`, and
`materiality_threshold` (0–1, default 0.05). Numeric expectations require metric,
comparison, and baseline or target_value through existing service validation.
The claim is a field of this structured object; a bare utterance is not input.
Use the discovered SDK schemas for exact enums and constraints.

A compact expectation contains only `id`, `claim`, `type`, `status`, `metric`,
`created_at`. UUIDs and timestamps are strings in JSON. List pagination has no
separate total count. Tool annotations mark get/list read-only and idempotent;
capture creates a row and is **not idempotent**. Do not automatically retry a
capture after an ambiguous timeout: reconcile using list/get first.

Safe error codes: `INVALID_ARGUMENTS`, `INVALID_EXPECTATION`, `UNAUTHORIZED`,
`NOT_FOUND`, `DATABASE_ERROR`, `SERVICE_ERROR`. SDK text may prepend a tool name;
check `isError` and the safe code. SQL, traces, tokens, URLs and rejected values
are omitted. Completion logs contain request/tool/user/status/duration only.

## Example Calls

After an MCP client initializes, call tools in this order. These are the
`name`/`arguments` fields for the SDK's `call_tool`, not plain REST endpoints:

```json
{"name":"list_expectations","arguments":{"request":{"limit":10,"offset":0}}}
```

Select an ID from that result, then:

```json
{"name":"get_expectation","arguments":{"request":{"expectation_id":"<id from list>"}}}
```

Capture a new structured expectation when the user asks to monitor it:

```json
{
  "name": "capture_expectation",
  "arguments": {
    "request": {
      "claim": "My next electricity bill should be lower",
      "type": "numeric_comparison",
      "metric": "total_cost",
      "comparison": "less_than",
      "baseline": 142.1,
      "materiality_threshold": 0.05
    }
  }
}
```

Successful capture/get `structuredContent`:

```json
{
  "id": "<expectation UUID>",
  "claim": "My next electricity bill should be lower",
  "type": "numeric_comparison",
  "status": "monitoring",
  "metric": "total_cost",
  "created_at": "<ISO 8601 timestamp>"
}
```

List wraps those objects as
`{"expectations":[...],"limit":10,"offset":0}`. A stored expectation is not an
evaluation outcome; get returns the persisted status, not a new evaluation.

## Testing

Third terminal, from the repository root:

```bash
cd backend
source .venv/bin/activate
DATABASE_TARGET=local python db/scripts/mcp_smoke.py
```

The token prompt is hidden; alternatively use the existing configured demo
credentials with `--demo-login`. If FastAPI uses port 8004, pass
`--api-url http://127.0.0.1:8004`. Never pass tokens as CLI arguments.
The smoke uses the real SDK network client, verifies all three tools and the
same row through FastAPI, exercises four error paths, and removes only its exact
unique smoke-tagged rows. Normal audit records remain. Cleanup failure exits
nonzero. Only loopback URLs without credentials/query/fragment are allowed.

Run `python -m pytest` from backend with the existing dedicated local
`TEST_DATABASE_URL` ending in `_test`. Without it DB tests skip. Network tests
reuse signed JWT fixtures and savepoint-isolated PostgreSQL, requiring no live
Supabase, Alexa+, or Bedrock. No backend lint/type tool is configured;
`python -m pip check` verifies dependencies.

## Person 2 Compiler Integration

`backend/app/mcp/compiler.py` defines a **Protocol only**:

```python
compile_expectation(text: str, context: CompilationContext) -> StructuredExpectation
```

`StructuredExpectation` aliases the actual `ExpectationCreate`, and
`CompilationContext` carries a trusted authenticated user, timezone-aware
reference time, and verified IANA timezone. The orchestrator supplies context;
never accept it as an ownership assertion from Alexa/tool arguments. No tokens
or raw provider payloads belong in compiler context or output.

Future flow: utterance → orchestration → Person 2's compiler → validate
`ExpectationCreate` → `capture_expectation` under the same verified identity.
The compiler must not persist, evaluate, choose an owner, or invoke capture
itself. Missing baseline/metric/comparison/timezone facts require clarification;
do not guess values. Clarification/error handling and the eventual sync/async
adapter belong to the integration pass. No compiler implementation, Bedrock
client, or compile tool is registered here.

## Future Tools (not registered)

| Tool | Purpose | Proposed inputs | Proposed output | Existing service to reuse |
| --- | --- | --- | --- | --- |
| `add_evidence` | Attach normalized evidence | expectation UUID, actual `EvidenceCreate`, optional idempotency key | Evidence ID, expectation ID, source, metric, value, unit, observed_at, confidence | `evidence_service.add_evidence` |
| `evaluate_expectation` | Run deterministic evaluation | expectation UUID | Evaluation ID, result MATCH/UNKNOWN/MISMATCH, expected, observed, confidence, reasoning, created_at | `evaluation_service.evaluate_expectation` |
| `explain_contradiction` | Explain persisted contradiction facts | expectation UUID | Persisted result, expected/observed and reasoning; no invented explanation | `evaluation_service.get_latest_evaluation`; no implemented investigator service exists |
| `update_expectation` | Update allowed fields | expectation UUID, actual `ExpectationUpdate` | Compact updated expectation | `expectation_service.update_expectation` |
| `resolve_expectation` | Mark resolved without deletion | expectation UUID | Compact expectation with status resolved | `expectation_service.update_expectation` with `ExpectationUpdate(status="resolved")` |

All future calls must reuse verified identity and existing ownership checks.
Explanations should report the persisted deterministic reasoning; Person 2's
future investigator may enrich it later, but the current investigator module
is only a placeholder. No new service or false functionality is provided.

## Known Limitations

Local service behavior is verified. Remote TLS/hosting, OAuth resource metadata
and client login/discovery, Alexa+ account linking/tool onboarding, capture
idempotency, conversation orchestration, and the compiler implementation are
unfinished. No Bedrock, Ring/Bee, schema, or evaluator changes are included.

## Next Steps for Alexa+

Confirm the actual client's MCP transport and authorization requirements,
configure account linking and token acquisition/refresh, then deploy a HTTPS
endpoint with an explicit Host/Origin allowlist. Validate schema discovery and
read tools for two linked users before enabling capture. Integrate Person 2's
compiler with explicit clarification handling and the same authenticated
identity; reconcile ambiguous writes rather than retrying blindly.
