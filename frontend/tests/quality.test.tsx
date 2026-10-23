import { render, screen } from '@testing-library/react';
import { beforeEach, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ auditEvents: vi.fn() }));
vi.mock('@/lib/api', async original => ({ ...await original<typeof import('@/lib/api')>(), api: mocks }));
import Quality from '@/app/(workspace)/quality/page';
beforeEach(() => { vi.clearAllMocks(); });
it('loads actual owned history without inventing a review queue or benchmarks', async () => {
  mocks.auditEvents.mockResolvedValue([{ id: 'owned-event', event_type: 'EXPLANATION_GENERATED' }]);
  render(<Quality />);
  expect(await screen.findByText('1 explanation events in your audit history.')).toBeInTheDocument();
  expect(mocks.auditEvents).toHaveBeenCalledWith({}, expect.any(AbortSignal));
  expect(screen.getByText(/cloud benchmark API are not implemented/)).toBeInTheDocument();
  expect(screen.getByRole('link', { name: 'Connected Accounts' })).toHaveAttribute('href', '/integrations');
});
it('shows a retry on an actual failure instead of presenting an empty successful result', async () => {
  mocks.auditEvents.mockRejectedValue(new Error('unavailable'));
  render(<Quality />);
  expect(await screen.findByRole('button', { name: /Try again/ })).toBeInTheDocument();
  expect(screen.queryByText('0 explanation events in your audit history.')).not.toBeInTheDocument();
});
