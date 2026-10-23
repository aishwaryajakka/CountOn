import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Suspense } from 'react';
import { beforeEach, expect, it, vi } from 'vitest';
import type { WatchedExpectation } from '@/lib/types';
import { expectation, evaluation } from './fixtures';

const mocks = vi.hoisted(() => ({
  board: { data: null as WatchedExpectation[] | null, error: null as Error | null, loading: true, reload: vi.fn() },
  tracking: { get: vi.fn(), configure: vi.fn() },
  api: { board: vi.fn(), expectation: vi.fn(), evidence: vi.fn(), evaluations: vi.fn(), latest: vi.fn(), auditEvents: vi.fn(), addEvidence: vi.fn(), evaluate: vi.fn(), simulateRing: vi.fn(), simulateBee: vi.fn(), updateExpectation: vi.fn() },
}));
vi.mock('@/lib/monitoring', () => ({ monitoring: mocks.tracking }));
vi.mock('@/lib/api', async original => ({ ...await original<typeof import('@/lib/api')>(), api: mocks.api }));
vi.mock('@/components/app-shell', async original => ({ ...await original<typeof import('@/components/app-shell')>(), useBoard: () => mocks.board }));
vi.mock('next/navigation', () => ({ usePathname: () => '/demos', useRouter: () => ({ replace: vi.fn() }) }));
vi.mock('@/components/auth-provider', () => ({
  useIdentity: () => ({ name: 'Fixture', firstName: 'Fixture', timeZone: 'UTC', email: 'fixture@example.test' }),
  useAuth: () => ({ loading: false, session: { user: { id: 'fixture-user' } }, error: null }),
}));
vi.mock('@/components/source-binding', () => ({ SourceBinding: ({ expectationId }: { expectationId: string }) => <div>Bound source {expectationId}</div> }));
vi.mock('@/components/tracking-controls', () => ({ TrackingControls: () => <div>Tracking controls</div> }));

import Expectations from '@/app/(workspace)/expectations/page';
import ExpectationDetail from '@/app/(workspace)/expectations/[id]/page';
import Dashboard from '@/app/(workspace)/dashboard/page';
import Activity from '@/app/(workspace)/activity/page';
import Demos from '@/app/(workspace)/demos/page';
import { AppShell } from '@/components/app-shell';
import { ExpectationActionsModal } from '@/components/expectation-actions-modal';
import { simulatorTarget, simulatorTargets } from '@/lib/simulators';

const ring = { ...expectation, type: 'boolean' as const, metric: 'package_detected', claim: 'Package fixture', evidence_sources: ['ring_simulator'] };
const bee = { ...ring, id: 'bee-fixture', metric: 'appointment_confirmed', claim: 'Appointment fixture', evidence_sources: ['bee_simulator'] };
const rows = (exp = expectation): WatchedExpectation[] => [{ expectation: exp, latest: null }];
beforeEach(() => {
  vi.clearAllMocks();
  Object.assign(mocks.board, { data: null, error: null, loading: true });
  mocks.api.board.mockResolvedValue([]);
  mocks.api.expectation.mockResolvedValue(expectation);
  mocks.api.evidence.mockResolvedValue([]);
  mocks.api.evaluations.mockResolvedValue([evaluation]);
  mocks.api.latest.mockResolvedValue(evaluation);
  mocks.api.auditEvents.mockResolvedValue([]);
  mocks.api.addEvidence.mockResolvedValue({});
  mocks.api.evaluate.mockResolvedValue({ ...evaluation, result: 'UNKNOWN' });
  mocks.api.simulateRing.mockResolvedValue({ evidence: {}, evaluation: { ...evaluation, result: 'UNKNOWN' } });
  mocks.api.simulateBee.mockResolvedValue({ evidence: {}, evaluation: { ...evaluation, result: 'UNKNOWN' } });
  mocks.api.updateExpectation.mockResolvedValue(expectation);
  mocks.tracking.get.mockResolvedValue({ status: 'pending', interval_seconds: 3600 });
  mocks.tracking.configure.mockResolvedValue({ status: 'paused' });
});

it('keeps hooks stable through loading, error and populated views, and preserves provider filters and management', async () => {
  const view = render(<Expectations />);
  Object.assign(mocks.board, { loading: false, error: new Error('fixture failure') });
  view.rerender(<Expectations />);
  expect(screen.getByText(/We couldn’t load/)).toBeInTheDocument();
  Object.assign(mocks.board, { error: null, data: rows() });
  view.rerender(<Expectations />);
  expect(screen.getByLabelText('Filter by provider')).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: /Manage/ }));
  expect(screen.getByLabelText('Claim description')).toHaveValue(expectation.claim);
});

it('preserves source binding and tracking alongside detail management and authoritative latest results', async () => {
  mocks.api.latest.mockResolvedValue({ ...evaluation, result: 'MATCH' });
  await act(async () => { render(<Suspense fallback={<div>Loading detail</div>}><ExpectationDetail params={Promise.resolve({ id: expectation.id })} /></Suspense>); });
  expect(await screen.findByText('Tracking controls')).toBeInTheDocument();
  expect(screen.getByText(`Bound source ${expectation.id}`)).toBeInTheDocument();
  expect(screen.getByRole('heading', { level: 1 }).closest('header')).toHaveTextContent('Matched');
  await userEvent.click(screen.getByRole('button', { name: 'Manage / Edit' }));
  expect(screen.getByLabelText('Claim description')).toHaveValue(expectation.claim);
});

