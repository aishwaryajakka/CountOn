import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { NextRequest } from 'next/server';
import { authMessage, safeAuthNext, supabaseConfig } from '@/lib/auth/config';
const mocks = vi.hoisted(() => ({ exchange: vi.fn(), user: vi.fn(), writes: [] as { name: string; value: string; options: object }[] }));
vi.mock('@supabase/ssr', () => ({ createServerClient: (_url: string, _key: string, options: { cookies: { setAll: (cookies: typeof mocks.writes) => void } }) => ({ auth: { getUser: mocks.user, exchangeCodeForSession: (...args: unknown[]) => { options.cookies.setAll(mocks.writes); return mocks.exchange(...args); } } }) }));
import { GET } from '@/app/auth/callback/route';
import { proxy } from '@/proxy';
const user = { id: '10000000-0000-4000-8000-000000000001', aud: 'authenticated', is_anonymous: false };
const callback = (query = 'code=fixture-code') => new NextRequest('https://counton.test/auth/callback?' + query);
beforeEach(() => {
  vi.clearAllMocks(); mocks.writes = [{ name: 'sb-fixture', value: 'fixture-session', options: { path: '/' } }];
  vi.stubEnv('NEXT_PUBLIC_APP_URL', 'https://counton.test'); vi.stubEnv('NEXT_PUBLIC_SUPABASE_URL', 'https://project.test'); vi.stubEnv('NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY', 'sb_publishable_fixture');
  mocks.exchange.mockResolvedValue({ data: { session: { user, access_token: 'fixture-session-token' }, user, redirectType: null }, error: null });
  mocks.user.mockResolvedValue({ data: { user }, error: null });
});
afterEach(() => vi.unstubAllEnvs());
it('exchanges once, revalidates identity and returns only cookie redirect', async () => {
  const result = await GET(callback());
  expect(mocks.exchange).toHaveBeenCalledExactlyOnceWith('fixture-code', undefined);
  expect(mocks.user).toHaveBeenCalledOnce();
  expect(result.headers.get('location')).toBe('https://counton.test/dashboard');
  expect(result.cookies.get('sb-fixture')?.value).toBe('fixture-session');
  expect(result.headers.get('cache-control')).toContain('no-store');
  expect(await result.text()).not.toContain('fixture-session');
});
it.each(['state=invalid', 'access_token=private', 'code=one&code=two', 'code=one&user_id=other', 'code=one&provider=amazon', 'error=denied&error_description=private'])('rejects malformed callback %s before exchange', async query => {
  const result = await GET(callback(query));
  expect(result.headers.get('location')).toBe('https://counton.test/login?auth_error=callback');
  expect(mocks.exchange).not.toHaveBeenCalled(); expect(result.cookies.get('sb-fixture')).toBeUndefined();
});
it('never redirects to arbitrary sites or trusts a query recovery flag', async () => {
  for (const next of ['https://evil.test', '//evil.test', '/reset-password']) expect((await GET(callback('code=fixture&next=' + encodeURIComponent(next)))).headers.get('location')).toBe('https://counton.test/dashboard');
});
it('recognizes recovery only from SDK PKCE storage', async () => {
  mocks.exchange.mockResolvedValue({ data: { session: { user, access_token: 'fixture-session-token' }, user, redirectType: 'recovery' }, error: null });
  expect((await GET(callback())).headers.get('location')).toBe('https://counton.test/reset-password');
});
it.each([{ session: null, user: null }, { session: {}, user: null }, { session: {}, user: {} }])('rejects unusable token responses %j', async data => {
  mocks.exchange.mockResolvedValue({ data, error: null });
  expect((await GET(callback())).headers.get('location')).toContain('auth_error=callback');
});
it('replay and expiry never expose upstream errors or new cookies', async () => {
  await GET(callback());
  mocks.exchange.mockResolvedValue({ data: { session: null, user: null }, error: { message: 'private-token-detail' } });
  const response = await GET(callback());
  expect(response.headers.get('location')).toContain('auth_error=callback'); expect(response.cookies.get('sb-fixture')).toBeUndefined();
  expect(await response.text()).not.toContain('private-token-detail');
});
it('explicit linking preserves the already authenticated user', async () => {
  const response = await GET(callback('code=fixture&mode=link&next=/settings'));
  expect(mocks.user).toHaveBeenCalledTimes(2); expect(response.headers.get('location')).toBe('https://counton.test/settings');
});
it('cross-user linking fails without handing out another session', async () => {
  mocks.user.mockResolvedValueOnce({ data: { user }, error: null }).mockResolvedValueOnce({ data: { user: { ...user, id: 'other' } }, error: null });
  const response = await GET(callback('code=fixture&mode=link'));
  expect(response.headers.get('location')).toContain('auth_error=callback'); expect(response.cookies.get('sb-fixture')).toBeUndefined();
});
it('requires a current session before linking', async () => {
  mocks.user.mockResolvedValue({ data: { user: null }, error: null }); await GET(callback('code=fixture&mode=link')); expect(mocks.exchange).not.toHaveBeenCalled();
});
it('does not trust a forged SSR cookie', async () => {
  mocks.user.mockResolvedValue({ data: { user: null }, error: { message: 'Invalid signature' } });
  const response = await proxy(new NextRequest('https://counton.test/expectations', { headers: { cookie: 'sb-fixture=forged' } }));
  expect(response.headers.get('location')).toBe('https://counton.test/login?next=%2Fexpectations');
});
it('preserves Alexa consent routing while verifying server identity', async () => {
  const request = new NextRequest('https://counton.test/oauth/consent?authorization_id=12345678901234567890');
  expect((await proxy(request)).headers.get('location')).toBeNull(); mocks.user.mockResolvedValue({ data: { user: null }, error: null });
  expect((await proxy(request)).headers.get('location')).toContain('authorization_id');
});
it('does not reflect a forged host in auth callback redirects', async () => {
  expect((await GET(new NextRequest('https://evil.test/auth/callback?code=fixture'))).headers.get('location')).toBe('https://counton.test/dashboard');
});
it('rejects privileged keys without printing them', () => {
  vi.stubEnv('NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY', 'sb_secret_private-fixture'); expect(() => supabaseConfig()).toThrow('never a privileged key');
});
it('normalizes rate limits, verification feedback and unsafe next paths', () => {
  expect(authMessage({ status: 429 }, 'fallback')).toContain('Too many attempts'); expect(authMessage({ code: 'email_not_confirmed' }, 'fallback')).toContain('Confirm your email');
  expect(safeAuthNext('//evil.test')).toBe('/dashboard');
});

it('supabase server failures never authenticate a protected page', async () => {
  mocks.user.mockRejectedValue(new Error('private provider detail'));
  const response = await proxy(new NextRequest('https://counton.test/alexa'));
  expect(response.headers.get('location')).toContain('/login');
  expect(await response.text()).not.toContain('private');
});
