import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import { integration } from './fixtures';
const mocks = vi.hoisted(() => ({ request: vi.fn(), integrations: vi.fn() }));
vi.mock('@/lib/api', () => ({ api: mocks }));
import { providers, consentUrl } from '@/lib/providers';
import { ProviderAccount } from '@/components/provider-account';
import { SourceBinding } from '@/components/source-binding';

beforeEach(() => {
  // jsdom omits native dialog lifecycle; emulate only the standard open/close surface.
  Object.defineProperty(HTMLDialogElement.prototype, 'showModal', { configurable: true, value: function(this: HTMLDialogElement) { this.setAttribute('open', ''); } });
  Object.defineProperty(HTMLDialogElement.prototype, 'close', { configurable: true, value: function(this: HTMLDialogElement) { this.removeAttribute('open'); } });
  vi.clearAllMocks(); mocks.integrations.mockResolvedValue([]); mocks.request.mockResolvedValue([]); });
it('restricts consent navigation to official provider HTTPS authorities', () => {
  expect(consentUrl('https://accounts.google.com/o/oauth2/v2/auth?state=fixture')).toContain('accounts.google.com');
  for (const url of ['https://evil.test/auth', 'http://accounts.google.com/auth', 'https://user:secret@login.microsoftonline.com/auth']) expect(() => consentUrl(url)).toThrow('invalid consent');
});
it('uses existing authenticated API wrapper and owned nested source rules', async () => {
  await providers.bind('expectation', 'sync1', { kind: 'reply', sender: 'friend@example.test', thread_id: 'thread1' });
  expect(mocks.request).toHaveBeenCalledWith('/expectations/expectation/sources', { method: 'POST', body: JSON.stringify({ sync_id: 'sync1', rule: { kind: 'reply', sender: 'friend@example.test', thread_id: 'thread1' } }) });
  await providers.disconnect('account');
  expect(mocks.request).toHaveBeenLastCalledWith('/integrations/account/disconnect', { method: 'POST', body: JSON.stringify({ revoke: true, erase_evidence: false }) });
});
it('separates authorization from verified synchronization and queues inbox sync', async () => {
  mocks.request.mockResolvedValue([]);
  render(<ProviderAccount item={{ ...integration, metadata: { ...integration.metadata, demo: false, mock: false }, scopes: ['https://www.googleapis.com/auth/gmail.readonly'], credential_state: 'configured' }} reload={vi.fn()} />);
  expect(await screen.findByText(/Provider authorized/)).toHaveTextContent('No successful sync yet');
  await userEvent.click(screen.getByRole('button', { name: 'Sync inbox' }));
  await waitFor(() => expect(mocks.request).toHaveBeenCalledWith('/integrations/connection-id/sync', { method: 'POST', body: '{}' }));
  expect(await screen.findByRole('status')).toHaveTextContent('Inbox sync queued');
});
it('selects an authorized calendar before enrolling it', async () => {
  mocks.request.mockImplementation(async (path: string) => path.endsWith('/calendars') ? [{ id: 'primary', name: 'Work' }] : []);
  render(<ProviderAccount item={{ ...integration, connection_type: 'calendar', scopes: ['https://www.googleapis.com/auth/calendar.readonly'], credential_state: 'configured' }} reload={vi.fn()} />);
  await userEvent.click(await screen.findByRole('button', { name: 'Select calendar' }));
  await userEvent.selectOptions(await screen.findByLabelText('Calendar'), 'primary');
  await userEvent.click(screen.getByRole('button', { name: 'Synchronize calendar' }));
  await waitFor(() => expect(mocks.request).toHaveBeenCalledWith('/integrations/connection-id/sync', { method: 'POST', body: '{"calendar_id":"primary"}' }));
});
it('does not pretend metadata-only connections have sync permission', async () => {
  render(<ProviderAccount item={integration} reload={vi.fn()} />);
  expect(await screen.findByText(/Authorization required/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Sync inbox' })).toBeDisabled();
});
it('requires an explicitly selected synchronized source', async () => {
  render(<SourceBinding expectationId="expectation" />);
  expect(await screen.findByText('Authorize and sync an account first.')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Use this source' })).not.toBeInTheDocument();
});

it('reports disabled provider configuration before creating account records', async () => {
  const { ConnectAccountModal } = await import('@/components/integration');
  mocks.request.mockResolvedValue({ google: false, microsoft: false, automatic_sync: false, push: false });
  render(<ConnectAccountModal onClose={vi.fn()} />);
  await userEvent.click(screen.getAllByRole('button', { name: 'Connect' })[0]);
  expect(await screen.findByRole('alert')).toHaveTextContent('not configured');
  expect(mocks.request).toHaveBeenCalledTimes(1);
});

it('disconnects only after confirmation and shows provider revocation limits', async () => {
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  const reload = vi.fn();
  mocks.request.mockImplementation(async (path: string) => path.endsWith('/disconnect') ? { disconnected: true, provider_revoked: false, revocation_action: 'Remove the grant in Microsoft My Apps.' } : []);
  render(<ProviderAccount item={{ ...integration, provider: 'microsoft', credential_state: 'configured' }} reload={reload} />);
  await userEvent.click(await screen.findByRole('button', { name: 'Disconnect' }));
  expect(await screen.findByRole('status')).toHaveTextContent('Microsoft My Apps');
  expect(reload).toHaveBeenCalledOnce();
  vi.restoreAllMocks();
});


it('identifies legacy Outlook scopes that cannot authorize body synchronization', async () => {
  render(<ProviderAccount item={{ ...integration, provider: 'microsoft', credential_state: 'configured', scopes: ['Mail.ReadBasic', 'User.Read'] }} reload={vi.fn()} />);
  expect(await screen.findByText(/Source sync permission is missing/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Sync inbox' })).toBeDisabled();
  expect(screen.getByRole('button', { name: 'Reconnect' })).toBeEnabled();
});
