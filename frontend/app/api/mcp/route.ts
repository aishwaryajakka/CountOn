import { actionSchema, errorMessages, toolNames, type McpMeta, type McpErrorCode } from '@/lib/mcp/contracts';
import { executeMcp, McpFailure } from '@/lib/mcp/server';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export async function POST(request: Request) {
  const started = performance.now();
  const meta: McpMeta = { transport: 'streamable-http', initialized: false, toolsDiscovered: false, durationMs: 0 };
  const reply = (body: object, status = 200) => {
    meta.durationMs = Math.round(performance.now() - started);
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
  if (input && typeof input === 'object' && 'action' in input && input.action === 'call_tool' && 'tool' in input && typeof input.tool === 'string' && !toolNames.includes(input.tool as typeof toolNames[number])) return fail('TOOL_NOT_FOUND', 404);
  const parsed = actionSchema.safeParse(input);
  if (!parsed.success) return fail('TOOL_VALIDATION_ERROR', 400);
  if (parsed.data.action === 'call_tool') meta.tool = parsed.data.tool;
  try { return reply(await executeMcp(parsed.data, authorization, meta)); }
  catch (error) { return error instanceof McpFailure ? fail(error.code, error.status) : fail('UNKNOWN', 500); }
}
