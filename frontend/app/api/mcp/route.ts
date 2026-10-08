import { actionSchema, errorMessages, toolNames, type McpMeta, type McpErrorCode, type McpAction } from '@/lib/mcp/contracts';
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
  if (input && typeof input === 'object' && 'action' in input && input.action === 'call_tool' && 'tool' in input && typeof input.tool === 'string' && !toolNames.includes(input.tool as typeof toolNames[number])) return fail('TOOL_NOT_FOUND', 404);
  const parsed = actionSchema.safeParse(input);
  if (!parsed.success) return fail('TOOL_VALIDATION_ERROR', 400);
  if (parsed.data.action === 'call_tool') meta.tool = parsed.data.tool;
  try {
    if (parsed.data.action === 'converse') {
      const input = parsed.data;
      const steps: McpMeta[] = [];
      const call = async (action: Exclude<McpAction, { action: 'converse' }>) => {
        const stepStarted = performance.now();
        const step: McpMeta = { ...meta, initialized: false, toolsDiscovered: false };
        const result = await executeMcp(action, authorization, step);
        step.durationMs = Math.round(performance.now() - stepStarted);
        steps.push(step);
        if (!('result' in result)) throw new McpFailure('MCP_PROTOCOL_ERROR', 502);
        return result.result.structuredContent;
      };
      const { compilationSchema } = await import('@/lib/mcp/contracts');
      const output = await call(input.state
        ? { action: 'call_tool', tool: 'continue_expectation_compilation', arguments: { request: { state: input.state, answer: input.text } } }
        : { action: 'call_tool', tool: 'compile_expectation', arguments: { request: { text: input.text, timezone: input.timezone, locale: input.locale, conversational: true, compilation_id: input.turn_id } } });
      const turn = compilationSchema.parse(output);
      if (turn.status === 'clarification' && !turn.state) throw new McpFailure('MCP_PROTOCOL_ERROR', 502);
      let saved: Record<string, unknown> | null = null;
      if (turn.status === 'compiled') {
        if (!turn.expectation || !turn.capture_state) throw new McpFailure('MCP_PROTOCOL_ERROR', 502);
        saved = await call({ action: 'call_tool', tool: 'capture_expectation', arguments: { request: { ...turn.expectation, compilation_state: turn.capture_state } } });
      }
      Object.assign(meta, steps.at(-1), { steps });
      // Capture tickets and compiled payloads stay on the trusted server.
      return reply({ result: { structuredContent: { status: turn.status, message: saved ? `Got it. I'll track: ${String(saved.claim)}` : turn.message, state: turn.status === 'clarification' ? turn.state : null, saved, bedrock_used: turn.bedrock_used, clarification_turn: turn.clarification_turn, code: turn.code } } });
    }
    const result = await executeMcp(parsed.data, authorization, meta);
    if ('result' in result && parsed.data.action === 'call_tool' && ['compile_expectation', 'continue_expectation_compilation', 'explain_expectation_mismatch'].includes(parsed.data.tool)) {
      const output = result.result.structuredContent;
      console.info(JSON.stringify({ event: 'counton_intelligence', request_id: meta.requestId, tool_called: meta.tool, bedrock_used: output.bedrock_used === true, bedrock_operation: meta.tool, compiler_result: ['compiled', 'clarification', 'cancelled', 'expired', 'unsupported', 'error'].includes(String(output.status)) ? output.status : undefined, clarification_turn: typeof output.clarification_turn === 'number' ? output.clarification_turn : undefined, investigator_used: meta.tool === 'explain_expectation_mismatch' && output.bedrock_used === true }));
    }
    return reply(result);
  }
  catch (error) { return error instanceof McpFailure ? fail(error.code, error.status) : fail('UNKNOWN', 500); }
}
