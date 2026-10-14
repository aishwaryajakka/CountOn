import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiError, createApiClient } from '@/lib/api';
import { expectation } from './fixtures';
describe('FastAPI client', () => {
  beforeEach(() => { vi.spyOn(console, 'warn').mockImplementation(() => {}); });
  it.each(['ftp://api.test', 'https://user:secret@api.test', 'https://api.test/path', 'https://api.test?key=private', 'https://api.test#fragment'])('rejects invalid API origins without echoing credentials', baseUrl => {
    expect(() => createApiClient({ token: async () => 'fixture', unauthorized: vi.fn(), baseUrl })).toThrow('must be an HTTP(S) origin');
  });
  it('bounds requests while preserving caller cancellation', async () => {
    const controller = new AbortController();
    const deadline = vi.spyOn(AbortSignal, 'timeout');
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response('[]'));
    const api = createApiClient({ token: async () => 'fixture', unauthorized: vi.fn(), fetcher });
    await api.expectations(controller.signal);
    expect(deadline).toHaveBeenCalledWith(20_000);
    const signal = fetcher.mock.calls[0][1]?.signal;
    expect(signal?.aborted).toBe(false);
    controller.abort();
    expect(signal?.aborted).toBe(true);
    deadline.mockRestore();
  });
  it('reports deadlines safely without retrying a possibly completed write', async () => {
    const fetcher = vi.fn<typeof fetch>().mockRejectedValue(new DOMException('private upstream detail', 'TimeoutError'));
    const api = createApiClient({ token: async () => 'private-token', unauthorized: vi.fn(), fetcher });
    await expect(api.request('/expectations', { method: 'POST', body: '{"claim":"private"}' })).rejects.toMatchObject({ status: 0 });
    expect(fetcher).toHaveBeenCalledOnce();
    expect(JSON.stringify(vi.mocked(console.warn).mock.calls)).not.toMatch(/private upstream|private-token/);
  });
  it('preserves explicit caller aborts', async () => {
    const aborted = new DOMException('Aborted', 'AbortError');
    const api = createApiClient({ token: async () => 'fixture', unauthorized: vi.fn(), fetcher: vi.fn<typeof fetch>().mockRejectedValue(aborted) });
    await expect(api.expectations()).rejects.toBe(aborted);
    expect(console.warn).not.toHaveBeenCalled();
  });
  it('logs network diagnostics without credentials, query values or upstream details', async () => {
    const api = createApiClient({ token: async () => 'private-token', unauthorized: vi.fn(), baseUrl: 'https://api.test', fetcher: vi.fn<typeof fetch>().mockRejectedValue(new TypeError('private provider detail')) });
    await expect(api.request('/expectations?private=value')).rejects.toMatchObject({ status: 0 });
    expect(console.warn).toHaveBeenCalledWith('CountOn API request failed', expect.objectContaining({ failure: 'network', status: 0, origin: 'https://api.test', route: '/api/v1/expectations', method: 'GET' }));
    const logged = JSON.stringify(vi.mocked(console.warn).mock.calls);
    expect(logged).not.toContain('private-token');
    expect(logged).not.toContain('private=value');
    expect(logged).not.toContain('private provider detail');
  });
  it('logs HTTP status and request reference without response or request payloads', async () => {
    const api = createApiClient({ token: async () => 'private-token', unauthorized: vi.fn(), fetcher: vi.fn<typeof fetch>().mockResolvedValue(new Response('{"error":{"message":"private SQL detail"}}', { status: 503, headers: { 'X-Request-ID': 'support-reference' } })) });
    await expect(api.request('/expectations', { method: 'POST', body: '{"claim":"private claim"}' })).rejects.toMatchObject({ status: 503 });
    expect(console.warn).toHaveBeenCalledWith('CountOn API request failed', expect.objectContaining({ failure: 'http', status: 503, requestId: 'support-reference', method: 'POST' }));
    const logged = JSON.stringify(vi.mocked(console.warn).mock.calls);
    expect(logged).not.toContain('private SQL detail');
    expect(logged).not.toContain('private claim');
    expect(logged).not.toContain('private-token');
  });
  it('explains rate limits without silently retrying requests', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response('{}', { status: 429 }));
    const api = createApiClient({ token: async () => 'fixture', unauthorized: vi.fn(), fetcher });
    await expect(api.expectations()).rejects.toMatchObject({ status: 429, message: 'Please wait a moment before trying again.' });
    expect(fetcher).toHaveBeenCalledOnce();
  });
  it('normalizes malformed successful responses without leaking parse errors', async () => {
    const api = createApiClient({ token: async () => 'fixture', unauthorized: vi.fn(), fetcher: vi.fn<typeof fetch>().mockResolvedValue(new Response('<html>private upstream details</html>', { headers: { 'X-Request-ID': 'parse-reference' } })) });
    await expect(api.expectations()).rejects.toMatchObject({ name: 'ApiError', message: 'We couldn’t read this response. Please try again.', requestId: 'parse-reference' });
  });
  it('hides upstream server details while preserving support references', async () => {
    const api = createApiClient({ token: async () => 'fixture', unauthorized: vi.fn(), fetcher: vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({ error: { message: 'internal SQL exception' } }), { status: 500, headers: { 'X-Request-ID': 'server-reference' } })) });
    await expect(api.expectations()).rejects.toMatchObject({ status: 500, message: 'CountOn is temporarily unavailable. Please try again.', requestId: 'server-reference' });
  });
  it('attaches Bearer auth and serializes the actual create contract', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify(expectation)));
    const api = createApiClient({ token: async () => 'fixture-token', unauthorized: vi.fn(), fetcher, baseUrl: 'http://api.test' });
    await api.createExpectation({ claim: 'A test claim', type: 'boolean', metric: 'confirmed', evidence_sources: [], materiality_threshold: .05 });
    const [url, options] = fetcher.mock.calls[0];
    expect(url).toBe('http://api.test/api/v1/expectations');
    expect(new Headers(options?.headers).get('Authorization')).toBe('Bearer fixture-token');
    expect(JSON.parse(String(options?.body))).not.toHaveProperty('user_id');
  });
  it('handles unauthorized responses and retains request references', async () => {
    const unauthorized = vi.fn(async () => {});
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({ error: { message: 'Session expired', request_id: 'reference-id' } }), { status: 401 }));
    const api = createApiClient({ token: async () => 'fixture', unauthorized, fetcher });
    await expect(api.expectations()).rejects.toMatchObject({ status: 401, requestId: 'reference-id' });
    expect(unauthorized).toHaveBeenCalledOnce();
  });
  it('does not fetch without a session', async () => {
    const fetcher = vi.fn<typeof fetch>();
    const api = createApiClient({ token: async () => null, unauthorized: vi.fn(), fetcher });
    await expect(api.expectations()).rejects.toBeInstanceOf(ApiError);
    expect(fetcher).not.toHaveBeenCalled();
  });
  it('paginates array responses instead of assuming an envelope', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(new Response(JSON.stringify(Array(100).fill(expectation)))).mockResolvedValueOnce(new Response(JSON.stringify([expectation])));
    const api = createApiClient({ token: async () => 'fixture', unauthorized: vi.fn(), fetcher });
    expect(await api.expectations()).toHaveLength(101);
    expect(fetcher.mock.calls[1][0]).toContain('offset=100');
  });
  it('treats an absent latest evaluation as a normal unevaluated state', async () => {
    const api = createApiClient({ token: async () => 'fixture', unauthorized: vi.fn(), fetcher: vi.fn<typeof fetch>().mockResolvedValue(new Response('{}', { status: 404 })) });
    expect(await api.latest(expectation.id)).toBeNull();
  });
  it('sends only the supported dismissal field', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response('{}'));
    const api = createApiClient({ token: async () => 'fixture', unauthorized: vi.fn(), fetcher });
    await api.updateNotification('notification-id', 'dismissed');
    expect(JSON.parse(String(fetcher.mock.calls[0][1]?.body))).toEqual({ status: 'dismissed' });
  });
  it('serializes owner-scoped audit filters without a caller-supplied user id', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response('[]'));
    const api = createApiClient({ token: async () => 'fixture', unauthorized: vi.fn(), fetcher });
    await api.auditEvents({
      expectationId: expectation.id,
      source: 'RING',
      result: 'MATCH',
      after: '2026-10-01T00:00:00Z',
      before: '2026-10-14T00:00:00Z',
    });
    const url = String(fetcher.mock.calls[0][0]);
    expect(url).toContain(`expectation_id=${expectation.id}`);
    expect(url).toContain('source_provider=RING');
    expect(url).toContain('result_status=MATCH');
    expect(url).toContain('occurred_after=2026-10-01T00%3A00%3A00Z');
    expect(url).toContain('occurred_before=2026-10-14T00%3A00%3A00Z');
    expect(url).not.toContain('user_id');
  });
  it('reads a bounded history for unevaluated board rows without routine 404s', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(new Response(JSON.stringify([expectation]))).mockResolvedValueOnce(new Response('[]'));
    const api = createApiClient({ token: async () => 'fixture', unauthorized: vi.fn(), fetcher });
    expect(await api.board()).toEqual([{ expectation, latest: null }]);
    expect(fetcher.mock.calls[1][0]).toContain('/evaluations?limit=1');
  });
});

