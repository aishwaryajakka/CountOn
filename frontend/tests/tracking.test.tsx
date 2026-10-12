import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { TrackingControls } from '@/components/tracking-controls';
import { NotificationPreferences } from '@/components/notification-preferences';
import { expectation } from './fixtures';
const mocks = vi.hoisted(() => ({ request: vi.fn() }));
vi.mock('@/lib/api', () => ({ api: { request: mocks.request } }));
const schedule = { status: 'pending', interval_seconds: 3600, next_run_at: '2026-10-16T17:00:00Z', last_run_at: null, recurring: false, max_evidence_age_seconds: 86400, max_attempts: 5, connection_id: null, window_start_at: null, provider_config: {} };
const prefs = { email_enabled: false, mismatch_enabled: true, deadline_enabled: false, connection_enabled: true, quiet_enabled: false, quiet_start_hour: 22, quiet_end_hour: 8, timezone: 'UTC' };
beforeEach(() => { vi.clearAllMocks(); mocks.request.mockImplementation((path: string) => Promise.resolve(path === '/notification-preferences' ? prefs : schedule)); });
it('pauses and resumes through the owned backend schedule', async () => {
  render(<TrackingControls expectation={expectation} refresh={vi.fn()} />);
  await userEvent.click(await screen.findByRole('button', { name: 'Pause tracking' }));
  await waitFor(() => expect(mocks.request).toHaveBeenCalledWith(`/expectations/${expectation.id}/monitoring`, expect.objectContaining({ method: 'PUT' })));
  const call = mocks.request.mock.calls.find(call => call[1]?.method === 'PUT');
  expect(JSON.parse(call![1].body)).toMatchObject({ status: 'paused', connection_id: null, outlook_rule: null });
});
it('edits the deadline and amount without adding identity or provider credentials', async () => {
  render(<TrackingControls expectation={expectation} refresh={vi.fn()} />);
  const amount = await screen.findByLabelText('Amount');
  await userEvent.clear(amount); await userEvent.type(amount, '150');
  const tolerance = screen.getByLabelText('Materiality tolerance (%)');
  await userEvent.clear(tolerance); await userEvent.type(tolerance, '0');
  await userEvent.click(screen.getByRole('button', { name: 'Save conditions' }));
  await waitFor(() => expect(mocks.request.mock.calls.some(call => call[1]?.method === 'PATCH')).toBe(true));
  const body = JSON.parse(mocks.request.mock.calls.find(call => call[1]?.method === 'PATCH')![1].body);
  expect(body).toMatchObject({ baseline: 150, materiality_threshold: 0 }); expect(body).not.toHaveProperty('user_id');
});
it('does not offer mutation for a cancelled expectation', async () => {
  render(<TrackingControls expectation={{ ...expectation, status: 'cancelled' }} refresh={vi.fn()} />);
  await screen.findByText(/Schedule: Pending/);
  expect(screen.queryByRole('button', { name: 'Pause tracking' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Save conditions' })).not.toBeInTheDocument();
});
it('saves opt-in preferences and quiet hours through authenticated API', async () => {
  render(<NotificationPreferences />);
  await userEvent.click(await screen.findByLabelText('Email me (opt-in)'));
  await userEvent.click(screen.getByLabelText('Quiet hours for email'));
  await userEvent.click(screen.getByRole('button', { name: 'Save preferences' }));
  const call = mocks.request.mock.calls.find(call => call[1]?.method === 'PUT');
  expect(JSON.parse(call![1].body)).toMatchObject({ email_enabled: true, quiet_enabled: true });
  expect(JSON.parse(call![1].body)).not.toHaveProperty('recipient');
});
it('reports deployment email configuration failure without a fake success', async () => {
  mocks.request.mockImplementation((_: string, options: RequestInit = {}) => options.method ? Promise.reject(new Error('Email notifications are not configured on this deployment')) : Promise.resolve(prefs));
  render(<NotificationPreferences />);
  await userEvent.click(await screen.findByLabelText('Email me (opt-in)'));
  await userEvent.click(screen.getByRole('button', { name: 'Save preferences' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Email notifications are not configured');
});
