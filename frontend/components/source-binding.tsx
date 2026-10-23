'use client';
import { useCallback, useState } from 'react';
import { api } from '@/lib/api';
import { providers, type SourceEvent, type SourceRule, type SyncState } from '@/lib/providers';
import { useResource } from '@/hooks/use-resource';
import { ErrorState, Loading } from './ui';
import { MonitoringPlanSetup } from './monitoring-plan';

export function SourceBinding({ expectationId, onUpdated }: { expectationId: string; onUpdated?: () => void }) {
  const load = useCallback(async (signal: AbortSignal) => {
    const [accounts, bindings] = await Promise.all([api.integrations(signal), providers.bindings(expectationId, signal)]);
    const choices: (SyncState & { name: string; calendar: boolean })[] = [];
    for (const account of accounts.filter(a => ['google', 'microsoft'].includes(a.provider) && a.credential_state === 'configured')) {
      for (const sync of await providers.states(account.id, signal)) choices.push({ ...sync, name: `${account.display_name ?? `${account.provider} ${account.connection_type}`} · ${account.external_account_id ?? account.id}`, calendar: account.connection_type === 'calendar' });
    }
    return { choices, bindings };
  }, [expectationId]);
  const state = useResource(load, 30000);
  function refresh() { state.reload(); onUpdated?.(); }
  const [selected, setSelected] = useState(''); const [events, setEvents] = useState<SourceEvent[]>([]); const [event, setEvent] = useState('');
  const [kind, setKind] = useState<SourceRule['kind']>('bill'); const [sender, setSender] = useState(''); const [subject, setSubject] = useState(''); const [thread, setThread] = useState(''); const [order, setOrder] = useState(''); const [expectedStart, setExpectedStart] = useState('');
  const [timezone, setTimezone] = useState('UTC'); const [recipient, setRecipient] = useState(''); const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null);
  const choice = state.data?.choices.find(c => c.id === selected);
  async function act(action: () => Promise<void>) { setBusy(true); setError(null); try { await action(); } catch (e) { setError(e instanceof Error ? e.message : 'Could not update the source.'); } finally { setBusy(false); } }
  return <div><h3>Bind a synchronized source</h3><p className="caption">Choose the exact event or sender/topic. Email facts are reports, not independently verified delivery.</p>{state.loading ? <Loading /> : state.error ? <ErrorState error={state.error} retry={state.reload} /> : <>
    <MonitoringPlanSetup expectationId={expectationId} refresh={refresh} />
    {state.data && state.data.bindings.length > 1 && <p role="status">Multiple sources require the same exact order or calendar occurrence. Unrelated, stale or conflicting sources keep monitoring unknown.</p>}{state.data?.bindings.map(b => <p key={b.id}>{b.rule.kind} source <button className="text-link" disabled={busy} onClick={() => act(async () => { await providers.unbind(expectationId, b.id); refresh(); })}>Remove binding</button></p>)}
    <label>Account source<select disabled={busy} value={selected} onChange={e => { const id = e.target.value; setSelected(id); setEvent(''); setEvents([]); if (id) void act(async () => setEvents(await providers.events(id))); }}><option value="">Select source</option>{state.data?.choices.map(c => <option value={c.id} key={c.id}>{c.name} · {c.stream}</option>)}</select></label>
    {choice && <><p className="caption" role="status">Sync: {choice.status} · Last synchronized: {choice.last_success_at ? new Date(choice.last_success_at).toLocaleString() : 'Not yet synchronized'}</p>{choice.calendar ? <><label>Exact event<select value={event} onChange={e => setEvent(e.target.value)}><option value="">Select an event</option>{events.filter(e => !e.facts.unavailable).map(e => <option key={e.id} value={e.id}>{e.facts.title ?? 'Event'} · {e.facts.start}</option>)}</select></label><label>Expected start (optional ISO timestamp, for event_unchanged)<input value={expectedStart} onChange={e => setExpectedStart(e.target.value)} placeholder="2026-10-16T09:00:00-05:00" /></label></> : <><label>Evidence kind<select value={kind} onChange={e => setKind(e.target.value as SourceRule['kind'])}>{['bill', 'reply', 'commitment', 'order'].map(k => <option key={k}>{k}</option>)}</select></label><label>Exact sender<input type="email" value={sender} onChange={e => setSender(e.target.value)} /></label><label>Recipient (optional exact address)<input type="email" value={recipient} onChange={e => setRecipient(e.target.value)} /></label><label>Message ID (optional exact ID)<input value={message} onChange={e => setMessage(e.target.value)} /></label><label>Source timezone (for date-only shipping estimates)<input value={timezone} onChange={e => setTimezone(e.target.value)} placeholder="America/Chicago" /></label><label>Subject contains<input minLength={3} value={subject} onChange={e => setSubject(e.target.value)} /></label>{kind === 'reply' && <p className="caption">Missing-reply checks require continuous sync from before the expectation started. A later first scan, lost cursor or unavailable messages keep the outcome unknown.</p>}<label>Thread ID (required for replies)<input value={thread} onChange={e => setThread(e.target.value)} /></label><label>Order ID (required for orders)<input value={order} onChange={e => setOrder(e.target.value)} placeholder="123-1234567-1234567" /></label><p className="caption">Thread IDs are shown below for synchronized messages.</p>{events.slice(0, 5).map(e => <p className="caption" key={e.id}>{e.facts.subject} · {e.facts.sender} · Thread: {e.facts.thread_id}</p>)}</>}
    <button className="button primary full" disabled={busy || (choice.calendar ? !event : !sender || !(subject || thread || order))} onClick={() => act(async () => { const rule: SourceRule = choice.calendar ? { kind: 'calendar', event_id: event, ...(expectedStart ? { expected_start: expectedStart } : {}) } : { kind, sender, timezone, ...(recipient ? { recipient } : {}), ...(message ? { message_id: message } : {}), ...(subject ? { subject_contains: subject } : {}), ...(thread ? { thread_id: thread } : {}), ...(order ? { order_id: order } : {}) }; await providers.bind(expectationId, selected, rule); refresh(); })}>Use this source</button></>}
    {!state.data?.choices.length && <p className="caption">Authorize and sync an account first.</p>}</>}{error && <p role="alert">{error}</p>}</div>;
}
