import { act, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
import type { Session } from '@supabase/supabase-js';
const mocks = vi.hoisted(() => ({ getSession: vi.fn(), subscribe: vi.fn(), unsubscribe: vi.fn() }));
vi.mock('@/lib/supabase', () => ({ getSupabase: () => ({ auth: { getSession: mocks.getSession, onAuthStateChange: mocks.subscribe } }) }));
import { AuthProvider, useAuth } from '@/components/auth-provider';
const session = { access_token: 'fixture', user: { id: 'fixture-user', email: 'user@example.test' } } as Session;
function Consumer() { const auth = useAuth(); return <div>{auth.loading ? 'Restoring session' : auth.session?.user.email ?? 'Signed out'}</div>; }
beforeEach(() => { vi.clearAllMocks(); mocks.subscribe.mockReturnValue({ data: { subscription: { unsubscribe: mocks.unsubscribe } } }); });
it('restores a persisted SDK session and cleans the listener on unmount', async () => {
  mocks.getSession.mockResolvedValue({ data: { session }, error: null });
  const result = render(<AuthProvider><Consumer /></AuthProvider>);
  expect(await screen.findByText('user@example.test')).toBeInTheDocument();
  result.unmount(); expect(mocks.unsubscribe).toHaveBeenCalledOnce();
});
it('responds to a sign-out event without keeping stale identity', async () => {
  mocks.getSession.mockResolvedValue({ data: { session }, error: null });
  render(<AuthProvider><Consumer /></AuthProvider>);
  await screen.findByText('user@example.test');
  await act(async () => { mocks.subscribe.mock.calls[0][0]('SIGNED_OUT', null); });
  await waitFor(() => expect(screen.getByText('Signed out')).toBeInTheDocument());
  expect(mocks.subscribe).toHaveBeenCalledOnce();
});
it('does not restore a stale session after a newer sign-out event', async () => {
  let restore!: (value: { data: { session: Session }; error: null }) => void;
  mocks.getSession.mockReturnValue(new Promise(resolve => { restore = resolve; }));
  render(<AuthProvider><Consumer /></AuthProvider>);
  await act(async () => { mocks.subscribe.mock.calls[0][0]('SIGNED_OUT', null); restore({ data: { session }, error: null }); });
  expect(screen.getByText('Signed out')).toBeInTheDocument();
});
it('accepts refreshed identity while a persisted session read is pending', async () => {
  let restore!: (value: { data: { session: Session }; error: null }) => void;
  mocks.getSession.mockReturnValue(new Promise(resolve => { restore = resolve; }));
  render(<AuthProvider><Consumer /></AuthProvider>);
  const refreshed = { ...session, user: { ...session.user, email: 'refreshed@example.test' } };
  await act(async () => { mocks.subscribe.mock.calls[0][0]('TOKEN_REFRESHED', refreshed); restore({ data: { session }, error: null }); });
  expect(screen.getByText('refreshed@example.test')).toBeInTheDocument();
});
