# Frontend MCP client

The browser calls the Node-runtime Next.js `POST /api/mcp` route. That route
uses the official `@modelcontextprotocol/client` **2.x** SDK (resolved version in `frontend/package-lock.json`) and
`StreamableHTTPClientTransport` to initialize, discover tools, and call the
existing Python MCP service. It does not call FastAPI expectation CRUD.
Normal dashboard requests continue to use FastAPI.

## Configuration and startup

Add the following **server-side** variable to `frontend/.env.local` and the
Vercel project's Production environment, then rebuild/redeploy:

```env
COUNTON_MCP_URL=https://counton-mcp.7ak6j8v4ypay0.us-east-2.cs.amazonlightsail.com/mcp
```

Do not prefix it with `NEXT_PUBLIC_`. Never configure a shared MCP access token.
The existing Supabase public variables remain required for browser login.

```sh
cd frontend
npm install
npm run build
npm start
```

## Auth and calling conventions

Use the current `useAuth().session.access_token`, passing it at call time:

```tsx
import { requestMcp } from '@/lib/mcp/client';
import { useAuth } from '@/components/auth-provider';

// Inside an authenticated component/event handler:
const { session } = useAuth();
const tools = await requestMcp(session?.access_token, { action: 'list_tools' });
const expectations = await requestMcp(session?.access_token, {
  action: 'call_tool',
  tool: 'list_expectations',
  arguments: { request: { limit: 50, offset: 0 } },
});
```

The helper sends `Authorization: Bearer <access_token>` to the internal route;
the route forwards the same header to MCP. No server cookies, stored tokens,
shared user identity, or second JWT implementation is added. Python MCP continues
to validate the token and enforce ownership. Connections are isolated per HTTP
request and closed afterward. Calls are not automatically retried.

The route permits `capture_expectation`, `get_expectation`, `list_expectations`,
`compile_expectation`, `continue_expectation_compilation`, and
`explain_expectation_mismatch`. Each call has **exactly one** tool argument, `request`:

```json
{"action":"call_tool","tool":"get_expectation","arguments":{"request":{"expectation_id":"<uuid>"}}}
```

```json
{"action":"call_tool","tool":"capture_expectation","arguments":{"request":{"claim":"My next electricity bill will be lower","type":"numeric_comparison","metric":"total_cost","comparison":"less_than","baseline":142.1,"evidence_sources":["utility_bill"],"materiality_threshold":0.05}}}
```

For conversation, `/alexa` sends `{action:"converse", text, state, turn_id,
timezone, locale}` to this internal route. It calls compile/continue over MCP,
then capture once only for COMPILED, including the returned `capture_state` as
`compilation_state`. The route keeps compiled payloads/capture tickets server-side
and returns only the safe turn result, nullable active state and saved compact row.
The backend ledger enforces user binding, consumed handles and atomic capture
replay protection. Direct structured capture without a ticket is not idempotent.
Never retry a write blindly. All actual MCP calls still use nested `request`.

Unknown tools, extra identity fields, flattened arguments and invalid inputs are
rejected. The route bounds bodies to 32 KiB, uses a 180-second MCP request budget,
disables caching, and refuses upstream redirects to avoid forwarding bearer
tokens to another destination. HTTPS is required in production; HTTP localhost
is supported only outside production. The authenticated `/alexa` simulator uses this helper for tools; normal dashboard
data uses `lib/api.ts`. See [the conversation guide](alexa-demo.md).

## Responses and failures

Discovery returns `{ tools: [...], meta }`, including discovered names,
descriptions, input schemas, and output schemas. Calls return
`{ result: { structuredContent: {...} }, meta }`. List structured content includes
`expectations`, `limit`, and `offset`; capture/get include the compact expectation
fields defined by the existing MCP server.

```json
{"meta":{"transport":"streamable-http","initialized":true,"toolsDiscovered":true,"tool":"list_expectations","durationMs":123}}
```

Errors return `{ error: { code, message }, meta }`. Safe codes are
`AUTH_REQUIRED`, `AUTH_EXPIRED`, `MCP_UNAVAILABLE`, `MCP_PROTOCOL_ERROR`,
`TOOL_NOT_FOUND`, `TOOL_VALIDATION_ERROR`, `TOOL_EXECUTION_ERROR`, and `UNKNOWN`.
Intelligence responses also carry safe compiler/clarification/Bedrock/fallback
codes. Their typed responses, provenance and outcome gates are documented in
[Bedrock integration](../../docs/bedrock-integration.md#mcp-surface).
A tool's `NOT_FOUND` for nonexistent/inaccessible IDs maps to `NO_EXPECTATION`;
other execution failures map to `TOOL_EXECUTION_ERROR`.
Route error messages are fixed and omit stack traces/raw upstream errors.
Successful intelligence responses use validated, user-facing compiler/explanation
messages rather than raw model drafts.
The browser helper exposes UI-friendly `McpClientError.code` and `.message`.
Do not log tokens, request headers, or sensitive results in simulator UI code.

## Tests and manual verification

```sh
npm run lint
npm run typecheck
npm test
npm run build
```

The default suite mocks the SDK for security/contract cases. The opt-in live test
uses the actual SDK and remote server through the route handler, only when both
`COUNTON_MCP_URL` and `COUNTON_MCP_TEST_ACCESS_TOKEN` are explicitly set in the
test process environment. Supply a fresh dedicated test-user access token through
a secure local mechanism, never in source or shell history. Then run:

```sh
npx vitest run tests/mcp-live.test.ts
```

The live test is read-only: it discovers tools, lists expectations, and fetches
the first owned expectation if one exists. It never creates or deletes rows.
Normal tests cover capture/continuation/Why contracts without production writes.
The explicitly configured `tests/alexa-live.mjs` browser test creates a uniquely
tagged capture, verifies shared persistence and cleans up only that exact row.

To verify the actual browser → HTTP route path, sign in normally and, from
the existing `/alexa` page, call discovery, list, then get an ID from
the list. Confirm `initialized` and `toolsDiscovered` are true. Alternatively,
in DevTools on that signed-in page (keep the token local):

```js
const authKey = Object.keys(localStorage).find(k => /^sb-.*-auth-token$/.test(k));
const accessToken = JSON.parse(localStorage.getItem(authKey)).access_token;
const call = async body => {
  const response = await fetch('/api/mcp', {
    method: 'POST', headers: {
      'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}`,
    }, body: JSON.stringify(body),
  });
  return response.json();
};
const discovery = await call({ action: 'list_tools' });
const listed = await call({ action: 'call_tool', tool: 'list_expectations',
  arguments: { request: { limit: 50, offset: 0 } } });
const id = listed.result.structuredContent.expectations[0]?.id;
if (id) await call({ action: 'call_tool', tool: 'get_expectation',
  arguments: { request: { expectation_id: id } } });
```

Inspect only safe metadata; do not copy tokens or private records into chat.
An unauthenticated POST should return `401/AUTH_REQUIRED`; a rejected token should
return `401/AUTH_EXPIRED`. Browser requests target `/api/mcp`, not the public
FastAPI origin or MCP directly, so no browser-to-MCP CORS change is required.

Run these commands against the current checkout; historical core-tool acceptance
is not certification of the latest intelligence deployment. Require discovery of
all six tools plus live compiler/clarification/explanation checks before declaring
production intelligence ready. No real Alexa/Echo runtime integration is claimed.
