import { describe, expect, it, vi } from 'vitest';
import { ApiError, createApiClient } from '@/lib/api';
import { expectation } from './fixtures';
describe('FastAPI client', () => {
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
  it('reads a bounded history for unevaluated board rows without routine 404s', async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(new Response(JSON.stringify([expectation]))).mockResolvedValueOnce(new Response('[]'));
    const api = createApiClient({ token: async () => 'fixture', unauthorized: vi.fn(), fetcher });
    expect(await api.board()).toEqual([{ expectation, latest: null }]);
    expect(fetcher.mock.calls[1][0]).toContain('/evaluations?limit=1');
  });
});
