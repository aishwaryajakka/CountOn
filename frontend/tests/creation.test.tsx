import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
const mocks = vi.hoisted(() => ({ create: vi.fn(), reload: vi.fn(), push: vi.fn() }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ push: mocks.push }) }));
vi.mock('@/components/app-shell', () => ({ useBoard: () => ({ reload: mocks.reload }) }));
vi.mock('@/lib/api', async original => {
  const actual = await original<typeof import('@/lib/api')>();
  return { ...actual, api: { createExpectation: mocks.create } };
});
import Create from '@/app/(workspace)/expectations/new/page';
beforeEach(() => { vi.clearAllMocks(); mocks.create.mockResolvedValue({ id: 'saved-fixture' }); });
it('keeps manual setup explicit and saves only after the user confirms the preview', async () => {
  const user = userEvent.setup(); render(<Create />);
  await user.type(screen.getByLabelText('In your own words'), 'My electricity bill will be below $150');
  await user.click(screen.getByRole('button', { name: /Count on this/ }));
  expect(screen.getByRole('link', { name: 'Use conversational setup' })).toHaveAttribute('href', '/alexa');
  expect(screen.queryByText(/Automatic interpretation is coming later/)).not.toBeInTheDocument();
  await user.type(screen.getByLabelText('Metric to watch'), 'total_cost');
  await user.type(screen.getByLabelText('Target value'), '150');
  await user.click(screen.getByRole('button', { name: /Review expectation/ }));
  expect(mocks.create).not.toHaveBeenCalled();
  expect(screen.getByText(/connect an authorized source/)).toBeInTheDocument();
  await user.click(screen.getByRole('button', { name: /Start monitoring/ }));
  await waitFor(() => expect(mocks.create).toHaveBeenCalledExactlyOnceWith(expect.objectContaining({ metric: 'total_cost', target_value: 150 })));
  expect(mocks.push).toHaveBeenCalledWith('/expectations/saved-fixture');
});
it('describes supported time checks without promising an outcome from missing evidence', async () => {
  const user = userEvent.setup(); render(<Create />);
  await user.type(screen.getByLabelText('In your own words'), 'My package will arrive before the deadline');
  await user.click(screen.getByRole('button', { name: /Count on this/ }));
  await user.selectOptions(screen.getByLabelText('What kind of check?'), 'temporal');
  expect(screen.getByText(/need a deadline and supported evidence source/)).toBeInTheDocument();
  expect(screen.getByText(/missing evidence remains unknown/)).toBeInTheDocument();
  expect(mocks.create).not.toHaveBeenCalled();
});
