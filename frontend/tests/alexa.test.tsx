import { beforeEach, expect, it, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AlexaPage from '@/app/alexa/page';
import { routeAlexaPrompt, matchExpectations } from '@/lib/alexa-router';
import { McpClientError } from '@/lib/mcp/client';
import type { McpAction } from '@/lib/mcp/contracts';

const mocks = vi.hoisted(() => ({ request: vi.fn(), replace: vi.fn(), authenticated: true }));
vi.mock('next/navigation', () => ({ useRouter: () => ({ replace: mocks.replace }) }));
vi.mock('@/components/auth-provider', () => ({ useAuth: () => ({ loading: false, session: mocks.authenticated ? { user: { id: 'user-id' }, access_token: 'test-access-token' } : null }), useIdentity: () => ({ firstName: 'Taylor' }) }));
vi.mock('@/lib/mcp/client', async importOriginal => ({ ...await importOriginal<typeof import('@/lib/mcp/client')>(), requestMcp: mocks.request }));
const row = { id: '12345678-1234-4234-8234-123456789abc', claim: 'My next electricity bill will be lower', type: 'numeric_comparison', status: 'contradicted', metric: 'total_cost', created_at: '2026-10-01T20:00:00Z' };
const meta = { transport: 'streamable-http', initialized: true, toolsDiscovered: true, durationMs: 184 };
const tools = ['capture_expectation', 'get_expectation', 'list_expectations'].map(name => ({ name }));
function respond(action: McpAction) {
  if (action.action === 'list_tools') return { tools, meta };
  return { result: { structuredContent: action.tool === 'list_expectations' ? { expectations: [row], limit: 50, offset: 0 } : row }, meta: { ...meta, tool: action.tool } };
}
beforeEach(() => { vi.clearAllMocks(); mocks.authenticated = true; mocks.request.mockImplementation(async (_token, action) => respond(action)); });
async function ready() { render(<AlexaPage />); await screen.findByText('Connected to CountOn MCP'); }

it('gates signed-out users without calling MCP', async () => {
  mocks.authenticated = false; render(<AlexaPage />);
  await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith('/login'));
  expect(mocks.request).not.toHaveBeenCalled();
});
it.each(['What am I counting on?', 'What are my expectations?', 'What am I tracking?', "What's being monitored?", 'Show my expectations'])('routes list prompt: %s', prompt => { expect(routeAlexaPrompt(prompt).kind).toBe('list'); });
it.each(['Tell me about my electricity bill', 'Check my electricity bill', 'Tell me about my package', 'Tell me about the plumber', "What's happening with my dentist expectation?"])('routes detail prompt: %s', prompt => { expect(routeAlexaPrompt(prompt).kind).toBe('detail'); });
it('builds capture from the actual contract and honors a strict USD cap', () => {
  const intent = routeAlexaPrompt("I'm counting on my grocery bill staying under $120 this week", new Date('2026-10-08T12:00:00Z'));
  expect(intent.kind).toBe('capture');
  if (intent.kind !== 'capture') throw new Error('Expected capture');
  expect(intent.payload).toMatchObject({ type: 'numeric_comparison', metric: 'total_cost', comparison: 'less_than', target_value: 120, evidence_sources: [], materiality_threshold: 0 });
  expect(Number.isNaN(Date.parse(intent.payload.deadline!))).toBe(false);
  expect(intent.payload.deadline).toMatch(/Z$/);
});
it('asks for clarification rather than inventing unsupported conditions', () => {
  for (const phrase of ["I'm counting on my grocery bill staying under $120 this week unless I have guests", 'Save my rent expectation', "I'm counting on my grocery bill staying under €120 this week", "I'm counting on my grocery bill staying under $0 this week"]) expect(routeAlexaPrompt(phrase).kind).toBe('clarify');
});
it('matches actual claims and metrics and retains ambiguous matches', () => {
  expect(matchExpectations('electricity bill', [row])).toEqual([row]);
  expect(matchExpectations('plumber', [row])).toEqual([]);
  expect(matchExpectations('electricity bill', [row, { ...row, id: 'second-id' }])).toHaveLength(2);
});
it('discovers tools before claiming connectivity and greets the actual user', async () => {
  await ready(); expect(screen.getByText('Hi Taylor. What are you counting on?')).toBeInTheDocument();
  expect(mocks.request).toHaveBeenCalledWith('test-access-token', { action: 'list_tools' });
});
it('does not claim connected when initialization or discovery is incomplete', async () => {
  mocks.request.mockResolvedValue({ tools, meta: { ...meta, initialized: false } });
  render(<AlexaPage />); await screen.findByText('CountOn MCP unavailable');
  expect(screen.queryByText('Connected to CountOn MCP')).not.toBeInTheDocument();
});
it('renders real list fields and expandable MCP trace', async () => {
  await ready(); await userEvent.click(screen.getByRole('button', { name: 'What am I counting on?' }));
  await screen.findByText(row.claim); expect(screen.getByText('contradicted')).toBeInTheDocument();
  await userEvent.click(screen.getByText('MCP → list_expectations'));
  expect(screen.getByText('184 ms')).toBeInTheDocument(); expect(screen.getByText('Streamable HTTP')).toBeInTheDocument();
  expect(mocks.request).toHaveBeenLastCalledWith('test-access-token', { action: 'call_tool', tool: 'list_expectations', arguments: { request: { limit: 50, offset: 0 } } });
});
it('handles an empty list', async () => {
  mocks.request.mockImplementation(async (_token, action) => action.action === 'list_tools' ? respond(action) : { result: { structuredContent: { expectations: [] } }, meta: { ...meta, tool: 'list_expectations' } });
  await ready(); await userEvent.click(screen.getByRole('button', { name: 'What am I counting on?' }));
  await screen.findByText("You're not counting on anything yet.");
});
it('fetches detail using the real list ID and renders only returned fields', async () => {
  await ready(); await userEvent.click(screen.getByRole('button', { name: 'Tell me about my electricity bill' }));
  await screen.findByText('MCP → get_expectation');
  expect(mocks.request).toHaveBeenLastCalledWith('test-access-token', { action: 'call_tool', tool: 'get_expectation', arguments: { request: { expectation_id: row.id } } });
  expect(screen.getByText(row.claim)).toBeInTheDocument(); expect(screen.queryByText('$142.10')).not.toBeInTheDocument();
});
it('does not fabricate a missing detail match', async () => {
  await ready(); await userEvent.type(screen.getByLabelText('Message CountOn'), 'Tell me about my plumber'); await userEvent.click(screen.getByRole('button', { name: 'Send message' }));
  await screen.findByText("I couldn't find an expectation about that.");
  expect(mocks.request.mock.calls.some(([, action]) => action.tool === 'get_expectation')).toBe(false);
});
it('does not choose an arbitrary ID for ambiguous matches', async () => {
  mocks.request.mockImplementation(async (_token, action) => action.action === 'call_tool' && action.tool === 'list_expectations' ? { result: { structuredContent: { expectations: [row, { ...row, id: 'second-id' }] } }, meta: { ...meta, tool: 'list_expectations' } } : respond(action));
  await ready(); await userEvent.click(screen.getByRole('button', { name: 'Tell me about my electricity bill' }));
  await screen.findByText('I found more than one expectation about that. Could you use a more specific part of its claim?');
  expect(mocks.request.mock.calls.some(([, action]) => action.tool === 'get_expectation')).toBe(false);
});
it('saves through MCP and links the returned ID to CountOn', async () => {
  await ready(); await userEvent.click(screen.getByRole('button', { name: "I'm counting on my grocery bill staying under $120 this week" }));
  await screen.findByText('Saved to CountOn');
  expect(screen.getByRole('link', { name: 'View in CountOn' })).toHaveAttribute('href', `/expectations/${row.id}`);
  expect(screen.getByText('MCP → capture_expectation')).toBeInTheDocument();
  expect(mocks.request.mock.calls.at(-1)?.[1]).toMatchObject({ action: 'call_tool', tool: 'capture_expectation', arguments: { request: { target_value: 120, type: 'numeric_comparison' } } });
});
it.each([['TOOL_VALIDATION_ERROR', 'I need a little more information before I can save that.'], ['AUTH_EXPIRED', 'Your CountOn session expired. Please sign in again.'], ['MCP_UNAVAILABLE', 'CountOn is temporarily unavailable.']])('handles %s safely', async (code, message) => {
  await ready(); mocks.request.mockRejectedValue(new McpClientError(code as 'TOOL_VALIDATION_ERROR' | 'AUTH_EXPIRED' | 'MCP_UNAVAILABLE'));
  await userEvent.click(screen.getByRole('button', { name: "I'm counting on my grocery bill staying under $120 this week" }));
  await screen.findByText(message);
  if (code === 'AUTH_EXPIRED') expect(screen.getByRole('button', { name: 'Send message' })).toBeDisabled();
});
it('performs discovery and conversation only through the MCP helper, without direct HTTP calls', async () => {
  const fetcher = vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('Unexpected direct HTTP call'));
  try {
    await ready(); await userEvent.click(screen.getByRole('button', { name: 'What am I counting on?' }));
    await screen.findByText(row.claim);
    expect(mocks.request).toHaveBeenCalledTimes(2);
    expect(fetcher).not.toHaveBeenCalled();
  } finally { fetcher.mockRestore(); }
});
