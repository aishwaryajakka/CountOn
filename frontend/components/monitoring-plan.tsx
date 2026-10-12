'use client';

import { useRef, useState } from 'react';
import { providers, type PlanQuery, type SourcePlan } from '@/lib/providers';

export function MonitoringPlanSetup({ expectationId, refresh }: { expectationId: string; refresh: () => void }) {
  const [plan, setPlan] = useState<SourcePlan | null>(null);
  const [query, setQuery] = useState<PlanQuery>({});
  const [usedQuery, setUsedQuery] = useState<PlanQuery>({});
  const [chosen, setChosen] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const inFlight = useRef(false);
  function changeQuery(next: PlanQuery) {
    setQuery(next); setPlan(null); setChosen([]); setMessage(null); setError(null);
  }
  async function preview() {
    if (inFlight.current) return;
    inFlight.current = true;
    setBusy(true); setError(null); setMessage(null); setChosen([]); setPlan(null);
    try { setPlan(await providers.previewPlan(expectationId, query)); setUsedQuery(query); }
    catch (e) { setError(e instanceof Error ? e.message : 'Could not review sources.'); }
    finally { inFlight.current = false; setBusy(false); }
  }
  async function confirm() {
    if (!plan || !chosen.length || inFlight.current) return;
    inFlight.current = true;
    setBusy(true); setError(null);
    try {
      const result = await providers.confirmPlan(expectationId, usedQuery, chosen.map(i => ({ sync_id: plan.candidates[i].sync_id, external_id: plan.candidates[i].external_id })));
      setMessage(result.status === 'paused' ? 'Sources saved. Monitoring remains paused.' : result.status === 'completed' ? 'Sources confirmed. Monitoring is complete.' : ['pending', 'running'].includes(result.status) ? 'Sources confirmed. Monitoring is scheduled.' : 'Sources saved. Monitoring needs attention; review its status.'); setPlan(null); setChosen([]); refresh();
    } catch (e) { setPlan(null); setChosen([]); setError(e instanceof Error ? e.message : 'Could not confirm this plan.'); }
    finally { inFlight.current = false; setBusy(false); }
  }
  return <div><h3>Review suggested sources</h3><p className="caption">CountOn searches your synchronized accounts. Select the exact order, event or thread before scheduling.</p>
    <label>Order ID (optional)<input disabled={busy} value={query.order_id ?? ''} onChange={e => changeQuery({ ...query, order_id: e.target.value || undefined })} /></label>
    <label>Calendar UID (optional)<input disabled={busy} value={query.calendar_uid ?? ''} onChange={e => changeQuery({ ...query, calendar_uid: e.target.value || undefined })} /></label>
    <label>Expected start (for unchanged meetings)<input disabled={busy} value={query.expected_start ?? ''} onChange={e => changeQuery({ ...query, expected_start: e.target.value || undefined })} placeholder="ISO timestamp with timezone" /></label>
    <button className="button secondary full" disabled={busy} onClick={preview}>Find authorized sources</button>
    {plan && <><p role="status">{plan.question}</p>{plan.candidates.map((c, i) => {
      const incompatible = chosen.some(j => plan.candidates[j].group_id !== c.group_id || (j !== i && plan.candidates[j].sync_id === c.sync_id));
      return <label key={`${c.sync_id}/${c.external_id}`}><input type="checkbox" checked={chosen.includes(i)} disabled={busy || incompatible || (chosen.length >= 4 && !chosen.includes(i))} onChange={e => setChosen(e.target.checked ? [...chosen, i] : chosen.filter(j => j !== i))} />{c.label} · {c.account_label}
        {c.suggestion_reason && <span className="caption"> · {c.suggestion_reason}</span>}
        {c.synced_at && <span className="caption"> · Last synchronized: {new Date(c.synced_at).toLocaleString()} · Sync: {c.sync_status}</span>}
      </label>;
    })}{!!plan.candidates.length && <button className="button primary full" disabled={busy || !chosen.length} onClick={confirm}>Confirm sources and monitoring</button>}</>}
    {busy && <p role="status" aria-live="polite">Reviewing authorized sources…</p>}{message && <p role="status">{message}</p>}{error && <p role="alert">{error} Find authorized sources again before confirming.</p>}
  </div>;
}
