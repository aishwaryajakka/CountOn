'use client';

import { useState } from 'react';
import { useResource } from '@/hooks/use-resource';
import { beeCli } from '@/lib/bee';
import { api } from '@/lib/api';
import type { BeeCliStatus, BeeImportCandidate, Expectation } from '@/lib/types';

export function BeeCliConnection() {
  const state = useResource(loadBeeCli);
  const status = state.data?.status ?? null;
  const candidates = state.data?.candidates ?? [];
  const expectations = state.data?.expectations ?? [];
  const [selected, setSelected] = useState<string[]>([]);
  const [expectation, setExpectation] = useState('');
  const [pairing, setPairing] = useState<{ pairing_code: string; expires_at: string } | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  async function createPairing() { setMessage(null); try { setPairing(await beeCli.pairing()); } catch { setMessage('Could not create a Bee CLI pairing code.'); } }
  async function importSelected() { if (!expectation || !selected.length) return; setMessage(null); try { const result = await beeCli.import(expectation, selected); setMessage(`Imported ${result.imported} selected Bee record(s). CountOn evaluated the persisted expectation.`); setSelected([]); state.reload(); } catch { setMessage('Bee import failed. Check the connection, selection, and expectation ownership.'); } }
  async function disconnect() { setMessage(null); try { const result = await beeCli.disconnect(); setPairing(null); setMessage(result.local_action); state.reload(); } catch { setMessage('Could not disconnect Bee CLI.'); } }

  return <section className="card" aria-labelledby="bee-cli-title">
    <div className="section-heading"><div><span className="overline">Optional live import</span><h2 id="bee-cli-title">Bee CLI</h2></div><span className={`badge ${status?.state === 'paired' || status?.state === 'import_enabled' ? 'monitoring' : status?.state === 'error' ? 'attention' : 'waiting'}`}>{status?.state.replaceAll('_', ' ') ?? 'checking'}</span></div>
    <p>Bee simulator is available separately. A live Bee account is connected only after the official local CLI is installed, authenticated, and paired.</p>
    {!status || ['not_paired', 'disconnected'].includes(status.state) ? <>
      <ol><li>Install: <code>npm install -g @beeai/cli</code></li><li>Check locally: <code>python -m app.integrations.bee.cli_bridge status</code></li><li>Authenticate if requested: <code>bee login</code></li></ol>
      <button className="button secondary" onClick={createPairing}>Create single-use pairing code</button>
      {pairing && <div className="soft-card" role="status"><p>Pair before {new Date(pairing.expires_at).toLocaleTimeString()}:</p><code>python -m app.integrations.bee.cli_bridge pair --api {'<API_ORIGIN>'} --code-stdin</code><p>One-time code: <code>{pairing.pairing_code}</code></p><p className="caption">Paste the code only into the bridge&apos;s hidden prompt. Do not paste Bee credentials into CountOn.</p></div>}
    </> : <>
      <p className="caption">CLI {status.cli_version ?? 'version unavailable'} · {status.last_sync_at ? `Last staged ${new Date(status.last_sync_at).toLocaleString()}` : 'No records staged yet'} · {status.pending_candidates} awaiting review</p>
      <p>Run <code>python -m app.integrations.bee.cli_bridge sync</code> locally to stage minimal summaries. Nothing is imported until you approve it here.</p>
      {candidates.map(candidate => <label key={candidate.id} className="soft-card"><input type="checkbox" checked={selected.includes(candidate.id)} onChange={event => setSelected(rows => event.target.checked ? [...rows, candidate.id] : rows.filter(id => id !== candidate.id))} /> <strong>{candidate.category}</strong> — {candidate.summary}</label>)}
      {!!candidates.length && <><label>Import into expectation<select value={expectation} onChange={event => setExpectation(event.target.value)}><option value="">Select an owned expectation</option>{expectations.map(row => <option key={row.id} value={row.id}>{row.claim}</option>)}</select></label><button className="button primary" disabled={!selected.length || !expectation} onClick={importSelected}>Approve selected evidence import</button></>}
      <button className="button secondary" onClick={disconnect}>Disconnect and revoke CountOn bridge</button>
    </>}
    {(message || state.error) && <p role="status">{message ?? 'Bee CLI status is unavailable.'}</p>}
  </section>;
}

async function loadBeeCli(signal: AbortSignal): Promise<{ status: BeeCliStatus; candidates: BeeImportCandidate[]; expectations: Expectation[] }> {
  const [status, candidates, expectations] = await Promise.all([beeCli.status(signal), beeCli.candidates(signal), api.expectations(signal)]);
  return { status, candidates, expectations: expectations.filter(row => !['resolved', 'cancelled'].includes(row.status)) };
}
