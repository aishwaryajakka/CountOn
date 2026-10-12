import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ previewPlan: vi.fn(), confirmPlan: vi.fn() }));
vi.mock('@/lib/providers', () => ({ providers: mocks }));
import { MonitoringPlanSetup } from '@/components/monitoring-plan';

const candidate = { sync_id: 'sync', external_id: 'mail', group_id: 'same-order', label: 'Order fixture', account_label: 'Gmail', rule: { kind: 'order' } };
beforeEach(() => { vi.clearAllMocks(); mocks.previewPlan.mockResolvedValue({ status: 'ready', question: 'Confirm which sources to monitor.', candidates: [candidate], bedrock_calls: 0 }); mocks.confirmPlan.mockResolvedValue({ status: 'pending', job_id: 'job' }); });
it('previews without mutation and confirms only explicitly selected references', async () => {
  const refresh = vi.fn(); render(<MonitoringPlanSetup expectationId="expectation" refresh={refresh} />);
  expect(mocks.previewPlan).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('button', { name: 'Find authorized sources' }));
  expect(await screen.findByRole('checkbox')).not.toBeChecked();
  expect(screen.getByRole('button', { name: 'Confirm sources and monitoring' })).toBeDisabled();
  expect(mocks.confirmPlan).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('checkbox'));
  await userEvent.click(screen.getByRole('button', { name: 'Confirm sources and monitoring' }));
  await waitFor(() => expect(mocks.confirmPlan).toHaveBeenCalledWith('expectation', {}, [{ sync_id: 'sync', external_id: 'mail' }]));
  expect(await screen.findByRole('status')).toHaveTextContent('Monitoring is scheduled'); expect(refresh).toHaveBeenCalledOnce();
});
it('requires disambiguation and prevents selecting a different order at the same time', async () => {
  mocks.previewPlan.mockResolvedValue({ status: 'clarification', question: 'Which order?', candidates: [candidate, { ...candidate, sync_id: 'other', external_id: 'other-mail', group_id: 'different-order', label: 'Other order' }] });
  render(<MonitoringPlanSetup expectationId="expectation" refresh={vi.fn()} />);
  await userEvent.click(screen.getByRole('button', { name: 'Find authorized sources' }));
  const choices = await screen.findAllByRole('checkbox');
  await userEvent.click(choices[0]); expect(choices[1]).toBeDisabled(); expect(mocks.confirmPlan).not.toHaveBeenCalled();
});
it('does not pretend unavailable permissions or stale plans are monitored', async () => {
  mocks.previewPlan.mockResolvedValue({ status: 'permission_required', question: 'Authorize and sync first.', candidates: [] });
  render(<MonitoringPlanSetup expectationId="expectation" refresh={vi.fn()} />);
  await userEvent.click(screen.getByRole('button', { name: 'Find authorized sources' }));
  expect(await screen.findByRole('status')).toHaveTextContent('Authorize and sync');
  expect(screen.queryByRole('button', { name: 'Confirm sources and monitoring' })).not.toBeInTheDocument();
});
it('shows reasons and synchronization details and invalidates edited queries', async () => {
  mocks.previewPlan.mockResolvedValue({ status: 'ready', question: 'Confirm.', candidates: [{ ...candidate, suggestion_reason: 'Exact order ID.', synced_at: '2026-10-12T12:00:00Z', sync_status: 'ready' }] });
  render(<MonitoringPlanSetup expectationId="expectation" refresh={vi.fn()} />);
  await userEvent.click(screen.getByRole('button', { name: 'Find authorized sources' }));
  await screen.findByRole('checkbox');
  expect(screen.getByText(/Exact order ID/)).toBeInTheDocument();
  expect(screen.getByText(/Last synchronized/)).toHaveTextContent('Sync: ready');
  await userEvent.click(screen.getByRole('checkbox'));
  await userEvent.type(screen.getByLabelText('Order ID (optional)'), '123');
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  expect(mocks.confirmPlan).not.toHaveBeenCalled();
});
it('prevents duplicate confirmation and exposes accessible loading', async () => {
  let finish!: (value: { status: string }) => void;
  mocks.confirmPlan.mockReturnValue(new Promise(resolve => { finish = resolve; }));
  render(<MonitoringPlanSetup expectationId="expectation" refresh={vi.fn()} />);
  await userEvent.click(screen.getByRole('button', { name: 'Find authorized sources' }));
  await userEvent.click(await screen.findByRole('checkbox'));
  await userEvent.dblClick(screen.getByRole('button', { name: 'Confirm sources and monitoring' }));
  expect(mocks.confirmPlan).toHaveBeenCalledOnce();
  expect(screen.getByLabelText('Order ID (optional)')).toBeDisabled();
  expect(screen.getByText('Reviewing authorized sources…')).toHaveAttribute('aria-live', 'polite');
  finish({ status: 'paused' });
  expect(await screen.findByText(/Monitoring remains paused/)).toBeInTheDocument();
});
it('requires fresh discovery after stale or revoked confirmation fails', async () => {
  mocks.confirmPlan.mockRejectedValue(new Error('Source authorization changed.'));
  render(<MonitoringPlanSetup expectationId="expectation" refresh={vi.fn()} />);
  await userEvent.click(screen.getByRole('button', { name: 'Find authorized sources' }));
  await userEvent.click(await screen.findByRole('checkbox'));
  await userEvent.click(screen.getByRole('button', { name: 'Confirm sources and monitoring' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Find authorized sources again');
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Find authorized sources' }));
  expect(await screen.findByRole('checkbox')).not.toBeChecked();
});
it('allows another source after unselecting the initial identity', async () => {
  mocks.previewPlan.mockResolvedValue({ status: 'clarification', question: 'Which order?', candidates: [candidate, { ...candidate, external_id: 'other', group_id: 'another', label: 'Another order' }] });
  render(<MonitoringPlanSetup expectationId="expectation" refresh={vi.fn()} />);
  await userEvent.click(screen.getByRole('button', { name: 'Find authorized sources' }));
  const choices = await screen.findAllByRole('checkbox');
  await userEvent.click(choices[0]);
  await userEvent.click(choices[0]);
  expect(choices[1]).toBeEnabled();
  await userEvent.click(choices[1]);
  await userEvent.click(screen.getByRole('button', { name: 'Confirm sources and monitoring' }));
  await waitFor(() => expect(mocks.confirmPlan).toHaveBeenCalledWith('expectation', {}, [{ sync_id: 'sync', external_id: 'other' }]));
});