it.each(['ring', 'bee'] as const)('submits authorized %s simulator evidence and idempotent evaluation', async kind => {
  const { generateRingEvent, ringEventToEvidence, generateBeeEvent, beeEventToEvidence } = await import('@/lib/simulators');
  const payload = kind === 'ring' ? ringEventToEvidence(generateRingEvent('package_not_detected')) : beeEventToEvidence(generateBeeEvent({ summary: 'SIMULATED cancellation', confirmed: false }));
  const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => new Response('{}'));
  const client = createApiClient({ token: async () => 'fixture-token', unauthorized: vi.fn(), fetcher, baseUrl: 'https://api.test' });
  await client.addEvidence(expectation.id, payload);
  await client.evaluate(expectation.id, `simulation:${payload.external_event_id}`);
  const [url, options] = fetcher.mock.calls[0];
  expect(url).toBe(`https://api.test/api/v1/expectations/${expectation.id}/evidence`);
  expect(new Headers(options?.headers).get('Authorization')).toBe('Bearer fixture-token');
  expect(JSON.parse(String(options?.body))).toMatchObject({ source: `${kind}_simulator`, raw_data: { simulated: true } });
  expect(JSON.parse(String(options?.body))).not.toHaveProperty('user_id');
  expect(new Headers(fetcher.mock.calls[1][1]?.headers).get('Idempotency-Key')).toBe(`simulation:${payload.external_event_id}`);
});

