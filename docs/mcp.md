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
DATABASE_TARGET=local python -m app.mcp
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
Every `/mcp` HTTP request, including initialization and discovery, now requires
bearer authentication. Missing/invalid credentials return HTTP 401 without
`WWW-Authenticate`, matching Amazon's current MCP discovery checklist. Health
and readiness remain public. After authentication, tool failures are MCP
`isError: true` results carried by HTTP 200; check both HTTP status and `isError`.

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
nonzero. The local script accepts only loopback URLs without credentials/query/fragment.
The separate remote script accepts HTTPS endpoints, as documented below.

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

Local service behavior is verified. Actual public deployment, OAuth resource metadata
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


## Remote Deployment

Configuration uses the existing `Settings` and ignored `backend/.env.local`.
No `MCP_ENVIRONMENT` is introduced: use existing `ENVIRONMENT`.

| Variable | Use |
| --- | --- |
| `MCP_HOST` | Internal bind interface; defaults to `127.0.0.1`, use `0.0.0.0` in a container |
| `MCP_PORT` | Internal port, 1–65535; default `8003` |
| `MCP_PUBLIC_URL` | Canonical external resource URL, exactly `https://<host>/mcp`; required to start production MCP |
| `MCP_ALLOWED_ORIGINS` | JSON list of explicit browser origins; default `[]`, no browser CORS enabled; production entries must be remote HTTPS |
| `ENVIRONMENT` | `development`, `test`, or `production`; inherited from CountOn |
| `DATABASE_TARGET` / `SUPABASE_DATABASE_URL` | Production uses `supabase` and existing SSL-required PostgreSQL configuration |
| `SUPABASE_URL` / `SUPABASE_PUBLISHABLE_KEY` | Existing project issuer/JWKS and Auth configuration |
| `ALLOWED_ORIGINS` | Existing global production configuration requires explicit HTTPS API/frontend origins; separate from optional MCP browser origins |

Configure real values through deployment environment/secrets, not Git.
`MCP_PUBLIC_URL` is public metadata, not a token. Production validation rejects
insecure/loopback public URLs, wildcard origins, and credential-bearing URLs.
The public URL's authority supplies the SDK's exact Host allowlist; no localhost
exception is added for the public MCP route. Origin-less server clients work;
if a browser sends Origin, it must match `MCP_ALLOWED_ORIGINS`.

Local start from backend: `DATABASE_TARGET=local python -m app.mcp`.
Production start, with required settings already provisioned:

```bash
ENVIRONMENT=production DATABASE_TARGET=supabase MCP_HOST=0.0.0.0 python -m app.mcp
```

Routes remain `/mcp`, `/health`, `/ready`. Debug is off. TLS belongs at the load
balancer/reverse proxy/platform; no Python certificate handling is added.
Preserve the canonical Host and Authorization headers, forward the `/mcp` path
without rewriting it, and permit MCP POST/GET/DELETE and content types. Keep the
internal port private; set edge timeouts/body limits and rate controls for your
platform. Forwarded headers are not trusted by this startup command. Configure
browser origins only when a browser client is actually required.

The existing backend Docker image can run MCP by overriding its command to
`python -m app.mcp` and setting `MCP_HOST=0.0.0.0`, with port publishing at your
edge. Its existing `.dockerignore` excludes `.env*`; inject environment at
runtime. The default image command remains FastAPI; there is no new
infrastructure stack. Image build and public deployment are not part of this pass.

Every authenticated request uses the existing JWT verifier; no fallback is
added. Auth outcomes (`authenticated`, `unauthorized`, `unavailable`) are logged
with request ID, safe user ID, and duration. Verified request identity is passed
to tools, avoiding duplicate JWT verification. Do not log OAuth secrets, raw
claims, bearer headers, or provider payloads.

### Remote smoke and discovery

From backend, set `MCP_PUBLIC_URL` and optionally `COUNTON_API_URL` in the
process environment. Supply `COUNTON_TEST_ACCESS_TOKEN` securely in that
environment, or use the hidden token prompt. Do not put tokens in CLI flags.

```bash
python db/scripts/mcp_remote_smoke.py --discovery-only
python db/scripts/mcp_remote_smoke.py
```

Endpoint overrides: `--mcp-url https://<host>/mcp` and
`--api-url https://<api-host>`. HTTPS certificate verification remains enabled.
Discovery initializes the current SDK client and reports missing/unexpected
tools against exactly the three core names. Without an API URL the second
command is a **read-only probe**, and explicitly reports capture/get/cross-check
and cleanup as NOT RUN. No orphan test rows are created.

With a matching API URL, it runs list → tagged capture → list/get → FastAPI
cross-check and owner-scoped exact-tag cleanup, including missing/invalid auth
and malformed input checks. Both services must use the same database and
accept the same user token. Cleanup failures exit nonzero; normal audit history
is retained. No second user identity or token exchange is fabricated.

Public-host initialization, discovery, Host/Origin rejection, and signed JWT
behavior are tested without live Alexa+. Local network smoke remains available
with `mcp_smoke.py`; its `--discovery-only` mode is non-mutating. A real public
HTTPS smoke cannot be reported as passed until a deployed URL/token is supplied.

### Account-linking boundary and current gap

Intended identity flow: Alexa+ user → CountOn account link → existing
Supabase user session → accepted JWT → MCP HTTP request → verified CountOn
user → existing ownership-filtered services. Alexa-supplied profile/user IDs
are never identities. Future OAuth tokens must satisfy current issuer/audience/
role validation or use an explicitly designed, validated session exchange.

Amazon's [MCP quickstart](https://www.developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-quickstart.html)
requires remote Streamable HTTP, HTTP 401 without a challenge header, protected
resource metadata, authorization-server metadata with S256, authorization-code
PKCE, and canonical `resource` handling. This pass supplies remote host config
and the 401 bearer boundary. It does **not** publish fake PRM/OAuth endpoints.
The resource hook is `MCP_PUBLIC_URL`; the identity hook is existing
`auth.authenticated_user_from_header` and the trusted HTTP request state.

Authorization/consent/code/token/refresh endpoints, static Alexa client
registration, approved redirects, PRM contents, scopes, and real account linking
are **NOT IMPLEMENTED**. Supabase sign-in alone does not prove these OAuth
requirements are met. There is no Alexa add-on ID or client configuration in
this repository. The deployment is therefore **not connected to Alexa+**.

Next action: provision the HTTPS endpoint and compatible OAuth authorization
server, then register the Alexa client and all provided redirects. Once metadata
is genuinely available, follow Amazon's
[account-linking guide](https://www.developer.amazon.com/docs/alexaplus/add-ons/mcp-toolkit-account-linking.html)
and run `alexa-ai configure-account-linking --addon-id <id> --stage development --client-id <id>`.
Enter any client secret through its masked prompt. Configure only with actual
issued IDs; test two linked users before enabling customer writes.

Validation on 2026-10-06: **309 backend tests passed**, dependency and syntax
checks passed, real-token local smoke (including exact-tag cleanup) passed, and
separate authenticated discovery passed. Configured public Host/Origin behavior
was verified in tests. Live remote HTTPS smoke and Alexa+ linking were **NOT
RUN**: no deployed public endpoint or actual OAuth client configuration was
provided. No backend lint/type check is configured. Tools, service/repository
logic, evaluators, and migrations were not changed by this pass.
