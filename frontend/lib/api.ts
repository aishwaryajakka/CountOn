import { getSupabase } from './supabase';
import type { Evidence, Evaluation, Expectation, ExpectationCreate, Integration, Notification, WatchedExpectation } from './types';

export class ApiError extends Error {
  constructor(message: string, public status: number, public requestId?: string) { super(message); this.name = 'ApiError'; }
}
type Dependencies = { token: () => Promise<string | null>; unauthorized: () => Promise<void>; fetcher?: typeof fetch; baseUrl?: string };
export function createApiClient(deps: Dependencies) {
  const configured = deps.baseUrl ?? process.env.NEXT_PUBLIC_API_BASE_URL;
  const base = (configured ?? (process.env.NODE_ENV === 'production' ? '' : 'http://localhost:8000')).replace(/\/$/, '');
  if (!base) throw new Error('Configure NEXT_PUBLIC_API_BASE_URL before building the production frontend.');
  if (process.env.NODE_ENV === 'production') {
    const url = new URL(base);
    if (url.protocol !== 'https:' || ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) {
      throw new Error('Production NEXT_PUBLIC_API_BASE_URL must point to the public HTTPS API.');
    }
  }
  async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
    const token = await deps.token();
    if (!token) { await deps.unauthorized(); throw new ApiError('Your session has ended. Please sign in again.', 401); }
    const headers = new Headers(options.headers);
    headers.set('Authorization', `Bearer ${token}`);
    if (options.body) headers.set('Content-Type', 'application/json');
    const started = performance.now();
    const logFailure = (failure: 'network' | 'http' | 'response', status: number, requestId?: string) => {
      // Keep credentials, query values, request bodies and upstream errors out of logs.
      console.warn('CountOn API request failed', {
        failure, status, requestId, method: options.method ?? 'GET',
        origin: new URL(base).origin,
        route: `/api/v1${path.split('?')[0]}`.replace(/[0-9a-f]{8}-[0-9a-f-]{27}/gi, ':id'),
        durationMs: Math.round(performance.now() - started),
      });
    };
    let response: Response;
    try { response = await (deps.fetcher ?? fetch)(`${base}/api/v1${path}`, { ...options, headers, cache: 'no-store' }); }
    catch (error) {
      if (error instanceof Error && error.name === 'AbortError') throw error;
      logFailure('network', 0);
      throw new ApiError('We couldn’t reach CountOn. Check your connection and try again.', 0);
    }
    if (!response.ok) {
      if (response.status === 401) await deps.unauthorized();
      const body: unknown = await response.json().catch(() => null);
      const envelope = body && typeof body === 'object' && 'error' in body ? body.error : null;
      const message = response.status === 429 ? 'Please wait a moment before trying again.' : response.status >= 500 ? 'CountOn is temporarily unavailable. Please try again.' : envelope && typeof envelope === 'object' && 'message' in envelope && typeof envelope.message === 'string' ? envelope.message : 'Something went wrong. Please try again.';
      const id = response.headers.get('X-Request-ID') ?? (envelope && typeof envelope === 'object' && 'request_id' in envelope && typeof envelope.request_id === 'string' ? envelope.request_id : undefined);
      logFailure('http', response.status, id);
      throw new ApiError(message, response.status, id);
    }
    if (response.status === 204) return undefined as T;
    try { return await response.json() as T; }
    catch {
      const id = response.headers.get('X-Request-ID') ?? undefined;
      logFailure('response', response.status, id);
      throw new ApiError('We couldn’t read this response. Please try again.', response.status, id);
    }
  }
  // FastAPI returns arrays, with limit/offset rather than a pagination envelope.
  async function all<T>(path: string, signal?: AbortSignal): Promise<T[]> {
    const rows: T[] = [];
    for (let offset = 0; offset < 5000; offset += 100) {
      const page = await request<T[]>(`${path}${path.includes('?') ? '&' : '?'}limit=100&offset=${offset}`, { signal });
      rows.push(...page);
      if (page.length < 100) return rows;
    }
    throw new ApiError('This view is too large to load at once. Please contact the team for a paginated view.', 0);
  }
  const latest = async (id: string, signal?: AbortSignal) => {
    try { return await request<Evaluation>(`/expectations/${encodeURIComponent(id)}/evaluations/latest`, { signal }); }
    catch (error) { if (error instanceof ApiError && error.status === 404) return null; throw error; }
  };
  return {
    request,
    expectations: (signal?: AbortSignal) => all<Expectation>('/expectations', signal),
    expectation: (id: string, signal?: AbortSignal) => request<Expectation>(`/expectations/${encodeURIComponent(id)}`, { signal }),
    evidence: (id: string, signal?: AbortSignal) => all<Evidence>(`/expectations/${encodeURIComponent(id)}/evidence`, signal),
    evaluations: (id: string, signal?: AbortSignal) => all<Evaluation>(`/expectations/${encodeURIComponent(id)}/evaluations`, signal),
    latest,
    createExpectation: (payload: ExpectationCreate) => request<Expectation>('/expectations', { method: 'POST', body: JSON.stringify(payload) }),
    notifications: (signal?: AbortSignal) => all<Notification>('/notifications', signal),
    updateNotification: (id: string, status: 'read' | 'dismissed') => request<Notification>(`/notifications/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify({ status }) }),
    integrations: (signal?: AbortSignal) => all<Integration>('/integrations', signal),
    async board(signal?: AbortSignal): Promise<WatchedExpectation[]> {
      const expectations = await all<Expectation>('/expectations', signal);
      const rows: WatchedExpectation[] = [];
      // Limit concurrent latest-evaluation requests instead of flooding FastAPI.
      for (let index = 0; index < expectations.length; index += 4) {
        rows.push(...await Promise.all(expectations.slice(index, index + 4).map(async expectation => {
          // An empty history is normal for new expectations, avoiding routine
          // 404 requests from the /latest endpoint during ordinary navigation.
          const history = await request<Evaluation[]>(`/expectations/${encodeURIComponent(expectation.id)}/evaluations?limit=1`, { signal });
          return { expectation, latest: history[0] ?? null };
        })));
      }
      return rows;
    },
  };
}
export const api = createApiClient({
  token: async () => { const { data, error } = await getSupabase().auth.getSession(); if (error) return null; return data.session?.access_token ?? null; },
  unauthorized: async () => { await getSupabase().auth.signOut({ scope: 'local' }); },
});