it.each(['ring', 'bee'] as const)('submits dedicated %s simulator route evidence', async kind => {
  const { generateRingEvent, generateBeeEvent } = await import('@/lib/simulators');
  const payload = kind === 'ring' ? generateRingEvent('package_not_detected') : generateBeeEvent({ summary: 'SIMULATED cancellation', confirmed: false });
  const fetcher = vi.fn<typeof fetch>().mockImplementation(async () => new Response('{}'));
  const client = createApiClient({ token: async () => 'fixture-token', unauthorized: vi.fn(), fetcher, baseUrl: 'https://api.test' });
  if (kind === 'ring') await client.simulateRing(expectation.id, payload as ReturnType<typeof generateRingEvent>);
  else await client.simulateBee(expectation.id, payload as ReturnType<typeof generateBeeEvent>);
  const [url, options] = fetcher.mock.calls[0];
  expect(url).toBe(`https://api.test/api/v1/simulators/${kind}/expectations/${expectation.id}/events`);
  expect(new Headers(options?.headers).get('Authorization')).toBe('Bearer fixture-token');
  expect(JSON.parse(String(options?.body))).toMatchObject({ simulated: true });
  expect(JSON.parse(String(options?.body))).not.toHaveProperty('user_id');
  expect(fetcher).toHaveBeenCalledOnce();
});
