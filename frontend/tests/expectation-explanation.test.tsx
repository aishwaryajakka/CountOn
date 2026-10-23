import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { ExpectationExplanation } from '@/components/expectation-explanation';
import { AgentClientError } from '@/lib/agent/client';
const mocks = vi.hoisted(() => ({ agent: vi.fn() }));
vi.mock('@/components/auth-provider', () => ({
  useAuth: () => ({ session: { access_token: 'private-fixture-token' } }),
  useIdentity: () => ({ timeZone: 'UTC' }),
}));
vi.mock('@/lib/agent/client', async original => ({ ...await original<typeof import('@/lib/agent/client')>(), requestAgent: mocks.agent }));
beforeEach(() => { vi.clearAllMocks(); });

it('requests an owned explanation through the same server agent route, never a browser-selected tool', async () => {
  mocks.agent.mockResolvedValue({ status: 'SUCCESS', action: 'EXPLAIN_MISMATCH', answer: 'The recorded bill was higher; there is not enough supporting evidence to identify the cause.' });
  const recorded = vi.fn();
  const view = render(<ExpectationExplanation expectationId="owned-record" record={null} loaded recorded={recorded} />);
  expect(mocks.agent).not.toHaveBeenCalled(); // Rendering/polling does not invoke Bedrock.
  await userEvent.click(screen.getByRole('button', { name: 'Get grounded explanation' }));
  expect(await screen.findByRole('status')).toHaveTextContent('The recorded bill was higher');
  expect(mocks.agent).toHaveBeenCalledExactlyOnceWith('private-fixture-token', {
    text: 'Why did it fail?', session_reference: null, expectation_id: 'owned-record',
  });
  expect(recorded).toHaveBeenCalledOnce();
  view.rerender(<ExpectationExplanation expectationId="owned-record" record={null} loaded={false} recorded={recorded} />);
  expect(screen.getByRole('status')).toHaveTextContent('The recorded bill was higher');
  expect(document.body.textContent).not.toContain('private-fixture-token');
});

it('shows session failure safely without fabricating an explanation', async () => {
  mocks.agent.mockRejectedValue(new AgentClientError('AUTH_EXPIRED'));
  render(<ExpectationExplanation expectationId="owned-record" record={null} loaded recorded={vi.fn()} />);
  await userEvent.click(screen.getByRole('button', { name: 'Get grounded explanation' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Your CountOn session expired');
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
  expect(mocks.agent).toHaveBeenCalledOnce();
});
