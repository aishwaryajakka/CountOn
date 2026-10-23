import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { expectation, evaluation, evidence, notification } from './fixtures';
import type { Result } from '@/lib/types';

const mocks = vi.hoisted(() => ({
  api: { createExpectation: vi.fn(), expectation: vi.fn(), evidence: vi.fn(), latest: vi.fn(), evaluations: vi.fn(), notifications: vi.fn(), auditEvents: vi.fn(), addEvidence: vi.fn(), evaluate: vi.fn(), simulateRing: vi.fn(), simulateBee: vi.fn() },
  requestAgent: vi.fn(),
}));
vi.mock('@/lib/api', () => ({ api: mocks.api }));
vi.mock('@/lib/agent/client', () => ({ requestAgent: mocks.requestAgent }));
vi.mock('@/components/auth-provider', () => ({
  useAuth: () => ({ session: { user: { id: 'fixture-user' }, access_token: 'test-only-token' } }),
  useIdentity: () => ({ timeZone: 'UTC' }),
}));
import { DemoScenarios } from '@/components/demo-scenarios';
import { demoExpectation, demoScenarios } from '@/lib/demo-scenarios';

beforeEach(() => {
  vi.resetAllMocks();
  mocks.api.createExpectation.mockResolvedValue(expectation);
  mocks.api.expectation.mockResolvedValue(expectation);
  mocks.api.evidence.mockResolvedValue([{ ...evidence[0], value: { amount: 180 }, raw_data: { simulated: true, category: 'DEMO', provenance: 'USER_SUBMITTED' } }]);
  const actual = { ...evaluation, expected: { target: 150, comparison: 'less_than' }, observed: { value: 180 } };
  mocks.api.latest.mockResolvedValue(actual);
  mocks.api.evaluations.mockResolvedValue([actual]);
  mocks.api.notifications.mockResolvedValue([notification]);
  mocks.api.auditEvents.mockResolvedValue([]);
  mocks.api.addEvidence.mockResolvedValue(evidence[0]);
  mocks.api.evaluate.mockResolvedValue(actual);
  mocks.api.simulateRing.mockResolvedValue({ evidence: evidence[0], evaluation: actual });
  mocks.api.simulateBee.mockResolvedValue({ evidence: evidence[0], evaluation: actual });
  mocks.requestAgent.mockResolvedValue({ status: 'SUCCESS', action: 'EXPLAIN_MISMATCH', answer: 'The recorded bill is $30 above your $150 target.' });
});

it('shows exactly three scenario cards and explicit consent to normal persisted demo records', () => {
  render(<DemoScenarios onSaved={vi.fn()} />);
  expect(screen.getAllByRole('article')).toHaveLength(3);
  demoScenarios.forEach(scenario => expect(screen.getByRole('button', { name: scenario.button })).toBeEnabled());
  expect(screen.getByText(/approves its named demo source/)).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /Reset/ })).not.toBeInTheDocument();
});

it('creates electricity, evaluates, reads persisted records and asks the shared orchestrator Why exactly once', async () => {
  const onSaved = vi.fn();
  render(<DemoScenarios onSaved={onSaved} />);
  const button = screen.getByRole('button', { name: 'Run Electricity Demo' });
  fireEvent.click(button); fireEvent.click(button);
  const result = await screen.findByRole('region', { name: 'Persisted demo result' });
  expect(mocks.api.createExpectation).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ target_value: 150, comparison: 'less_than', materiality_threshold: 0 }));
  expect(mocks.api.addEvidence).toHaveBeenCalledWith(expectation.id, expect.objectContaining({ value: { amount: 180 }, raw_data: { simulated: true, category: 'DEMO', provenance: 'USER_SUBMITTED' } }));
  expect(mocks.api.evaluate).toHaveBeenCalledWith(expectation.id, expect.stringMatching(/^simulation:/));
  expect(within(result).getByRole('heading', { name: 'MISMATCH' })).toBeInTheDocument();
  expect(within(result).getByText('Difference: $30.00 over target')).toBeInTheDocument();
  expect(within(result).getByText(/Notification notification-id · pending/)).toBeInTheDocument();
  expect(await screen.findByText('The recorded bill is $30 above your $150 target.')).toBeInTheDocument();
  expect(mocks.requestAgent).toHaveBeenCalledExactlyOnceWith('test-only-token', { text: 'Why did it fail?', expectation_id: expectation.id, session_reference: null });
  expect(screen.getByRole('link', { name: 'Open created expectation' })).toHaveAttribute('href', `/expectations/${expectation.id}`);
  await userEvent.click(screen.getByText('Evidence & provenance (1)'));
  expect(within(result).getByText('Utility bill · SIMULATED')).toBeInTheDocument();
  expect(within(result).getByText(/USER_SUBMITTED · DEMO/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Refresh saved result' }));
  await waitFor(() => expect(mocks.api.expectation).toHaveBeenCalledWith(expectation.id));
  expect(mocks.api.createExpectation).toHaveBeenCalledOnce();
  expect(mocks.api.evaluate).toHaveBeenCalledOnce();
  expect(onSaved).toHaveBeenCalled();
});

