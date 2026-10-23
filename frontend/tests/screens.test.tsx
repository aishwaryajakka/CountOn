import { Suspense } from 'react';
import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import type { AuditEvent, WatchedExpectation } from '@/lib/types';
import { formatDate } from '@/lib/presentation';
import { evidence, evaluation, expectation, integration, notification } from './fixtures';
const mocks = vi.hoisted(() => ({ board: { data: null as WatchedExpectation[] | null, error: null as Error | null, loading: false, reload: vi.fn() }, signIn: vi.fn(), replace: vi.fn(), push: vi.fn(), evidence: vi.fn(), expectation: vi.fn(), evaluations: vi.fn(), latest: vi.fn(), integrations: vi.fn(), notifications: vi.fn(), auditEvents: vi.fn(), updateNotification: vi.fn(), request: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ replace: mocks.replace, push: mocks.push }) }));
vi.mock('@/components/app-shell', () => ({ useBoard: () => mocks.board }));
vi.mock('@/components/auth-provider', () => ({ useAuth: () => ({ session: null, loading: false, error: null }), useIdentity: () => ({ firstName: 'Test', name: 'Test User', timeZone: 'America/Chicago' }) }));
vi.mock('@/lib/supabase', () => ({ getSupabase: () => ({ auth: { signInWithPassword: mocks.signIn } }) }));
vi.mock('@/lib/api', async importOriginal => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return { ...actual, api: { evidence: mocks.evidence, expectation: mocks.expectation, evaluations: mocks.evaluations, latest: mocks.latest, integrations: mocks.integrations, notifications: mocks.notifications, auditEvents: mocks.auditEvents, updateNotification: mocks.updateNotification, request: mocks.request } };
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
  vi.clearAllMocks(); mocks.request.mockImplementation((path: string) => Promise.resolve(path.endsWith('/monitoring') ? { status: 'pending', next_run_at: '2026-10-16T17:00:00Z', last_run_at: null, interval_seconds: 3600, recurring: false, max_evidence_age_seconds: 86400, max_attempts: 5, attempt_count: 0, connection_id: null, window_start_at: null, provider_config: {} } : path === '/notification-preferences' ? { email_enabled: false, mismatch_enabled: true, deadline_enabled: false, connection_enabled: true, quiet_enabled: false, quiet_start_hour: 22, quiet_end_hour: 8, timezone: 'UTC' } : [])); mocks.board.data = [{ expectation, latest: evaluation }]; mocks.board.error = null; mocks.board.loading = false;
  mocks.evidence.mockResolvedValue(evidence); mocks.expectation.mockResolvedValue(expectation); mocks.evaluations.mockResolvedValue([evaluation]); mocks.latest.mockResolvedValue(evaluation); mocks.integrations.mockResolvedValue([integration]); mocks.notifications.mockResolvedValue([notification]); mocks.auditEvents.mockResolvedValue([]);
});
it('does not fabricate lifecycle audit events from current board snapshots', async () => {
  render(<Activity />);
  expect(await screen.findByText('No audit events yet.')).toBeInTheDocument();
  expect(screen.queryByText('Expectation created')).not.toBeInTheDocument();
  expect(screen.queryByText(/MISMATCH/)).not.toBeInTheDocument();
});
it('renders persisted audit history from the backend', async () => {
  mocks.auditEvents.mockResolvedValue([{
    audit_event_id: 'audit-id', counton_user_id: expectation.user_id,
    expectation_id: expectation.id, event_type: 'SOURCE_AUTHORIZED',
    occurred_at: expectation.created_at, source_provider: 'GMAIL',
    source_type: 'EMAIL', source_provenance: 'OFFICIAL_OAUTH',
    source_reference: null, evidence_id: null, evaluation_id: null,
    result_status: null, action_taken: 'provider.source_bound', actor_type: 'USER',
    action_metadata: {}, request_id: 'request-id',
    expectation: { id: expectation.id, claim: expectation.claim, status: expectation.status },
    evidence: null,
  }]);
  render(<Activity />);
  expect(await screen.findByRole('table', { name: 'Audit History' })).toBeInTheDocument();
  for (const heading of ['Expectation', 'Evidence', 'Source', 'Result', 'Action', 'Timestamp']) {
    expect(screen.getByRole('columnheader', { name: heading })).toBeInTheDocument();
  }
  expect(screen.getByText('Provider source bound')).toBeInTheDocument();
  expect(screen.getByText('Gmail · Official oauth')).toBeInTheDocument();
  expect(screen.queryByText('Source authorized')).not.toBeInTheDocument();
});
it('renders the login form and submits through Supabase Auth', async () => {
  mocks.signIn.mockResolvedValue({ data: { session: { access_token: 'fixture-token', user: { id: 'fixture-user' } } }, error: null });
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
  // Comparison, decision and resolution panels all use the same persisted observation.
  expect(screen.getAllByText('$162.00')).toHaveLength(4);
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

const auditFixture = (changes: Partial<AuditEvent> = {}): AuditEvent => ({
  audit_event_id: 'audit-record', counton_user_id: expectation.user_id,
  expectation_id: expectation.id, event_type: 'EXPECTATION_CONFIRMED',
  occurred_at: evaluation.created_at, source_provider: 'ALEXA', source_type: 'VOICE',
  source_provenance: 'SIGNED_ASK', source_reference: null, evidence_id: null,
  evaluation_id: null, result_status: null, action_taken: 'expectation.confirmed',
  actor_type: 'USER', action_metadata: { channel: 'alexa_skill' }, request_id: null,
  expectation: { id: expectation.id, claim: expectation.claim, status: expectation.status },
  evidence: null, ...changes,
});

it.each(['alexa_skill', 'alexa_web'] as const)('renders persisted %s expectations in the standard list and reloads', async source => {
  mocks.board.data = [{ expectation: { ...expectation, compiler_metadata: { creation_source: source }, deadline: '2026-10-30T20:00:00Z' }, latest: evaluation }];
  render(<Expectations />);
  expect(screen.getByText(source === 'alexa_skill' ? 'Created via Alexa' : 'Created via Alexa web')).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Electricity bill' })).toHaveAttribute('href', `/expectations/${expectation.id}`);
  const card = screen.getByRole('link', { name: 'Electricity bill' }).closest('article')!;
  expect(within(card).getByText('Needs attention')).toBeInTheDocument();
  expect(within(card).getByText(formatDate('2026-10-30T20:00:00Z', 'America/Chicago'))).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Refresh' }));
  expect(mocks.board.reload).toHaveBeenCalledOnce();
});

it('shows Alexa creation on the normal dashboard while UNKNOWN stays waiting despite high observations', async () => {
  mocks.board.data = [{ expectation: { ...expectation, compiler_metadata: { creation_source: 'alexa_skill' } }, latest: { ...evaluation, result: 'UNKNOWN', reasoning: { reason: 'conflicting_evidence' } } }];
  render(<Dashboard />);
  expect(await screen.findByText('Created via Alexa')).toBeInTheDocument();
  expect(screen.queryByText('Needs your attention')).not.toBeInTheDocument();
  expect(screen.queryByText('Everything looks as expected.')).not.toBeInTheDocument();
  expect(screen.getAllByText('Waiting for evidence').length).toBeGreaterThan(0);
  expect(screen.getByRole('link', { name: 'Electricity bill' })).toHaveAttribute('href', `/expectations/${expectation.id}`);
});

it('renders detail from persisted criteria, evaluation snapshots, evidence, explanation receipts and notification status', async () => {
  mocks.expectation.mockResolvedValue({ ...expectation, baseline: 999, compiler_metadata: { creation_source: 'alexa_skill' }, deadline: '2026-10-30T20:00:00Z' });
  mocks.evaluations.mockResolvedValue([evaluation, { ...evaluation, id: 'older-evaluation', result: 'MATCH', created_at: '2026-10-01T12:00:00Z' }]);
  mocks.notifications.mockResolvedValue([{ ...notification, status: 'read' }, { ...notification, id: 'other-notice', expectation_id: 'another-expectation', message: 'Unrelated notification' }]);
  mocks.auditEvents.mockResolvedValue([
    auditFixture({ event_type: 'EXPLANATION_GENERATED', evaluation_id: 'old-result', action_metadata: { bedrock_used: true, grounded: true } }),
    auditFixture({ audit_event_id: 'current-explanation', event_type: 'EXPLANATION_GENERATED', evaluation_id: evaluation.id, action_metadata: { bedrock_used: false, fallback_used: true, grounded: true, evidence_ids: ['bill-evidence'] } }),
  ]);
  await act(async () => { render(<Suspense><Detail params={Promise.resolve({ id: expectation.id })} /></Suspense>); });
  expect(await screen.findByText('Created via Alexa')).toBeInTheDocument();
  expect(screen.getByRole('heading', { level: 1 }).closest('header')).toHaveTextContent('Needs attention');
  const criteria = screen.getByRole('region', { name: 'Current monitoring criteria' });
  expect(criteria).toHaveTextContent('Baseline999');
  expect(criteria).toHaveTextContent('Less than');
  const comparison = document.querySelector('.comparison.expected')!;
  expect(comparison).toHaveTextContent('$142.10');
  expect(comparison).not.toHaveTextContent('999');
  expect(screen.getAllByText('$162.00').length).toBeGreaterThan(0);
  expect(screen.getByText('Matched')).toBeInTheDocument(); // Actual older evaluation.
  expect(await screen.findByText(/CountOn fallback explanation recorded/)).toBeInTheDocument();
  expect(screen.queryByText(/Bedrock explanation recorded/)).not.toBeInTheDocument();
  expect(await screen.findByText('Read · In-app notification')).toBeInTheDocument();
  expect(screen.queryByText('Unrelated notification')).not.toBeInTheDocument();
  expect(mocks.auditEvents).toHaveBeenCalledWith({ expectationId: expectation.id }, expect.any(AbortSignal));
  const previousReads = mocks.expectation.mock.calls.length;
  await userEvent.click(screen.getByRole('button', { name: 'Refresh' }));
  await waitFor(() => expect(mocks.expectation.mock.calls.length).toBeGreaterThan(previousReads));
  expect(mocks.board.reload).toHaveBeenCalled();
});

it('keeps simulated Ring and Bee provenance visible in persisted detail evidence', async () => {
  mocks.evidence.mockResolvedValue([
    { ...evidence[0], id: 'ring-observation', source: 'ring_simulator', raw_data: { simulated: true, provenance: 'SIMULATED_RING' } },
    { ...evidence[0], id: 'bee-observation', source: 'bee_simulator', raw_data: { simulated: true, provenance: 'SIMULATED_BEE' } },
  ]);
  await act(async () => { render(<Suspense><Detail params={Promise.resolve({ id: expectation.id })} /></Suspense>); });
  expect((await screen.findAllByText(/Ring · SIMULATED/)).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/Bee · SIMULATED/).length).toBeGreaterThan(0);
  expect(screen.getAllByText('Hardware simulation fixture · Not physical device')).toHaveLength(2);
});

it('shows the Alexa electricity acceptance record and its linked persisted 150/180 result in normal detail', async () => {
  const saved = { ...expectation, claim: 'My next electricity bill should be below $150.', baseline: null, target_value: 150, materiality_threshold: 0, compiler_metadata: { creation_source: 'alexa_skill' } };
  const evaluated = { ...evaluation, expected: { metric: 'total_cost', comparison: 'less_than', target: 150 }, observed: { metric: 'total_cost', value: 180, evidence_id: evidence[0].id } };
  mocks.expectation.mockResolvedValue(saved);
  mocks.evidence.mockResolvedValue([{ ...evidence[0], value: { amount: 180 }, raw_data: { simulated: true, category: 'DEMO', provenance: 'USER_SUBMITTED' } }]);
  mocks.evaluations.mockResolvedValue([evaluated]);
  mocks.latest.mockResolvedValue(evaluated);
  mocks.notifications.mockResolvedValue([{ ...notification, expectation_id: saved.id, evaluation_id: evaluated.id }]);
  mocks.auditEvents.mockResolvedValue([
    auditFixture({ expectation_id: saved.id, event_type: 'EXPECTATION_CONFIRMED', source_provider: 'ALEXA', source_provenance: 'SIGNED_ASK' }),
    auditFixture({ audit_event_id: 'evaluation-link', expectation_id: saved.id, evaluation_id: evaluated.id, evidence_id: evidence[0].id, event_type: 'EVALUATION_COMPLETED', result_status: 'MISMATCH' }),
  ]);
  await act(async () => { render(<Suspense><Detail params={Promise.resolve({ id: saved.id })} /></Suspense>); });
  expect(await screen.findByText('Created via Alexa')).toBeInTheDocument();
  expect(screen.getByRole('region', { name: 'Current monitoring criteria' })).toHaveTextContent('Target150');
  expect(document.querySelector('.comparison.expected')).toHaveTextContent('$150.00');
  expect(document.querySelector('.comparison.observed')).toHaveTextContent('$180.00');
  expect(screen.getByRole('heading', { level: 1 }).closest('header')).toHaveTextContent('Needs attention');
  expect(await screen.findByText('Pending · In-app notification')).toBeInTheDocument();
  expect(screen.getAllByText(/Utility bill · SIMULATED/).length).toBeGreaterThan(0);
  expect(mocks.evidence).toHaveBeenCalledWith(saved.id, expect.any(AbortSignal));
  expect(mocks.evaluations).toHaveBeenCalledWith(saved.id, expect.any(AbortSignal));
  expect(mocks.auditEvents).toHaveBeenCalledWith({ expectationId: saved.id }, expect.any(AbortSignal));
});

it('renders actual lifecycle audit events without inventing model or notification activity', async () => {
  mocks.auditEvents.mockResolvedValue([
    auditFixture(),
    auditFixture({ audit_event_id: 'email-audit', event_type: 'EVIDENCE_INGESTED', source_provider: 'GMAIL', source_provenance: 'OFFICIAL_OAUTH', action_taken: 'evidence.ingested' }),
    auditFixture({ audit_event_id: 'result-audit', event_type: 'EVALUATION_COMPLETED', result_status: 'MISMATCH', evaluation_id: evaluation.id, action_taken: 'expectation.evaluated' }),
    auditFixture({ audit_event_id: 'explanation-audit', event_type: 'EXPLANATION_GENERATED', action_metadata: { bedrock_used: true, grounded: true }, action_taken: 'explanation.generated' }),
    auditFixture({ audit_event_id: 'notice-audit', event_type: 'NOTIFICATION_CREATED', action_taken: 'notification.created' }),
  ]);
  render(<Activity />);
  const table = await screen.findByRole('table', { name: 'Audit History' });
  for (const label of ['Alexa created expectation', 'Evidence received from Gmail', 'CountOn evaluated MISMATCH', 'Bedrock generated grounded explanation', 'Notification created']) {
    expect(within(table).getByText(label)).toBeInTheDocument();
  }
  await userEvent.click(screen.getByRole('button', { name: 'Refresh' }));
  await waitFor(() => expect(mocks.auditEvents).toHaveBeenCalledTimes(2));
});

it('refreshes detail and shared board only after notification acknowledgement is persisted', async () => {
  let acknowledge!: (value: typeof notification) => void;
  mocks.updateNotification.mockReturnValue(new Promise(resolve => { acknowledge = resolve; }));
  mocks.notifications.mockResolvedValueOnce([notification]).mockResolvedValue([{ ...notification, status: 'read' }]);
  await act(async () => { render(<Suspense><Detail params={Promise.resolve({ id: expectation.id })} /></Suspense>); });
  await screen.findByText('Pending · In-app notification');
  await userEvent.click(screen.getByRole('button', { name: 'Mark as read' }));
  expect(screen.queryByText('Read · In-app notification')).not.toBeInTheDocument();
  expect(mocks.board.reload).not.toHaveBeenCalled();
  await act(async () => { acknowledge({ ...notification, status: 'read' }); });
  expect(await screen.findByText('Read · In-app notification')).toBeInTheDocument();
  expect(mocks.updateNotification).toHaveBeenCalledWith(notification.id, 'read');
  expect(mocks.notifications).toHaveBeenCalledTimes(2);
  expect(mocks.board.reload).toHaveBeenCalledOnce();
});

it('revalidates externally changed criteria on focus without reusing stale form values', async () => {
  mocks.expectation.mockResolvedValueOnce(expectation).mockResolvedValue({ ...expectation, baseline: 150, deadline: '2026-10-30T20:00:00Z', updated_at: '2026-10-23T12:00:00Z' });
  await act(async () => { render(<Suspense><Detail params={Promise.resolve({ id: expectation.id })} /></Suspense>); });
  expect(await screen.findByLabelText('Amount')).toHaveValue(142.1);
  await act(async () => { window.dispatchEvent(new Event('focus')); });
  await waitFor(() => expect(screen.getByLabelText('Amount')).toHaveValue(150));
  expect(screen.getByLabelText('Deadline (ISO timestamp with timezone)')).toHaveValue('2026-10-30T20:00:00Z');
  expect(screen.getByRole('region', { name: 'Current monitoring criteria' })).toHaveTextContent('Baseline150');
});

it('preserves unsaved condition edits when a background refresh only changes status', async () => {
  mocks.expectation.mockResolvedValueOnce(expectation).mockResolvedValue({ ...expectation, status: 'fulfilled', updated_at: '2026-10-23T12:00:00Z' });
  await act(async () => { render(<Suspense><Detail params={Promise.resolve({ id: expectation.id })} /></Suspense>); });
  const amount = await screen.findByLabelText('Amount');
  await userEvent.clear(amount); await userEvent.type(amount, '175');
  await act(async () => { window.dispatchEvent(new Event('focus')); });
  await waitFor(() => expect(mocks.expectation).toHaveBeenCalledTimes(2));
  expect(screen.getByLabelText('Amount')).toHaveValue(175);
});
