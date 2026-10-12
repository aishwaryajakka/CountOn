import { agentInputSchema, agentResponseSchema, agentErrors, type AgentErrorCode } from '@/lib/agent/contracts';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export const maxDuration = 180;
async function boundedText(body: ReadableStream<Uint8Array> | null, limit: number) {
  if (!body) throw new Error();
  const reader = body.getReader(); const decoder = new TextDecoder(); let text = ''; let bytes = 0;
  try {
    while (true) {
      const { value, done } = await reader.read(); if (done) break;
      bytes += value.byteLength; if (bytes > limit) { await reader.cancel(); throw new Error(); }
      text += decoder.decode(value, { stream: true });
    }
    return text + decoder.decode();
  } finally { reader.releaseLock(); }
}
export async function POST(request: Request) {
  const started = performance.now(); const requestId = crypto.randomUUID();
  const reply = (body: object, status = 200) => {
    // No headers, utterances, handles, upstream errors or provider data in logs.
    console.info(JSON.stringify({ event: 'counton_agent_request', request_id: requestId, status, duration_ms: Math.round(performance.now() - started) }));
    return Response.json(body, { status, headers: { 'Cache-Control': 'no-store' } });
  };
  const fail = (code: AgentErrorCode, status: number) => reply({ error: { code, message: agentErrors[code] } }, status);
  const authorization = request.headers.get('Authorization');
  if (!authorization || !/^Bearer [^\s,]+$/i.test(authorization)) return fail('AUTH_REQUIRED', 401);
  let input: unknown;
  try { input = JSON.parse(await boundedText(request.body, 12_000)); }
  catch { return fail('INVALID_REQUEST', 400); }
  const parsed = agentInputSchema.safeParse(input);
  if (!parsed.success) return fail('INVALID_REQUEST', 400);
  let endpoint: URL;
  try {
    const base = process.env.NEXT_PUBLIC_API_BASE_URL ?? (process.env.NODE_ENV !== 'production' ? 'http://localhost:8000' : '');
    endpoint = new URL('/api/v1/agent/converse', base);
    if (endpoint.username || endpoint.password || (process.env.NODE_ENV === 'production' && ['localhost', '127.0.0.1', '[::1]'].includes(endpoint.hostname)) || (endpoint.protocol !== 'https:' && !(process.env.NODE_ENV !== 'production' && endpoint.protocol === 'http:' && ['localhost', '127.0.0.1', '[::1]'].includes(endpoint.hostname)))) throw new Error();
  } catch { return fail('UNAVAILABLE', 503); }
  try {
    // FastAPI validates the Supabase JWT with the existing verifier before invoking
    // the orchestrator. Next does not create or accept any user identity itself.
    const upstream = await fetch(endpoint, { method: 'POST', headers: { Authorization: authorization, 'Content-Type': 'application/json', 'X-Request-ID': requestId, 'Accept-Language': request.headers.get('Accept-Language') ?? '' }, body: JSON.stringify(parsed.data), signal: AbortSignal.timeout(175_000), redirect: 'error', cache: 'no-store' });
    if (upstream.status === 401 || upstream.status === 403) return fail('AUTH_EXPIRED', 401);
    if (!upstream.ok) return fail(upstream.status >= 500 || upstream.status === 429 ? 'UNAVAILABLE' : 'INVALID_REQUEST', upstream.status >= 500 || upstream.status === 429 ? 503 : 400);
    const output = agentResponseSchema.safeParse(JSON.parse(await boundedText(upstream.body, 192_000)));
    if (!output.success) return fail('INVALID_RESPONSE', 502);
    if (output.data.code === 'UNAUTHORIZED') return fail('AUTH_EXPIRED', 401);
    return reply(output.data);
  } catch { return fail('UNAVAILABLE', 503); }
}
