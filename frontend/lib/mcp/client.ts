import { errorMessages, type McpAction, type McpResponse, type McpErrorCode } from './contracts';

export class McpClientError extends Error {
  constructor(public code: McpErrorCode) { super(errorMessages[code]); }
}
// Pass useAuth().session.access_token at call time; no cookies or stored tokens.
export async function requestMcp(accessToken: string | undefined, action: McpAction): Promise<McpResponse> {
  if (!accessToken) throw new McpClientError('AUTH_REQUIRED');
  let response: Response;
  try {
    response = await fetch('/api/mcp', { method: 'POST', headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' }, body: JSON.stringify(action), cache: 'no-store' });
  } catch { throw new McpClientError('MCP_UNAVAILABLE'); }
  let body: McpResponse;
  try { body = await response.json(); } catch { throw new McpClientError('MCP_PROTOCOL_ERROR'); }
  if (!body || typeof body !== 'object') throw new McpClientError('MCP_PROTOCOL_ERROR');
  if ('error' in body) {
    const code = Object.hasOwn(errorMessages, body.error?.code) ? body.error.code : 'UNKNOWN';
    throw new McpClientError(code);
  }
  if (!response.ok || !body.meta || (!('tools' in body) && !('result' in body))) throw new McpClientError('MCP_PROTOCOL_ERROR');
  return body;
}
