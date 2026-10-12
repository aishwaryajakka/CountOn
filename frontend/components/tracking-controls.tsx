'use client';
import { useCallback, useState } from 'react';
import type { Expectation } from '@/lib/types';
import { monitoring } from '@/lib/monitoring';
import { useResource } from '@/hooks/use-resource';
import { ErrorState, Loading } from './ui';
import { humanize } from '@/lib/presentation';

export function TrackingControls({ expectation, refresh }: { expectation: Expectation; refresh: () => void }) {
  const load = useCallback((signal: AbortSignal) => monitoring.get(expectation.id, signal), [expectation.id]);
  const state = useResource(load, 30000);
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null);
  const [deadline, setDeadline] = useState(expectation.deadline ?? '');
  const [threshold, setThreshold] = useState(String(expectation.target_value ?? expectation.baseline ?? ''));
  const [tolerance, setTolerance] = useState(String(expectation.materiality_threshold * 100));
  const [comparison, setComparison] = useState(expectation.comparison ?? 'less_than');
  const terminal = ['cancelled', 'resolved'].includes(expectation.status);
  async function action(work: () => Promise<unknown>) {
    setBusy(true); setError(null);
    try { await work(); state.reload(); refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : 'Tracking could not be updated.'); }
    finally { setBusy(false); }
  }
  return <section className="card"><h2>Tracking health</h2>{state.loading ? <Loading /> : state.error ? <ErrorState error={state.error} retry={state.reload} /> : state.data && <>
    <p>Schedule: {humanize(state.data.status)} · every {Math.round(state.data.interval_seconds / 60)} minutes</p>
    <p className="caption">Last checked: {state.data.last_run_at ?? 'Not yet'}<br />Next check: {state.data.next_run_at}</p>
    {state.data.last_error && <p role="status">Monitoring needs attention: {humanize(state.data.last_error)}</p>}
    {!terminal && <div className="actions"><button className="button secondary" disabled={busy} onClick={() => action(() => monitoring.configure(expectation.id, state.data!, state.data!.status === 'paused' ? 'pending' : 'paused'))}>{state.data.status === 'paused' ? 'Resume tracking' : 'Pause tracking'}</button><button className="button ghost" disabled={busy} onClick={() => { if (window.confirm('Cancel tracking this expectation? Your history will be retained.')) void action(() => monitoring.update(expectation.id, { status: 'cancelled' })); }}>Cancel tracking</button></div>}
  </>}
  {!terminal && <form onSubmit={e => { e.preventDefault(); void action(() => {
    const changes: Partial<Expectation> = { deadline: deadline || null };
    if (expectation.type === 'numeric_comparison') {
      if (!threshold.trim() || !Number.isFinite(Number(threshold))) throw new Error('Enter a valid amount.');
      changes[expectation.target_value !== null ? 'target_value' : 'baseline'] = Number(threshold); changes.comparison = comparison;
      if (!tolerance.trim() || !Number.isFinite(Number(tolerance)) || Number(tolerance) < 0 || Number(tolerance) > 100) throw new Error('Enter a tolerance between 0 and 100 percent.');
      changes.materiality_threshold = Number(tolerance) / 100;
    }
    return monitoring.update(expectation.id, changes);
  }); }}><h3>Conditions</h3>{expectation.type === 'numeric_comparison' && <><label>Comparison<select value={comparison} onChange={e => setComparison(e.target.value as typeof comparison)}>{['less_than', 'less_than_or_equal', 'greater_than', 'greater_than_or_equal', 'equal', 'not_equal'].map(value => <option key={value} value={value}>{humanize(value)}</option>)}</select></label><label>Amount<input type="number" step="any" value={threshold} onChange={e => setThreshold(e.target.value)} required /></label><label>Materiality tolerance (%)<input type="number" step="any" min={0} max={100} value={tolerance} onChange={e => setTolerance(e.target.value)} required /></label></>}
  <label>Deadline (ISO timestamp with timezone)<input value={deadline} onChange={e => setDeadline(e.target.value)} placeholder="2026-10-16T17:00:00-05:00" /></label><p className="caption">Include a UTC offset to avoid daylight-saving ambiguity. Clear the field to remove the deadline.</p><button className="button secondary" disabled={busy}>Save conditions</button></form>}
  {error && <p role="alert" className="inline-error">{error}</p>}
  </section>;
}
