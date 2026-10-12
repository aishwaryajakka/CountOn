# MCP and orchestrator client boundaries

`/alexa` uses `lib/agent/client.ts` to send only text and an opaque session handle
to `/api/agent`, with the current Supabase bearer token. The trusted Next.js proxy
forwards to the configured FastAPI `/api/v1/agent/converse`; existing backend JWT
verification establishes identity before orchestration. No service-role key or AWS
credential is used by the frontend.

The Python orchestrator selects only its static approved capabilities. Its
request-scoped adapter calls the configured MCP service using the real SDK over
Streamable HTTP, with exactly `{"request": {...}}`. Six tools remain registered:
`capture_expectation`, `get_expectation`, `list_expectations`,
`compile_expectation`, `continue_expectation_compilation`, and
`explain_expectation_mismatch`. Deterministic evaluation remains authoritative.

`lib/mcp/server.ts` and `/api/mcp` retain actual SDK initialization/tools discovery
for connection readiness. `/api/mcp` is **discovery-only**; direct `call_tool`,
legacy `converse`, user IDs, extra arguments and arbitrary tools are rejected.
Existing Python MCP tools remain available to authenticated external MCP clients.

Input/output Zod schemas reject arbitrary plans, tool names, identities, evaluator
results, raw compiler state and unexpected response fields. The public projection
contains approved speech, compact records, a capture link ID, closed safe trace
labels and the rotated opaque handle. Internal prompts, compiler payloads/tickets,
evidence/evaluation provenance and credentials are not exposed. Logs contain only
safe request correlation/status/duration. Redirects and automatic write retries
are disabled. Network-loss messages ask users to check CountOn before resaving.

Frontend: configure the existing public API/Supabase variables and server-only
`COUNTON_MCP_URL` for discovery. Backend: configure `MCP_PUBLIC_URL` for actual
calls and the same `COUNTON_CLARIFICATION_SIGNING_KEY` on API and MCP. Session
state is bounded and fixed-TTL: memory for development, encrypted PostgreSQL for
production. Browser localStorage never stores conversation state. Apply current
Alembic head and configure the private conversation key before rollout. API and frontend redeploys are needed to publish this path.
See [the demo guide](alexa-demo.md) and
[backend orchestrator](../../backend/app/agent/README.md).
