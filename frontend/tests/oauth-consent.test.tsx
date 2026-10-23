import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { authorizationId, consentReturnPath, safeAlexaRedirect } from '@/lib/oauth-consent';
const id = '11111111-2222-3333-4444-555555555555';
const redirect = 'https://alexa.amazon.com/api/skill/link/example';
const mocks = vi.hoisted(() => ({ getUser: vi.fn(), details: vi.fn(), approve: vi.fn(), deny: vi.fn(), replace: vi.fn(), router: {} as { replace?: unknown }, session: { user: { id: 'owned-user' } } as { user: { id: string } } | null }));
vi.mock('@/components/auth-provider', () => ({ useAuth: () => ({ session: mocks.session, loading: false }) }));
vi.mock('@/lib/supabase', () => ({ getSupabase: () => ({ auth: { getUser: mocks.getUser, oauth: { getAuthorizationDetails: mocks.details, approveAuthorization: mocks.approve, denyAuthorization: mocks.deny } } }) }));
vi.mock('next/navigation', () => ({ useRouter: () => mocks.router, useSearchParams: () => new URLSearchParams('authorization_id=' + id) }));
import ConsentPage from '@/app/oauth/consent/page';
function details(changes = {}) { return { authorization_id: id, redirect_uri: redirect, client: { id: 'configured-client', name: 'Alexa' }, user: { id: 'owned-user', email: 'owner@example.test' }, scope: 'openid email profile', ...changes }; }
beforeEach(() => {
  vi.clearAllMocks(); mocks.router = { replace: mocks.replace }; mocks.session = { user: { id: 'owned-user' } };
  vi.stubEnv('NEXT_PUBLIC_ALEXA_OAUTH_CLIENT_ID', 'configured-client');
  vi.stubEnv('NEXT_PUBLIC_ALEXA_REDIRECT_URIS', redirect);
  mocks.getUser.mockResolvedValue({ data: { user: mocks.session.user }, error: null });
  mocks.details.mockResolvedValue({ data: details(), error: null });
  // No navigation/network in isolated tests; prove explicit consent dispatch.
  mocks.approve.mockResolvedValue({ data: null, error: { message: 'Unavailable' } });
  mocks.deny.mockResolvedValue({ data: null, error: { message: 'Unavailable' } });
});
afterEach(() => vi.unstubAllEnvs());
it('preserves only an exact consent return path, never an arbitrary redirect', () => {
  expect(consentReturnPath('/oauth/consent?authorization_id=' + id)).toContain(id);
  for (const input of ['https://evil.example/oauth/consent?authorization_id=' + id, '//evil.example', '/oauth/consent?authorization_id=' + id + '&authorization_id=' + id, '/dashboard', '/oauth/consent?authorization_id=bad']) expect(consentReturnPath(input)).toBe('/dashboard');
  expect(() => authorizationId('bad')).toThrow();
});
it('allows only registered HTTPS code callbacks, never credentials or tokens', () => {
  expect(safeAlexaRedirect(redirect + '?code=fixture-code&state=original', [redirect])).toContain('state=original');
  for (const value of ['http://alexa.amazon.com/api/skill/link/example', redirect + '?access_token=private', redirect + '?refresh_token=private', redirect + '?code=one&code=two', redirect + '#fragment', 'https://attacker.example/callback?code=fixture', 'https://user:password@alexa.amazon.com/api/skill/link/example']) expect(() => safeAlexaRedirect(value, [redirect])).toThrow();
});
it('requires explicit consent and re-verifies identity before approving', async () => {
  render(<ConsentPage />);
  const allow = await screen.findByRole('button', { name: 'Allow Alexa' });
  expect(mocks.approve).not.toHaveBeenCalled();
  fireEvent.click(allow);
  await waitFor(() => expect(mocks.approve).toHaveBeenCalledWith(id, { skipBrowserRedirect: true }));
  expect(mocks.getUser).toHaveBeenCalledTimes(2);
  expect(mocks.deny).not.toHaveBeenCalled();
});
it('supports explicit denial', async () => {
  render(<ConsentPage />); fireEvent.click(await screen.findByRole('button', { name: 'Deny' }));
  await waitFor(() => expect(mocks.deny).toHaveBeenCalledWith(id, { skipBrowserRedirect: true }));
  expect(mocks.approve).not.toHaveBeenCalled();
});
it.each([
  { client: { id: 'foreign-client' } }, { user: { id: 'other-user' } },
  { scope: 'openid unexpected-permission' }, { redirect_uri: 'https://attacker.example/callback' }, { authorization_id: 'not-this-request' },
])('rejects untrusted authorization details %j', async changes => {
  mocks.details.mockResolvedValue({ data: details(changes), error: null });
  render(<ConsentPage />); expect(await screen.findByRole('alert')).toHaveTextContent('invalid');
  expect(screen.queryByRole('button', { name: 'Allow Alexa' })).not.toBeInTheDocument();
  expect(mocks.approve).not.toHaveBeenCalled();
});
it('preserves native OAuth authorization ID through existing login', async () => {
  mocks.session = null; render(<ConsentPage />);
  await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith('/login?next=' + encodeURIComponent('/oauth/consent?authorization_id=' + id)));
  expect(mocks.details).not.toHaveBeenCalled();
});
it('blocks expired or changed identity during approval', async () => {
  render(<ConsentPage />); const allow = await screen.findByRole('button', { name: 'Allow Alexa' });
  mocks.getUser.mockResolvedValue({ data: { user: { id: 'other-user' } }, error: null });
  fireEvent.click(allow); expect(await screen.findByRole('alert')).toHaveTextContent('could not complete');
  expect(mocks.approve).not.toHaveBeenCalled();
});