it.each([['ring', ring, 'Ring Delivery Simulator', 'Send Ring Evidence'], ['bee', bee, 'Bee Wearable Simulator', 'Send Bee Context']] as const)(
  'sends tagged %s evidence to the selected expectation and shows the actual backend outcome', async (kind, exp, tab, submit) => {
    Object.assign(mocks.board, { loading: false, data: rows(exp) });
    render(<Demos />);
    await userEvent.click(screen.getByRole('button', { name: tab }));
    expect(screen.getByText(/Ring remains simulated/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole('button', { name: new RegExp(submit) }));
    const method = kind === 'ring' ? mocks.api.simulateRing : mocks.api.simulateBee;
    await waitFor(() => expect(method).toHaveBeenCalledOnce());
    expect(method.mock.calls[0][0]).toBe(exp.id);
    expect(method.mock.calls[0][1]).toMatchObject({ simulated: true });
    expect(await screen.findByText(/Backend evaluation: UNKNOWN/)).toBeInTheDocument();
  }
);

it('requires exact selection when multiple compatible expectations exist', async () => {
  const second = { ...ring, id: 'second-ring', claim: 'Other package' };
  Object.assign(mocks.board, { loading: false, data: [...rows(ring), ...rows(second)] });
  render(<Demos />);
  await userEvent.click(screen.getByRole('button', { name: 'Ring Delivery Simulator' }));
  const submit = screen.getByRole('button', { name: /Send Ring Evidence/ });
  expect(submit).toBeDisabled();
  await userEvent.selectOptions(screen.getByLabelText('Expectation receiving SIMULATED evidence'), second.id);
  await userEvent.click(submit);
  await waitFor(() => expect(mocks.api.simulateRing).toHaveBeenCalledWith(second.id, expect.any(Object)));
});

it('never attaches a quick simulator event to an unrelated first row', async () => {
  Object.assign(mocks.board, { loading: false, data: rows() });
  render(<Dashboard />);
  await userEvent.click(screen.getByRole('button', { name: /Ring: No Package Detected/ }));
  expect(await screen.findByText(/No compatible active expectation/)).toBeInTheDocument();
  expect(mocks.api.addEvidence).not.toHaveBeenCalled();
});

it('does not continuously refetch empty dashboard evidence on state updates', async () => {
  const view = render(<Dashboard />);
  await act(async () => {});
  view.rerender(<Dashboard />);
  expect(mocks.api.evidence).not.toHaveBeenCalled();
});

it('keeps both Alexa and simulator navigation routes', async () => {
  render(<AppShell><div>Workspace fixture</div></AppShell>);
  expect(screen.getByRole('link', { name: 'Alexa+ MCP Demo' })).toHaveAttribute('href', '/alexa');
  expect(screen.getByRole('link', { name: 'Interactive Demos' })).toHaveAttribute('href', '/demos');
});

it('preserves an explicitly zero tolerance when editing', async () => {
  render(<ExpectationActionsModal expectation={{ ...expectation, materiality_threshold: 0 }} isOpen onClose={vi.fn()} onUpdated={vi.fn()} />);
  await userEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
  await waitFor(() => expect(mocks.api.updateExpectation).toHaveBeenCalledWith(expectation.id, expect.objectContaining({ materiality_threshold: 0 })));
});

it('rejects terminal, unrelated and ambiguous simulator targets without inventing an association', () => {
  expect(simulatorTargets(rows(), 'ring')).toEqual([]);
  expect(simulatorTargets(rows({ ...ring, status: 'cancelled' }), 'ring')).toEqual([]);
  expect(() => simulatorTarget([...rows(ring), ...rows({ ...ring, id: 'other' })], 'ring')).toThrow('Select the exact');
  expect(() => simulatorTarget(rows(ring), 'ring', 'unowned-id')).toThrow('Select the exact');
});

it('retains package event simulations without inventing temporal outcomes', () => {
  const temporal = { ...ring, type: 'event' as const, metric: 'package_delivery' };
  expect(simulatorTarget(rows(temporal), 'ring')).toEqual(temporal);
});


it('pauses the durable job without cancelling the expectation', async () => {
  render(<ExpectationActionsModal expectation={expectation} isOpen onClose={vi.fn()} onUpdated={vi.fn()} />);
  const pause = screen.getByRole('button', { name: 'Pause Expectation' });
  await waitFor(() => expect(pause).toBeEnabled());
  await userEvent.click(pause);
  await waitFor(() => expect(mocks.tracking.configure).toHaveBeenCalledWith(expectation.id, expect.any(Object), 'paused'));
  expect(mocks.api.updateExpectation).not.toHaveBeenCalled();
});

it.each(['cancelled', 'resolved'] as const)('explicitly reopens a %s expectation and restarts its cancelled job', async status => {
  mocks.tracking.get.mockResolvedValue({ status: 'cancelled', interval_seconds: 3600 });
  render(<ExpectationActionsModal expectation={{ ...expectation, status }} isOpen onClose={vi.fn()} onUpdated={vi.fn()} />);
  const reopen = screen.getByRole('button', { name: status === 'cancelled' ? 'Reopen and Resume Monitoring' : 'Re-open Expectation' });
  await waitFor(() => expect(reopen).toBeEnabled());
  await userEvent.click(reopen);
  await waitFor(() => expect(mocks.tracking.configure).toHaveBeenCalledWith(expectation.id, expect.any(Object), 'pending'));
  expect(mocks.api.updateExpectation).toHaveBeenCalledWith(expectation.id, { status: 'monitoring' });
});


it.each([Dashboard, Activity])('shows evidence request failures rather than an invented empty timeline', async Page => {
  Object.assign(mocks.board, { loading: false, data: rows({ ...expectation, status: 'monitoring' }) });
  mocks.api.evidence.mockRejectedValue(new Error('Fixture upstream outage'));
  render(<Page />);
  expect(await screen.findByText(/We couldn’t load/)).toBeInTheDocument();
  expect(screen.queryByText('No evidence recorded yet')).not.toBeInTheDocument();
});
