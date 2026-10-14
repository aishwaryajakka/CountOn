import { expect, it } from 'vitest';
import { createBrowserClient } from '@supabase/ssr';
import { amazonAuthorizationUrl } from '@/lib/auth/config';

it('real Supabase SDK builds custom OAuth authorization with cookie-backed PKCE', async () => {
  let cookies: { name: string; value: string }[] = [];
  const client = createBrowserClient('https://project.test', 'sb_publishable_fixture', {
    isSingleton: false, auth: { detectSessionInUrl: false },
    cookies: { getAll: () => cookies, setAll: changes => { cookies = changes; } },
  });
  const result = await client.auth.signInWithOAuth({ provider: 'custom:amazon', options: { scopes: 'profile:user_id', skipBrowserRedirect: true, redirectTo: 'https://counton.test/auth/callback' } });
  expect(result.error).toBeNull();
  if (!result.data.url) throw new Error('No authorization URL');
  const url = new URL(result.data.url);
  expect(url.origin).toBe('https://project.test'); expect(url.searchParams.get('provider')).toBe('custom:amazon');
  expect(url.searchParams.has('code_challenge')).toBe(true);
  expect(cookies.some(cookie => cookie.name.includes('code-verifier'))).toBe(true);
  expect(amazonAuthorizationUrl(url.href, 'https://project.test', false)).toBe(url.href);
  client.auth.stopAutoRefresh();
});
it('accepts the actual direct Amazon code URL returned for explicit linking only', () => {
  const url = new URL('https://www.amazon.com/ap/oa');
  const params = { response_type: 'code', scope: 'profile:user_id', redirect_uri: 'https://project.test/auth/v1/callback', code_challenge_method: 'S256', code_challenge: 'a'.repeat(43), state: 'supabase-signed-state', client_id: 'fixture-client' };
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, value);
  expect(amazonAuthorizationUrl(url.href, 'https://project.test', true)).toBe(url.href);
  for (const [key, value] of [['response_type', 'token'], ['scope', 'profile postal_code'], ['redirect_uri', 'https://evil.test'], ['code_challenge_method', 'plain'], ['state', '']]) {
    const invalid = new URL(url); invalid.searchParams.set(key, value);
    expect(() => amazonAuthorizationUrl(invalid.href, 'https://project.test', true)).toThrow();
  }
});
