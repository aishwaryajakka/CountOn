// @vitest-environment node
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
const sdk = vi.hoisted(() => ({ connect: vi.fn(), listTools: vi.fn(), callTool: vi.fn(), close: vi.fn(), transport: vi.fn() }));
vi.mock('@modelcontextprotocol/client', async importOriginal => {
  const original = await importOriginal<typeof import('@modelcontextprotocol/client')>();
  return { ...original, Client: class { connect = sdk.connect; listTools = sdk.listTools; callTool = sdk.callTool; close = sdk.close; }, StreamableHTTPClientTransport: class { constructor(...args: unknown[]) { sdk.transport(...args); } } };
});
import { POST } from '@/app/api/mcp/route';
import { requestMcp } from '@/lib/mcp/client';
const token = 'private-test-token';
const toolList = ['capture_expectation', 'get_expectation', 'list_expectations', 'compile_expectation', 'continue_expectation_compilation', 'explain_expectation_mismatch'].map(name => ({ name, description: name, inputSchema: { type: 'object' } }));
const request = (body: unknown, authorization: string | null = `Bearer ${token}`) => new Request('http://localhost/api/mcp', { method: 'POST', headers: { 'Content-Type': 'application/json', ...(authorization ? { Authorization: authorization } : {}) }, body: JSON.stringify(body) });
describe('MCP route and browser helper', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.stubEnv('COUNTON_MCP_URL', 'https://mcp.test/mcp');
    sdk.connect.mockResolvedValue(undefined); sdk.close.mockResolvedValue(undefined);
    sdk.listTools.mockResolvedValue({ tools: [...toolList, { name: 'unknown_tool', inputSchema: {} }] });
    sdk.callTool.mockResolvedValue({ content: [], structuredContent: { id: 'expectation-id' } });
  });
  afterEach(() => { vi.unstubAllEnvs(); vi.unstubAllGlobals(); });
  it('rejects missing or malformed authorization without opening MCP', async () => {
    for (const authorization of [null, 'Basic private', 'Bearer one two']) {
      const response = await POST(request({ action: 'list_tools' }, authorization));
      expect(response.status).toBe(401); expect((await response.json()).error.code).toBe('AUTH_REQUIRED');
    }
    expect(sdk.connect).not.toHaveBeenCalled();
  });
  it('rejects malformed JSON and unsupported actions', async () => {
    const malformed = new Request('http://localhost/api/mcp', { method: 'POST', headers: { Authorization: `Bearer ${token}` }, body: '{' });
    expect((await POST(malformed)).status).toBe(400);
    expect((await POST(request({ action: 'anything' }))).status).toBe(400);
    expect(sdk.connect).not.toHaveBeenCalled();
  });
  it('bounds oversized bodies', async () => {
    expect((await POST(request({ action: 'list_tools', padding: 'x'.repeat(33_000) }))).status).toBe(413);
    expect(sdk.connect).not.toHaveBeenCalled();
  });
  it('rejects unknown tools and extra user identity or flattened arguments', async () => {
    const unknown = await POST(request({ action: 'call_tool', tool: 'delete_everything', arguments: { request: {} } }));
    expect(unknown.status).toBe(404); expect((await unknown.json()).error.code).toBe('TOOL_NOT_FOUND');
    for (const args of [{ limit: 50 }, { request: {}, user_id: 'private' }, { request: { user_id: 'private' } }, { request: { limit: 101 } }]) {
      expect((await POST(request({ action: 'call_tool', tool: 'list_expectations', arguments: args }))).status).toBe(400);
    }
    expect(sdk.callTool).not.toHaveBeenCalled();
  });
  it('initializes and discovers only allowed tools while forwarding bearer auth', async () => {
    const response = await POST(request({ action: 'list_tools' })); const body = await response.json();
    expect(response.status).toBe(200); expect(body.tools.map((t: { name: string }) => t.name)).toEqual(toolList.map(t => t.name));
    expect(body.meta).toMatchObject({ transport: 'streamable-http', initialized: true, toolsDiscovered: true });
    expect(sdk.connect).toHaveBeenCalledOnce(); expect(sdk.listTools).toHaveBeenCalledOnce();
    expect(sdk.transport.mock.calls[0][1].requestInit).toMatchObject({ headers: { Authorization: `Bearer ${token}` }, redirect: 'error', cache: 'no-store' });
    expect(response.headers.get('Cache-Control')).toBe('no-store'); expect(JSON.stringify(body)).not.toContain(token);
    expect(sdk.close).toHaveBeenCalledOnce();
  });
  it.each([
    ['list_expectations', { limit: 50, offset: 0 }],
    ['get_expectation', { expectation_id: '12345678-1234-4234-8234-123456789abc' }],
    ['capture_expectation', { claim: 'Tagged test claim', type: 'boolean', evidence_sources: [] }],
  ])('calls %s with exactly one nested request argument', async (tool, input) => {
    const response = await POST(request({ action: 'call_tool', tool, arguments: { request: input } }));
    expect(response.status).toBe(200);
    expect(sdk.callTool).toHaveBeenCalledWith({ name: tool, arguments: { request: input } }, expect.objectContaining({ signal: expect.any(AbortSignal) }));
    const body = await response.json(); expect(body.meta.tool).toBe(tool); expect(body.result.structuredContent.id).toBe('expectation-id');
    expect(JSON.stringify(body)).not.toContain(token);
  });
  it('rejects tools absent from discovery', async () => {
    sdk.listTools.mockResolvedValue({ tools: [] });
    const response = await POST(request({ action: 'call_tool', tool: 'list_expectations', arguments: { request: {} } }));
    expect((await response.json()).error.code).toBe('TOOL_NOT_FOUND'); expect(sdk.callTool).not.toHaveBeenCalled();
  });
  it('sanitizes thrown upstream failures and closes the client', async () => {
    sdk.connect.mockRejectedValue(new Error(`private stack ${token} postgresql://private`));
    const response = await POST(request({ action: 'list_tools' })); const body = await response.json();
    expect(body.error.code).toBe('MCP_PROTOCOL_ERROR'); expect(body.meta.initialized).toBe(false);
    expect(JSON.stringify(body)).not.toMatch(/private|postgresql/); expect(sdk.close).toHaveBeenCalledOnce();
  });
  it.each([['UNAUTHORIZED', 'AUTH_EXPIRED'], ['INVALID_ARGUMENTS', 'TOOL_VALIDATION_ERROR'], ['INVALID_EXPECTATION', 'TOOL_VALIDATION_ERROR'], ['NOT_FOUND', 'NO_EXPECTATION'], ['DATABASE_ERROR', 'TOOL_EXECUTION_ERROR']])('normalizes %s tool errors', async (upstream, expected) => {
    sdk.callTool.mockResolvedValue({ isError: true, content: [{ type: 'text', text: `${upstream}: private ${token}` }] });
    const response = await POST(request({ action: 'call_tool', tool: 'list_expectations', arguments: { request: {} } }));
    const body = await response.json(); expect(body.error.code).toBe(expected); expect(JSON.stringify(body)).not.toContain(token);
  });
  it('normalizes HTTP auth and network failures in the SDK transport', async () => {
    await POST(request({ action: 'list_tools' }));
    const transportFetch = sdk.transport.mock.calls[0][1].fetch;
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response('', { status: 401 })));
    await expect(transportFetch('https://mcp.test/mcp', {})).rejects.toMatchObject({ code: 'AUTH_EXPIRED' });
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error(`private ${token}`)));
    await expect(transportFetch('https://mcp.test/mcp', {})).rejects.toMatchObject({ code: 'MCP_UNAVAILABLE' });
  });
  it('fails safely when server configuration is missing', async () => {
    vi.stubEnv('COUNTON_MCP_URL', ''); const response = await POST(request({ action: 'list_tools' }));
    expect(response.status).toBe(503); expect(sdk.connect).not.toHaveBeenCalled();
  });
  it('browser helper calls only the internal route with the supplied session token', async () => {
    const fetcher = vi.fn().mockResolvedValue(Response.json({ tools: toolList, meta: { initialized: true } }));
    vi.stubGlobal('fetch', fetcher);
    await requestMcp(token, { action: 'list_tools' });
    expect(fetcher).toHaveBeenCalledWith('/api/mcp', expect.objectContaining({ headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: '{"action":"list_tools"}' }));
    await expect(requestMcp(undefined, { action: 'list_tools' })).rejects.toMatchObject({ code: 'AUTH_REQUIRED' });
  });
  it('browser helper uses safe local error messages', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(Response.json({ error: { code: 'MCP_UNAVAILABLE', message: `private ${token}` } }, { status: 503 })));
    await expect(requestMcp(token, { action: 'list_tools' })).rejects.toMatchObject({ code: 'MCP_UNAVAILABLE', message: 'CountOn tools are temporarily unavailable. Try again later.' });
  });

  it('forwards compiler and continuation over real SDK-shaped nested requests, and logs no secrets', async () => {
    const logger = vi.spyOn(console, 'info').mockImplementation(() => {});
    try {
      sdk.callTool.mockResolvedValue({ content: [], structuredContent: { status: 'clarification', message: 'Which bill?', expectation: null, state: 'signed-private-state', code: 'CLARIFICATION_REQUIRED', bedrock_used: true, prompt_version: 'v2', clarification_turn: 0 } });
      const response = await POST(request({ action: 'call_tool', tool: 'compile_expectation', arguments: { request: { text: 'My bill lower', timezone: 'UTC', locale: 'en-US' } } }));
      expect(response.status).toBe(200);
      expect(sdk.callTool.mock.calls[0][0]).toEqual({ name: 'compile_expectation', arguments: { request: { text: 'My bill lower', timezone: 'UTC', locale: 'en-US' } } });
      const body = await response.json();
      expect(body.result.structuredContent.state).toBe('signed-private-state');
      expect(body.meta.requestId).toBeTruthy();
      const continuation = await POST(request({ action: 'call_tool', tool: 'continue_expectation_compilation', arguments: { request: { state: 'signed-private-state', answer: 'Electricity bill' } } }));
      expect(continuation.status).toBe(200);
      expect(JSON.stringify(logger.mock.calls)).not.toMatch(/private-test-token|signed-private-state|My bill lower|Authorization/);
      expect(JSON.stringify(body)).not.toContain(token);
    } finally { logger.mockRestore(); }
  });
  it('rejects unrecognized compiler output fields instead of forwarding a leaked credential', async () => {
    sdk.callTool.mockResolvedValue({ content: [], structuredContent: { status: 'error', message: 'No interpretation', state: null, expectation: null, code: 'BEDROCK_UNAVAILABLE', bedrock_used: false, prompt_version: 'v2', clarification_turn: 0, jwt: token } });
    const response = await POST(request({ action: 'call_tool', tool: 'compile_expectation', arguments: { request: { text: 'My bill lower', timezone: 'UTC' } } }));
    const body = await response.json();
    expect(body.error.code).toBe('MCP_PROTOCOL_ERROR');
    expect(JSON.stringify(body)).not.toContain(token);
  });
});

