// Node-only adapter, imported by the route handler, never by browser helpers.
import { Client, StreamableHTTPClientTransport, ProtocolError, UnauthorizedError } from '@modelcontextprotocol/client';
import { z } from 'zod';
import { compilationSchema, explanationSchema, errorMessages, toolNames, type McpAction, type McpErrorCode, type McpMeta, type McpResponse } from './contracts';

export class McpFailure extends Error {
  constructor(public code: McpErrorCode, public status: number) { super(errorMessages[code]); }
}
export async function executeMcp(action: Exclude<McpAction, { action: 'converse' }>, authorization: string, meta: McpMeta): Promise<McpResponse> {
  const configured = process.env.COUNTON_MCP_URL;
  if (!configured) throw new McpFailure('MCP_UNAVAILABLE', 503);
  let endpoint: URL;
  try {
    endpoint = new URL(configured);
    if (endpoint.username || endpoint.password || endpoint.hash || endpoint.search ||
        (endpoint.protocol !== 'https:' && !(process.env.NODE_ENV !== 'production' && endpoint.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(endpoint.hostname)))) throw new Error();
  } catch { throw new McpFailure('MCP_UNAVAILABLE', 503); }
  const signal = AbortSignal.timeout(180_000);
  const client = new Client({ name: 'counton-frontend', version: '1.0.0' });
  const transport = new StreamableHTTPClientTransport(endpoint, {
    requestInit: { headers: { Authorization: authorization, 'X-Request-ID': meta.requestId ?? crypto.randomUUID() }, redirect: 'error', cache: 'no-store' },
    fetch: async (input, init) => {
      let response: Response;
      try { response = await fetch(input, { ...init, signal: AbortSignal.any([signal, ...(init?.signal ? [init.signal] : [])]) }); }
      catch { throw new McpFailure('MCP_UNAVAILABLE', 503); }
      if (response.status === 401 || response.status === 403) throw new McpFailure('AUTH_EXPIRED', 401);
      if (response.status >= 500 || response.status === 429) throw new McpFailure('MCP_UNAVAILABLE', 503);
      return response;
    },
  });
  try {
    // connect performs the actual legacy initialize handshake used by Python MCP.
    await client.connect(transport, { signal, timeout: 180_000 });
    meta.initialized = true;
    const discovered = await client.listTools(undefined, { signal, timeout: 180_000 });
    meta.toolsDiscovered = true;
    const tools = discovered.tools.filter(tool => toolNames.includes(tool.name as typeof toolNames[number]));
    if (action.action === 'list_tools') return { tools: tools.map(({ name, description, inputSchema, outputSchema }) => ({ name, description, inputSchema, outputSchema })), meta };
    if (!tools.some(tool => tool.name === action.tool)) throw new McpFailure('TOOL_NOT_FOUND', 404);
    const result = await client.callTool({ name: action.tool, arguments: action.arguments }, { signal, timeout: 180_000 });
    if (result.isError) {
      const text = result.content.filter(block => block.type === 'text').map(block => block.text).join('\n');
      // Match only known error codes; never forward upstream error content.
      if (/\bUNAUTHORIZED:/.test(text)) throw new McpFailure('AUTH_EXPIRED', 401);
      if (/\b(INVALID_ARGUMENTS|INVALID_EXPECTATION):/.test(text)) throw new McpFailure('TOOL_VALIDATION_ERROR', 422);
      if (/\bNOT_FOUND:/.test(text)) throw new McpFailure('NO_EXPECTATION', 404);
      for (const code of ['CLARIFICATION_EXPIRED', 'CLARIFICATION_UNAVAILABLE', 'TOOL_VALIDATION_ERROR'] as const) {
        if (new RegExp(`\\b${code}:`).test(text)) throw new McpFailure(code, 422);
      }
      throw new McpFailure('TOOL_EXECUTION_ERROR', 422);
    }
    const output = z.record(z.string(), z.unknown()).safeParse(result.structuredContent);
    if (!output.success) throw new McpFailure('MCP_PROTOCOL_ERROR', 502);
    if (action.tool === 'compile_expectation' || action.tool === 'continue_expectation_compilation') {
      if (!compilationSchema.safeParse(output.data).success) throw new McpFailure('MCP_PROTOCOL_ERROR', 502);
    } else if (action.tool === 'explain_expectation_mismatch') {
      if (!explanationSchema.safeParse(output.data).success) throw new McpFailure('MCP_PROTOCOL_ERROR', 502);
    }
    return { result: { structuredContent: output.data }, meta };
  } catch (error) {
    if (error instanceof McpFailure) throw error;
    if (error instanceof UnauthorizedError) throw new McpFailure('AUTH_EXPIRED', 401);
    if (error instanceof ProtocolError && error.code === -32602) throw new McpFailure('TOOL_VALIDATION_ERROR', 422);
    throw new McpFailure('MCP_PROTOCOL_ERROR', 502);
  } finally {
    await client.close().catch(() => {});
  }
}
