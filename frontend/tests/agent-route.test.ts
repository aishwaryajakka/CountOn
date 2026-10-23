// @vitest-environment node
import { beforeEach, afterEach, expect, it, vi } from 'vitest';
import { POST } from '@/app/api/agent/route';
import { requestAgent } from '@/lib/agent/client';
const token = 'private-token-sentinel';
const handle = 'h'.repeat(43);
const output = { action: 'LIST_EXPECTATIONS', status: 'SUCCESS', answer: 'Here are your expectations.', code: null, session_reference: handle, captured: false, clarification_required: false, rows: [], saved_id: null, traces: [{ layer: 'Agent', label: 'LIST_EXPECTATIONS' }, { layer: 'MCP', label: 'list_expectations' }] };
const request = (body: unknown, auth: string | null = `Bearer ${token}`) => new Request('https://frontend.test/api/agent', { method: 'POST', headers: { 'Content-Type': 'application/json', 'Accept-Language': 'en-US', ...(auth ? { Authorization: auth } : {}) }, body: JSON.stringify(body) });
const fetcher = vi.fn();
beforeEach(() => { vi.resetAllMocks(); vi.stubEnv('NEXT_PUBLIC_API_BASE_URL', 'https://api.test'); vi.stubGlobal('fetch', fetcher); fetcher.mockResolvedValue(Response.json(output)); });
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); });
it('browser conversation has a deadline and masks timeout details without retries', async () => {
  const deadline = vi.spyOn(AbortSignal, 'timeout');
  fetcher.mockRejectedValue(new DOMException(`private ${token}`, 'TimeoutError'));
  await expect(requestAgent(token, { text: 'Hello', session_reference: null })).rejects.toMatchObject({ code: 'UNAVAILABLE' });
  expect(deadline).toHaveBeenCalledWith(185_000);
  expect(fetcher).toHaveBeenCalledOnce();
  expect(fetcher.mock.calls[0][1].signal).toBeInstanceOf(AbortSignal);
  deadline.mockRestore();
});
it('proxies only utterance/handle to the JWT-validated backend without redirects or caching', async () => { const response = await POST(request({ text: 'What am I counting on?', session_reference: null })); expect(response.status).toBe(200); expect(fetcher.mock.calls[0][0].href).toBe('https://api.test/api/v1/agent/converse'); expect(fetcher.mock.calls[0][1]).toMatchObject({ headers: { Authorization: `Bearer ${token}`, 'Accept-Language': 'en-US' }, body: '{"text":"What am I counting on?","session_reference":null}', redirect: 'error', cache: 'no-store' }); expect(response.headers.get('Cache-Control')).toBe('no-store'); expect(JSON.stringify(await response.json())).not.toContain(token); });
it.each([null, 'Basic secret', 'Bearer one two'])('rejects malformed/missing auth: %s', async auth => { expect((await POST(request({ text: 'Hello', session_reference: null }, auth))).status).toBe(401); expect(fetcher).not.toHaveBeenCalled(); });
it.each(['tool', 'user_id', 'action', 'plan', 'result', 'expectation_id', 'clarification_state', 'aws_credentials'])('rejects client %s injection before contacting backend', async field => { expect((await POST(request({ text: 'Hello', session_reference: null, [field]: 'injected-private' }))).status).toBe(400); expect(fetcher).not.toHaveBeenCalled(); });
it('bounds request bodies', async () => { expect((await POST(request({ text: 'x'.repeat(13000), session_reference: null }))).status).toBe(400); expect(fetcher).not.toHaveBeenCalled(); });
it.each([401, 403])('normalizes backend auth failure %s', async status => { fetcher.mockResolvedValue(Response.json({ error: { message: token } }, { status })); const response = await POST(request({ text: 'Hello', session_reference: null })); expect(response.status).toBe(401); expect(JSON.stringify(await response.json())).not.toContain(token); });
it('maps rejected MCP auth inside an execution result to re-auth', async () => { fetcher.mockResolvedValue(Response.json({ ...output, code: 'UNAUTHORIZED', status: 'FAILED' })); expect((await POST(request({ text: 'Hello', session_reference: null }))).status).toBe(401); });
it('never returns invalid upstream fields, traces or private metadata', async () => { for (const value of [{ ...output, jwt: token }, { ...output, traces: [{ layer: 'MCP', label: token }] }, { ...output, captured: true, saved_id: null }]) { fetcher.mockResolvedValue(Response.json(value)); const response = await POST(request({ text: 'Hello', session_reference: null })); expect(response.status).toBe(502); expect(JSON.stringify(await response.json())).not.toContain(token); } });
it('keeps credentials, utterances and handles out of logs', async () => { const logger = vi.spyOn(console, 'info').mockImplementation(() => {}); await POST(request({ text: 'private-utterance-sentinel', session_reference: handle })); expect(JSON.stringify(logger.mock.calls)).not.toMatch(/private-token-sentinel|private-utterance-sentinel|hhhhhhhh|Authorization/); logger.mockRestore(); });
it('blocks unsafe production backend configuration', async () => { vi.stubEnv('NODE_ENV', 'production'); vi.stubEnv('NEXT_PUBLIC_API_BASE_URL', 'http://localhost:8000'); expect((await POST(request({ text: 'Hello', session_reference: null }))).status).toBe(503); expect(fetcher).not.toHaveBeenCalled(); });
it('browser calls only the internal route and uses safe local errors', async () => { await requestAgent(token, { text: 'Hello', session_reference: handle }); expect(fetcher).toHaveBeenCalledWith('/api/agent', expect.objectContaining({ headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' }, body: JSON.stringify({ text: 'Hello', session_reference: handle }) })); fetcher.mockResolvedValue(Response.json({ message: token }, { status: 503 })); await expect(requestAgent(token, { text: 'Hello', session_reference: null })).rejects.toMatchObject({ code: 'UNAVAILABLE' }); await expect(requestAgent(undefined, { text: 'Hello', session_reference: null })).rejects.toMatchObject({ code: 'AUTH_REQUIRED' }); });

it('keeps orchestration and Supabase business mutations out of the browser page', async () => {
  const { readFile } = await import('node:fs/promises');
  const source = await readFile(new URL('../app/alexa/page.tsx', import.meta.url), 'utf8');
  expect(source).not.toMatch(/routeAlexaPrompt|matchExpectations|\.from\s*\(|call_tool|arguments:\s*\{|user_id\s*:/);
  expect(source).toContain('requestAgent(token,');
});

it('forwards only a typed expectation selection without treating it as an identity', async () => {
  const expectationId = 'b3767384-bd03-4bb8-a4ac-15e782e38802';
  const response = await POST(request({ text: 'Why did it fail?', session_reference: null, expectation_id: expectationId }));
  expect(response.status).toBe(200);
  expect(JSON.parse(fetcher.mock.calls[0][1].body as string)).toEqual({ text: 'Why did it fail?', session_reference: null, expectation_id: expectationId });
  expect(JSON.stringify(await response.json())).not.toContain(token);
});
