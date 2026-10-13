import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  status: vi.fn(), pairing: vi.fn(), candidates: vi.fn(), import: vi.fn(), disconnect: vi.fn(), expectations: vi.fn(),
}));
vi.mock('@/lib/bee', () => ({ beeCli: { status: mocks.status, pairing: mocks.pairing, candidates: mocks.candidates, import: mocks.import, disconnect: mocks.disconnect } }));
vi.mock('@/lib/api', () => ({ api: { expectations: mocks.expectations } }));

import { BeeCliConnection } from '@/components/bee-cli-connection';
import { expectation } from './fixtures';

beforeEach(() => {
  vi.clearAllMocks();
  mocks.candidates.mockResolvedValue([]);
  mocks.expectations.mockResolvedValue([expectation]);
  mocks.pairing.mockResolvedValue({ pairing_code: 'fixture-pairing-code', expires_at: '2026-10-13T12:00:00Z' });
});

it('keeps simulator availability separate and shows official CLI setup before pairing', async () => {
  mocks.status.mockResolvedValue({ simulator_available: true, state: 'not_paired', connection_id: null, cli_version: null, last_sync_at: null, last_error: null, pending_candidates: 0 });
  render(<BeeCliConnection />);
  expect(await screen.findByText('not paired')).toBeInTheDocument();
  expect(screen.getByText(/npm install -g @beeai\/cli/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole('button', { name: 'Create single-use pairing code' }));
  expect(await screen.findByText(/fixture-pairing-code/)).toBeInTheDocument();
  expect(screen.getByText(/--code-stdin/)).toBeInTheDocument();
});

it('requires selected records and an expectation before importing', async () => {
  mocks.status.mockResolvedValue({ simulator_available: true, state: 'import_enabled', connection_id: 'connection', cli_version: '1.2.3', last_sync_at: '2026-10-13T11:00:00Z', last_error: null, pending_candidates: 1 });
  mocks.candidates.mockResolvedValue([{ id: 'candidate', connection_id: 'connection', external_id: 'todo:1', category: 'todo', summary: 'Plumber visit completed', observed_at: '2026-10-13T10:00:00Z', confidence: 0.8, status: 'pending' }]);
  mocks.import.mockResolvedValue({ imported: 1, duplicate: 0, evaluation_ids: ['evaluation'], binding_id: 'binding' });
  render(<BeeCliConnection />);
  await screen.findByText(/Plumber visit completed/);
  const approve = screen.getByRole('button', { name: 'Approve selected evidence import' });
  expect(approve).toBeDisabled();
  await userEvent.click(screen.getByRole('checkbox'));
  await userEvent.selectOptions(screen.getByLabelText('Import into expectation'), expectation.id);
  await userEvent.click(approve);
  await waitFor(() => expect(mocks.import).toHaveBeenCalledWith(expectation.id, ['candidate']));
});
