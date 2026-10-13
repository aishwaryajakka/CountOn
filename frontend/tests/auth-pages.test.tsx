import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ auth: { signUp: vi.fn(), resetPasswordForEmail: vi.fn(), updateUser: vi.fn(), getUser: vi.fn(), signInWithOAuth: vi.fn(), linkIdentity: vi.fn(), unlinkIdentity: vi.fn() }, replace: vi.fn(), session: null as { user: { id: string } } | null }));
vi.mock('@/lib/supabase', () => ({ getSupabase: () => ({ auth: mocks.auth }) }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ replace: mocks.replace }) }));
vi.mock('@/components/auth-provider', () => ({ useAuth: () => ({ session: mocks.session, loading: false, error: null }) }));
import Register from '@/app/register/page';
import Forgot from '@/app/forgot-password/page';
import Reset from '@/app/reset-password/page';
import { AmazonSignIn } from '@/components/amazon-sign-in';
import { AccountSecurity } from '@/components/account-security';
beforeEach(() => {
  vi.clearAllMocks(); mocks.session = null; vi.stubEnv('NEXT_PUBLIC_APP_URL', window.location.origin); vi.stubEnv('NEXT_PUBLIC_SUPABASE_URL', 'https://project.test'); vi.stubEnv('NEXT_PUBLIC_AMAZON_AUTH_ENABLED', 'false');
  mocks.auth.signUp.mockResolvedValue({ data: { session: null }, error: null }); mocks.auth.resetPasswordForEmail.mockResolvedValue({ error: null }); mocks.auth.updateUser.mockResolvedValue({ error: null });
  mocks.auth.getUser.mockResolvedValue({ data: { user: { id: 'owned-user', identities: [] } }, error: null });
});
afterEach(() => vi.unstubAllEnvs());
it('signup uses Supabase with an exact confirmation redirect and neutral duplicate feedback', async () => {
  render(<Register />); await userEvent.type(screen.getByLabelText('Email address'), 'owner@example.test'); await userEvent.type(screen.getByLabelText('Password'), 'fixture-password-123'); await userEvent.type(screen.getByLabelText('Confirm password'), 'fixture-password-123');
  await userEvent.click(screen.getByRole('button', { name: 'Create account' }));
  expect(mocks.auth.signUp).toHaveBeenCalledWith({ email: 'owner@example.test', password: 'fixture-password-123', options: { emailRedirectTo: window.location.origin + '/auth/callback?next=%2Fdashboard' } });
  expect(await screen.findByRole('status')).toHaveTextContent('Existing accounts are preserved'); expect(mocks.replace).not.toHaveBeenCalled();
});
it('recovery never reveals whether the email exists', async () => {
  render(<Forgot />); await userEvent.type(screen.getByLabelText('Email address'), 'owner@example.test'); await userEvent.click(screen.getByRole('button', { name: 'Send reset link' }));
  expect(mocks.auth.resetPasswordForEmail).toHaveBeenCalledWith('owner@example.test', { redirectTo: window.location.origin + '/auth/callback?next=%2Fdashboard' }); expect(await screen.findByRole('status')).toHaveTextContent('If this account');
});
it('password update revalidates session and remains in Supabase Auth', async () => {
  mocks.session = { user: { id: 'owned-user' } }; render(<Reset />); await userEvent.type(screen.getByLabelText('New password'), 'fixture-password-123'); await userEvent.type(screen.getByLabelText('Confirm password'), 'fixture-password-123'); await userEvent.click(screen.getByRole('button', { name: 'Update password' }));
  expect(mocks.auth.getUser).toHaveBeenCalledOnce(); expect(mocks.auth.updateUser).toHaveBeenCalledWith({ password: 'fixture-password-123' });
});
it('cross-user recovery does not dispatch a password update', async () => {
  mocks.session = { user: { id: 'other' } }; render(<Reset />); await userEvent.type(screen.getByLabelText('New password'), 'fixture-password-123'); await userEvent.type(screen.getByLabelText('Confirm password'), 'fixture-password-123'); await userEvent.click(screen.getByRole('button', { name: 'Update password' }));
  expect(mocks.auth.updateUser).not.toHaveBeenCalled(); expect(await screen.findByRole('status')).toHaveTextContent('expired');
});
it('unconfigured Amazon button does not claim success', () => {
  render(<AmazonSignIn />); expect(screen.getByRole('button', { name: 'Continue with Amazon' })).toBeDisabled();
});
it.each([false, true])('Amazon native flow link=%s uses minimal scope without injecting user_id', async link => {
  vi.stubEnv('NEXT_PUBLIC_AMAZON_AUTH_ENABLED', 'true'); mocks.auth.signInWithOAuth.mockResolvedValue({ data: { url: 'https://evil.test/private' }, error: null }); mocks.auth.linkIdentity.mockResolvedValue({ data: { url: 'https://evil.test/private' }, error: null });
  render(<AmazonSignIn link={link} />); await userEvent.click(screen.getByRole('button'));
  const method = link ? mocks.auth.linkIdentity : mocks.auth.signInWithOAuth;
  expect(method).toHaveBeenCalledWith({ provider: 'custom:amazon', options: { scopes: 'profile:user_id', skipBrowserRedirect: true, redirectTo: window.location.origin + `/auth/callback?next=${link ? '%2Fsettings&mode=link' : '%2Fdashboard'}` } });
  expect(await screen.findByRole('alert')).not.toHaveTextContent('evil.test');
});
it('cannot unlink the only login/recovery identity', async () => {
  mocks.auth.getUser.mockResolvedValue({ data: { user: { id: 'owned-user', identities: [{ id: 'amazon-sub', provider: 'custom:amazon' }] } }, error: null }); render(<AccountSecurity />);
  expect(await screen.findByRole('button', { name: 'Unlink Amazon' })).toBeDisabled(); expect(mocks.auth.unlinkIdentity).not.toHaveBeenCalled();
});
it('explicit unlink revalidates ownership and retains the account', async () => {
  const identity = { id: 'amazon-sub', provider: 'custom:amazon' };
  mocks.auth.getUser.mockResolvedValue({ data: { user: { id: 'owned-user', email_confirmed_at: '2026-10-13', identities: [identity, { provider: 'email' }] } }, error: null }); mocks.auth.unlinkIdentity.mockResolvedValue({ error: null }); vi.spyOn(window, 'confirm').mockReturnValue(true);
  render(<AccountSecurity />); await userEvent.click(await screen.findByRole('button', { name: 'Unlink Amazon' })); await waitFor(() => expect(mocks.auth.unlinkIdentity).toHaveBeenCalledWith(identity));
});