it.each([['package', 'MATCH'], ['bee', 'UNKNOWN']] as const)('uses the existing %s simulator and displays persisted %s without asking Why', async (kind, resultName) => {
  const actual = { ...evaluation, result: resultName, observed: {}, expected: {} };
  mocks.api.latest.mockResolvedValue(actual);
  mocks.api.evaluations.mockResolvedValue([actual]);
  mocks.api.notifications.mockResolvedValue([]);
  mocks.api.evidence.mockResolvedValue([{ ...evidence[0], source: kind === 'package' ? 'ring_simulator' : 'bee_simulator', value: kind === 'package' ? { value: true } : { summary: demoScenarios[2].claim, commitment_confirmed: true, context_only: true }, raw_data: { simulated: true, provenance: kind === 'package' ? 'SIMULATED_RING' : 'SIMULATED_BEE' } }]);
  render(<DemoScenarios onSaved={vi.fn()} />);
  await userEvent.click(screen.getByRole('button', { name: kind === 'package' ? 'Run Package Demo' : 'Run Bee Demo' }));
  const result = await screen.findByRole('region', { name: 'Persisted demo result' });
  expect(within(result).getByRole('heading', { name: resultName })).toBeInTheDocument();
  expect(within(result).getByText('No mismatch notification recorded.')).toBeInTheDocument();
  if (kind === 'package') {
    expect(mocks.api.addEvidence).toHaveBeenCalledWith(expectation.id, expect.objectContaining({ source: 'delivery', metric: 'delivered', value: { value: true }, raw_data: { simulated: true, category: 'DEMO', provenance: 'USER_SUBMITTED' } }));
    expect(mocks.api.simulateRing).toHaveBeenCalledWith(expectation.id, expect.objectContaining({ simulated: true, kind: 'package_detected', metric: 'delivered' }));
    expect(within(result).getByText('No alert needed. Silence is success.')).toBeInTheDocument();
  } else {
    expect(mocks.api.simulateBee).toHaveBeenCalledWith(expectation.id, expect.objectContaining({ simulated: true, type: 'commitment', confirmed: true, summary: demoScenarios[2].claim }));
    expect(within(result).getByText(/Arrival not yet confirmed/)).toBeInTheDocument();
  }
  await userEvent.click(screen.getByText('Evidence & provenance (1)'));
  expect(within(result).getByText(kind === 'package' ? 'Ring · SIMULATED' : 'Bee · SIMULATED')).toBeInTheDocument();
  expect(mocks.requestAgent).not.toHaveBeenCalled();
});

it.each(['MATCH', 'UNKNOWN'] as Result[])('does not hard-code the expected electricity verdict when the backend returns %s', async actual => {
  mocks.api.latest.mockResolvedValue({ ...evaluation, result: actual });
  mocks.api.notifications.mockResolvedValue([]);
  render(<DemoScenarios onSaved={vi.fn()} />);
  await userEvent.click(screen.getByRole('button', { name: 'Run Electricity Demo' }));
  const result = await screen.findByRole('region', { name: 'Persisted demo result' });
  expect(within(result).getByRole('heading', { name: actual })).toBeInTheDocument();
  expect(mocks.requestAgent).not.toHaveBeenCalled();
});

it('does not recreate records after a partial failure, and refresh only reads persisted data', async () => {
  mocks.api.addEvidence.mockRejectedValue(new Error('network failure'));
  render(<DemoScenarios onSaved={vi.fn()} />);
  await userEvent.click(screen.getByRole('button', { name: 'Run Electricity Demo' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Check the saved expectation');
  expect(screen.getByRole('button', { name: 'Run Electricity Demo' })).toBeDisabled();
  expect(screen.getByRole('link', { name: 'Open created expectation' })).toHaveAttribute('href', `/expectations/${expectation.id}`);
  await userEvent.click(screen.getByRole('button', { name: 'Refresh saved result' }));
  expect(await screen.findByRole('region', { name: 'Persisted demo result' })).toBeInTheDocument();
  expect(mocks.api.createExpectation).toHaveBeenCalledOnce();
  expect(mocks.api.addEvidence).toHaveBeenCalledOnce();
  expect(mocks.api.evaluate).not.toHaveBeenCalled();
});

it('shows only persisted audit events and notification status, and keeps evidence after explanation failure', async () => {
  mocks.requestAgent.mockRejectedValue(new Error('provider unavailable'));
  mocks.api.auditEvents.mockResolvedValue([{ audit_event_id: 'audit-1', occurred_at: evaluation.created_at, event_type: 'EVALUATION_COMPLETED', action_taken: 'expectation.evaluated', result_status: 'MISMATCH', action_metadata: {}, source_provider: 'UTILITY', source_provenance: 'USER_SUBMITTED' }]);
  render(<DemoScenarios onSaved={vi.fn()} />);
  await userEvent.click(screen.getByRole('button', { name: 'Run Electricity Demo' }));
  expect(await screen.findByText(/Explanation is unavailable/)).toBeInTheDocument();
  await userEvent.click(screen.getByText('Activity timeline (1)'));
  expect(screen.getByText('CountOn evaluated MISMATCH')).toBeInTheDocument();
  expect(screen.queryByText('Notification created')).not.toBeInTheDocument();
  expect(screen.queryByText('Bedrock generated grounded explanation')).not.toBeInTheDocument();
});

it('persists an explicit upcoming Friday deadline and preserves the exact claims', () => {
  const now = new Date(2026, 9, 23, 12);
  for (const kind of ['package', 'bee'] as const) {
    const payload = demoExpectation(kind, now);
    expect(new Date(payload.deadline!).getDay()).toBe(5);
    expect(new Date(payload.deadline!).getTime()).toBeGreaterThan(now.getTime());
    expect(payload.claim).toBe(demoScenarios.find(item => item.id === kind)!.claim);
    expect(payload.evidence_sources).toEqual(kind === 'package' ? ['delivery', 'ring_simulator'] : ['bee_simulator']);
  }
});
