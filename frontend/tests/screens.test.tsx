import { Suspense } from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import type { WatchedExpectation } from '@/lib/types';
import { evidence, evaluation, expectation, integration, notification } from './fixtures';
const mocks = vi.hoisted(() => ({ board: { data: null as WatchedExpectation[] | null, error: null as Error | null, loading: false, reload: vi.fn() }, signIn: vi.fn(), replace: vi.fn(), push: vi.fn(), evidence: vi.fn(), expectation: vi.fn(), evaluations: vi.fn(), latest: vi.fn(), integrations: vi.fn(), notifications: vi.fn(), updateNotification: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ replace: mocks.replace, push: mocks.push }) }));
vi.mock('@/components/app-shell', () => ({ useBoard: () => mocks.board }));
vi.mock('@/components/auth-provider', () => ({ useAuth: () => ({ session: null, loading: false, error: null }), useIdentity: () => ({ firstName: 'Test', name: 'Test User', timeZone: 'America/Chicago' }) }));
vi.mock('@/lib/supabase', () => ({ getSupabase: () => ({ auth: { signInWithPassword: mocks.signIn } }) }));
vi.mock('@/lib/api', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, api: { evidence: mocks.evidence, expectation: mocks.expectation, evaluations: mocks.evaluations, latest: mocks.latest, integrations: mocks.integrations, notifications: mocks.notifications, updateNotification: mocks.updateNotification } };
});
import Dashboard from '@/app/(workspace)/dashboard/page';
import Expectations from '@/app/(workspace)/expectations/page';
import Detail from '@/app/(workspace)/expectations/[id]/page';
import Integrations from '@/app/(workspace)/integrations/page';
import Notifications from '@/app/(workspace)/notifications/page';
import Login from '@/app/login/page';
import Activity from '@/app/(workspace)/activity/page';
import { NotificationCard } from '@/components/notification';
import { ErrorState } from '@/components/ui';
import { Timeline } from '@/components/expectation';
beforeEach(() => {
  vi.clearAllMocks(); mocks.board.data = [{ expectation, latest: evaluation }]; mocks.board.error = null; mocks.board.loading = false;
  mocks.evidence.mockResolvedValue(evidence); mocks.expectation.mockResolvedValue(expectation); mocks.evaluations.mockResolvedValue([evaluation]); mocks.latest.mockResolvedValue(evaluation); mocks.integrations.mockResolvedValue([integration]); mocks.notifications.mockResolvedValue([notification]);
});
it('shows readable result labels in activity rather than raw evaluator enums', () => {
  render(<Activity />);
  expect(screen.getByText('Electricity bill · Needs attention')).toBeInTheDocument();
  expect(screen.queryByText(/MISMATCH/)).not.toBeInTheDocument();
});
it('renders the login form and submits through Supabase Auth', async () => {
  mocks.signIn.mockResolvedValue({ data: {}, error: null });
  render(<Login />); const user = userEvent.setup();
  await user.type(screen.getByLabelText('Email address'), 'user@example.test');
  await user.type(screen.getByLabelText('Password'), 'fixture-only-password');
  await user.click(screen.getByRole('button', { name: 'Sign in to CountOn' }));
  expect(mocks.signIn).toHaveBeenCalledWith({ email: 'user@example.test', password: 'fixture-only-password' });
  expect(mocks.replace).toHaveBeenCalledWith('/dashboard');
});
it('renders dynamic dashboard evidence, not static reference amounts', async () => {
  mocks.evidence.mockResolvedValue(evidence.map(item => item.metric === 'total_cost' ? { ...item, value: { amount: 180 } } : item));
  mocks.board.data = [{ expectation, latest: { ...evaluation, observed: { value: 180, evidence_id: 'bill-evidence' } } }];
  render(<Dashboard />);
  expect(await screen.findByText('$180.00')).toBeInTheDocument();
  expect(screen.queryByText('$162.00')).not.toBeInTheDocument();
});
it('renders a calm dashboard empty state', async () => {
  mocks.board.data = []; render(<Dashboard />);
  expect(await screen.findByText('Nothing being monitored yet.')).toBeInTheDocument();
});
it('stays quiet when no expectation needs attention', async () => {
  mocks.board.data = [{ expectation: { ...expectation, status: 'fulfilled' }, latest: { ...evaluation, result: 'MATCH' } }];
  render(<Dashboard />);
  expect(await screen.findByText('Everything looks as expected.')).toBeInTheDocument();
  expect(screen.queryByText('Needs your attention')).not.toBeInTheDocument();
});
it('renders expectations and filters by derived status', async () => {
  render(<Expectations />); expect(screen.getByRole('link', { name: 'Electricity bill' })).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: /Matched/ }));
  expect(screen.getByText('Nothing here right now.')).toBeInTheDocument();
});
it('renders detail evidence and an actual timestamp timeline', async () => {
  const params = Promise.resolve({ id: expectation.id });
  await act(async () => { render(<Suspense fallback={<span>Loading detail</span>}><Detail params={params} /></Suspense>); await params; });
  expect(await screen.findByRole('heading', { name: 'Evidence gathered' })).toBeInTheDocument();
  expect(screen.getByRole('heading', { name: 'Timeline' })).toBeInTheDocument();
  expect(screen.getAllByText('$162.00')).toHaveLength(2);
});
it('renders backend connections with an honest demo badge', async () => {
  render(<Integrations />);
  expect(await screen.findByText('Personal Gmail')).toBeInTheDocument();
  expect(screen.getByText('Demo connection')).toBeInTheDocument();
  expect(screen.getByText(/Live access not configured/)).toBeInTheDocument();
});
it('transitions from subtle loading to an actionable connections empty state', async () => {
  let resolve!: (rows: []) => void;
  mocks.integrations.mockReturnValue(new Promise(done => { resolve = done; }));
  render(<Integrations />);
  expect(screen.getByRole('status')).toBeInTheDocument();
  await act(async () => { resolve([]); });
  expect(await screen.findByText('No connected accounts yet.')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Explore connections' })).toBeInTheDocument();
});
it('recovers a failed connections read through the retry action', async () => {
  mocks.integrations.mockRejectedValueOnce(new Error('Connection unavailable')).mockResolvedValueOnce([integration]);
  render(<Integrations />);
  await screen.findByRole('alert');
  await userEvent.click(screen.getByRole('button', { name: 'Try again' }));
  expect(await screen.findByText(integration.display_name!)).toBeInTheDocument();
  expect(mocks.integrations).toHaveBeenCalledTimes(2);
});
it('renders notifications from the API', async () => {
  render(<Notifications />);
  expect(await screen.findByText(notification.message)).toBeInTheDocument();
});
it('preserves a notification and reports failed dismissal', async () => {
  mocks.updateNotification.mockRejectedValue(new Error('offline')); const refresh = vi.fn();
  render(<NotificationCard item={notification} refresh={refresh} />);
  await userEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('unchanged');
  expect(refresh).not.toHaveBeenCalled();
});
it('refetches only after a successful dismissal', async () => {
  mocks.updateNotification.mockResolvedValue({ ...notification, status: 'dismissed' }); const refresh = vi.fn();
  render(<NotificationCard item={notification} refresh={refresh} />);
  await userEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
  await waitFor(() => expect(refresh).toHaveBeenCalledOnce());
});
it('offers a retry for data errors', () => {
  render(<ErrorState error={new Error('Connection unavailable')} retry={vi.fn()} />);
  expect(screen.getByRole('alert')).toHaveTextContent('Connection unavailable');
  expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument();
});
it('orders creation before evaluation when database timestamps tie', () => {
  render(<Timeline expectation={expectation} evidence={[]} evaluations={[{ ...evaluation, created_at: expectation.created_at }]} />);
  const items = screen.getAllByRole('listitem');
  expect(items[0]).toHaveTextContent('Expectation created');
  expect(items[1]).toHaveTextContent('Mismatch detected');
});
