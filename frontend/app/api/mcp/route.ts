import { errorMessages, type McpMeta, type McpErrorCode } from '@/lib/mcp/contracts';
import { executeMcp, McpFailure } from '@/lib/mcp/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 180;
export async function POST(request: Request) {
  const started = performance.now();
  const meta: McpMeta = { transport: 'streamable-http', initialized: false, toolsDiscovered: false, durationMs: 0, requestId: crypto.randomUUID() };
  const reply = (body: object, status = 200) => {
    meta.durationMs = Math.round(performance.now() - started);
    console.info(JSON.stringify({ event: 'counton_mcp_request', request_id: meta.requestId, mcp_initialized: meta.initialized, tools_discovered: meta.toolsDiscovered, tool_called: meta.tool, status, duration_ms: meta.durationMs }));
    return Response.json({ ...body, meta }, { status, headers: { 'Cache-Control': 'no-store' } });
  };
  const fail = (code: McpErrorCode, status: number) => reply({ error: { code, message: errorMessages[code] } }, status);
  const authorization = request.headers.get('Authorization');
  if (!authorization || !/^Bearer [^\s,]+$/i.test(authorization)) return fail('AUTH_REQUIRED', 401);
  let input: unknown;
  try {
    // Bound the stream as well as Content-Length; untrusted clients may omit it.
    const reader = request.body?.getReader();
    if (!reader) return fail('TOOL_VALIDATION_ERROR', 400);
    let text = ''; let bytes = 0;
    const decoder = new TextDecoder();
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        bytes += value.byteLength;
        if (bytes > 32_768) { await reader.cancel(); return fail('TOOL_VALIDATION_ERROR', 413); }
        text += decoder.decode(value, { stream: true });
      }
      input = JSON.parse(text + decoder.decode());
    } finally { reader.releaseLock(); }
  } catch { return fail('TOOL_VALIDATION_ERROR', 400); }
  // This browser surface is discovery-only. All CountOn actions go through the
  // authenticated orchestrator route; clients cannot select even approved tools.
  if (!input || typeof input !== 'object' || Object.keys(input).length !== 1 ||
      !('action' in input) || input.action !== 'list_tools') return fail('TOOL_VALIDATION_ERROR', 400);

  try {
    const result = await executeMcp({ action: 'list_tools' }, authorization, meta);
    return reply(result);
  }
  catch (error) { return error instanceof McpFailure ? fail(error.code, error.status) : fail('UNKNOWN', 500); }
}