it('trusted conversation compiles then captures once with nested arguments and hides ticket', async () => {
  vi.stubEnv('COUNTON_MCP_URL', 'https://mcp.test/mcp');
  sdk.connect.mockResolvedValue(undefined); sdk.close.mockResolvedValue(undefined);
  sdk.listTools.mockResolvedValue({ tools: toolList });
  const expectation = { claim: 'My grocery bill under $120 this week', type: 'numeric_comparison', metric: 'total_cost', comparison: 'less_than', target_value: 120 };
  sdk.callTool.mockReset().mockResolvedValueOnce({ content: [], structuredContent: { status: 'compiled', message: 'Ready', expectation, state: null, capture_state: 'private-capture-ticket', bedrock_used: true, prompt_version: 'v2', clarification_turn: 0 } }).mockResolvedValueOnce({ content: [], structuredContent: { id: '12345678-1234-4234-8234-123456789abc', claim: expectation.claim } });
  const result = await POST(request({ action: 'converse', text: "I'm counting on my grocery bill under $120 this week", state: null, turn_id: '12345678-1234-4234-8234-123456789abc', timezone: 'America/Chicago', locale: 'en-US' }));
  const body = await result.json();
  expect(result.status).toBe(200);
  expect(sdk.callTool.mock.calls.map(([call]) => call.name)).toEqual(['compile_expectation', 'capture_expectation']);
  expect(sdk.callTool.mock.calls[1][0].arguments).toEqual({ request: { ...expectation, compilation_state: 'private-capture-ticket' } });
  expect(JSON.stringify(body)).not.toContain('private-capture-ticket');
  expect(JSON.stringify(body)).not.toContain(token);
  expect(body.result.structuredContent.state).toBeNull();
  vi.unstubAllEnvs();
});

it.each(['clarification', 'cancelled', 'expired', 'unsupported', 'error'])('never captures conversation outcome %s', async status => {
  vi.stubEnv('COUNTON_MCP_URL', 'https://mcp.test/mcp');
  sdk.connect.mockResolvedValue(undefined); sdk.close.mockResolvedValue(undefined);
  sdk.listTools.mockResolvedValue({ tools: toolList });
  sdk.callTool.mockReset().mockResolvedValue({ content: [], structuredContent: { status, message: 'One safe question or response', expectation: null, state: status === 'clarification' ? 'signed-state' : null, bedrock_used: false, prompt_version: 'v2', clarification_turn: 1 } });
  const result = await POST(request({ action: 'converse', text: 'Never mind', state: 'previous-signed-state', turn_id: '12345678-1234-4234-8234-123456789abc', timezone: 'America/Chicago', locale: 'en-US' }));
  expect(result.status).toBe(200);
  expect(sdk.callTool).toHaveBeenCalledOnce();
  expect(sdk.callTool.mock.calls[0][0]).toMatchObject({ name: 'continue_expectation_compilation', arguments: { request: { state: 'previous-signed-state', answer: 'Never mind' } } });
  vi.unstubAllEnvs();
});
