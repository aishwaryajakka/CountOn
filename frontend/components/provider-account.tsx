'use client';
import { useCallback, useState } from 'react';
import { providers, consentUrl } from '@/lib/providers';
import type { Integration } from '@/lib/types';
import { useResource } from '@/hooks/use-resource';
import { ErrorState, Loading } from './ui';

export function ProviderAccount({ item, reload }: { item: Integration; reload: () => void }) {
  const load = useCallback((signal: AbortSignal) => providers.states(item.id, signal), [item.id]);
  const state = useResource(load);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [calendars, setCalendars] = useState<{ id: string; name: string }[]>([]);
  const expectedScope = item.provider === 'google' ? `https://www.googleapis.com/auth/${item.connection_type === 'calendar' ? 'calendar' : 'gmail'}.readonly` : item.connection_type === 'calendar' ? 'calendars.read' : 'mail.read';
  const hasScope = item.scopes.some(scope => scope.replace('https://graph.microsoft.com/', '').toLowerCase() === expectedScope.toLowerCase());
  const [selected, setSelected] = useState('');
  async function act(action: () => Promise<void>) {
    setBusy(true); setError(null); setNotice(null);
    try { await action(); } catch (e) { setError(e instanceof Error ? e.message : 'The source is unavailable. Try again.'); } finally { setBusy(false); }
  }
  return <div><p className="caption">{item.credential_state === 'configured' ? 'Provider authorized' : 'Authorization required'} · {state.data?.some(s => s.last_success_at) ? 'Synchronization verified' : 'No successful sync yet'}</p>{state.loading ? <Loading label="Checking source health" /> : state.error ? <ErrorState error={state.error} retry={state.reload} /> : state.data?.map(s => <p className="caption" key={s.id}>{s.stream} · {s.status} · {s.last_error ?? (s.last_success_at ? `Last success ${new Date(s.last_success_at).toLocaleString()}` : 'Awaiting worker')} <button className="text-link" disabled={busy} onClick={() => act(async () => { await providers.run(s.id); setNotice('Sync queued. Refresh after the provider worker runs.'); state.reload(); })}>Sync now</button></p>)}
    <p className="caption">{item.credential_state === 'configured' && !hasScope ? 'Source sync permission is missing. Reconnect to approve read-only access.' : 'Sync reads only sources you select.'}</p><div className="modal-actions"><button className="button secondary" disabled={busy} onClick={() => act(async () => { const result = await providers.authorize(item.id); window.location.assign(consentUrl(result.authorization_url)); })}>{item.credential_state === 'configured' ? 'Reconnect' : 'Authorize'}</button><button className="button secondary" disabled={busy || item.credential_state !== 'configured' || !hasScope} onClick={() => act(async () => { if (item.connection_type === 'calendar') { setCalendars(await providers.calendars(item.id)); } else { await providers.sync(item.id); setNotice('Inbox sync queued.'); state.reload(); } })}>{item.connection_type === 'calendar' ? 'Select calendar' : 'Sync inbox'}</button><button className="text-link" disabled={busy} onClick={() => { if (window.confirm('Disconnect this account and remove its sync cache and source bindings? Saved expectation evidence is retained.')) void act(async () => { const result = await providers.disconnect(item.id); setNotice(result.provider_revoked ? 'Access revoked and account disconnected.' : result.revocation_action); reload(); state.reload(); }); }}>Disconnect</button></div>
    {calendars.length > 0 && <div><label>Calendar<select value={selected} onChange={e => setSelected(e.target.value)}><option value="">Choose a calendar</option>{calendars.map(c => <option value={c.id} key={c.id}>{c.name}</option>)}</select></label><button className="button primary" disabled={busy || !selected} onClick={() => act(async () => { await providers.sync(item.id, selected); setNotice('Calendar sync queued.'); state.reload(); })}>Synchronize calendar</button></div>}{error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}</div>;
}
