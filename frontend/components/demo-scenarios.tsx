'use client';

import { useRef, useState } from 'react';
import Link from 'next/link';
import { ArrowRight, Camera, Lightbulb, Mic } from 'lucide-react';
import { useAuth, useIdentity } from './auth-provider';
import { Badge, IconBox } from './ui';
import { api } from '@/lib/api';
import { requestAgent } from '@/lib/agent/client';
import { demoExpectation, demoScenarios, loadDemoSnapshot, submitDemoEvidence, type DemoSnapshot } from '@/lib/demo-scenarios';
import { auditActionLabel, auditSourceLabel, evidenceSourceLabel, evidenceValue, formatDate, getExpectationPresentationStatus, number } from '@/lib/presentation';

function ScenarioCard({ scenario, onSaved }: { scenario: typeof demoScenarios[number]; onSaved: () => void }) {
  const { session } = useAuth();
  const { timeZone } = useIdentity();
  const started = useRef(false);
  const [attempted, setAttempted] = useState(false);
  const [id, setId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState('');
  const [snapshot, setSnapshot] = useState<DemoSnapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [answer, setAnswer] = useState<{ evaluationId: string; text: string } | null>(null);
  const [explanationError, setExplanationError] = useState<string | null>(null);

  async function refresh(ownedId: string) {
    const saved = await loadDemoSnapshot(ownedId);
    setSnapshot(saved);
    return saved;
  }
  async function run() {
    // Synchronous guard also covers two clicks before React re-renders. There is
    // no automatic mutation retry after an ambiguous network failure.
    if (started.current) return;
    started.current = true;
    setAttempted(true);
    setBusy(true); setError(null); setPhase('Creating expectation…');
    try {
      const created = await api.createExpectation(demoExpectation(scenario.id));
      setId(created.id);
      setPhase('Saving SIMULATED evidence and evaluating…');
      await submitDemoEvidence(scenario.id, created.id);
      onSaved();
      const saved = await refresh(created.id);
      if (scenario.id === 'electricity' && saved.evaluation?.result === 'MISMATCH') {
        setPhase('Asking CountOn why…');
        try {
          const explanation = await requestAgent(session?.access_token, {
            text: 'Why did it fail?', expectation_id: created.id, session_reference: null,
          });
          if (explanation.status === 'SUCCESS' && explanation.action === 'EXPLAIN_MISMATCH') {
            setAnswer({ evaluationId: saved.evaluation.id, text: explanation.answer });
            await refresh(created.id);
          } else setExplanationError(explanation.answer);
        } catch {
          setExplanationError('The result is saved. Explanation is unavailable just now; open the expectation to try again.');
        }
      }
    } catch {
      setError('The run could not finish. Check the saved expectation or your Expectations list before starting again. Refresh reads records only; it does not retry a save.');
    } finally { setBusy(false); setPhase(''); onSaved(); }
  }
  async function reload() {
    if (!id) return;
    setBusy(true); setError(null);
    try { await refresh(id); onSaved(); }
    catch { setError('Saved records could not be loaded. Open the expectation or try refreshing again.'); }
    finally { setBusy(false); }
  }

  const result = snapshot?.evaluation;
  const target = result?.expected.target;
  const observed = result?.observed.value;
  // Presentation arithmetic only. The verdict always comes from the evaluator.
  const over = typeof target === 'number' && typeof observed === 'number' && result?.expected.comparison === 'less_than' && observed > target ? observed - target : null;
  const notices = snapshot?.notifications.filter(item => item.type === 'expectation_mismatch') ?? [];
  const icon = scenario.id === 'electricity' ? Lightbulb : scenario.id === 'package' ? Camera : Mic;
  return <article className="card" aria-labelledby={`scenario-${scenario.id}`} style={{ display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 }}>
    <div className="section-heading"><IconBox icon={icon} /><span className="overline">SIMULATED DEMO</span></div>
    <h2 id={`scenario-${scenario.id}`}>{scenario.title}</h2>
    <p>{scenario.claim}</p>
    <p className="caption">Evidence: {scenario.source}</p>
    <p className="caption">Expected scenario outcome: {scenario.expected}</p>
    <button className="button primary" onClick={() => void run()} disabled={busy || attempted} style={{ marginTop: 'auto' }}>{busy ? phase || 'Refreshing…' : scenario.button}<ArrowRight size={16} aria-hidden="true" /></button>
    {phase && <p role="status" className="caption">{phase}</p>}
    {error && <p role="alert">{error}</p>}
    {id && <><Link className="text-link" href={`/expectations/${id}`}>Open created expectation</Link><p className="caption" style={{ overflowWrap: 'anywhere' }}>Expectation ID: {id}</p><button className="button secondary" disabled={busy} onClick={() => void reload()}>Refresh saved result</button></>}
    {snapshot && <section aria-label="Persisted demo result" aria-live="polite" style={{ borderTop: '1px solid var(--color-border, #e6ebf2)', paddingTop: 16 }}>
      <p className="overline">Saved backend result</p>
      <Badge status={getExpectationPresentationStatus(snapshot.expectation, result)} />
      <h3>{result?.result ?? 'No evaluation recorded'}</h3>
      <p className="caption">Expectation status: {snapshot.expectation.status}</p>
      {snapshot.expectation.deadline && <p className="caption">Deadline: {formatDate(snapshot.expectation.deadline, timeZone)}</p>}
      {typeof target === 'number' && <p>Expected: {result?.expected.comparison === 'less_than' ? '< ' : ''}{number(target, 'USD')}</p>}
      {typeof observed === 'number' && <p>Observed: {number(observed, 'USD')}</p>}
      {over !== null && <p>Difference: {number(over, 'USD')} over target</p>}
      {result?.result === 'MATCH' && notices.length === 0 && <p>No alert needed. Silence is success.</p>}
      {result?.result === 'UNKNOWN' && <p>{scenario.id === 'bee' ? 'Commitment observed. Arrival not yet confirmed. ' : ''}Still watching.</p>}
      <p>{notices.length ? `Mismatch notifications: ${notices.length}` : 'No mismatch notification recorded.'}</p>
      {notices.map(item => <p className="caption" key={item.id} style={{ overflowWrap: 'anywhere' }}>Notification {item.id} · {item.status} · {item.channel}</p>)}
      {result && <p className="caption" style={{ overflowWrap: 'anywhere' }}>Evaluation ID: {result.id}</p>}
      {scenario.id === 'electricity' && result?.result === 'MISMATCH' && <div className="quiet-note" style={{ display: 'block' }}><strong>Why?</strong><p>{answer?.evaluationId === result.id ? answer.text : explanationError ?? 'Open the expectation to request an explanation.'}</p></div>}
      <details><summary>Evidence &amp; provenance ({snapshot.evidence.length})</summary>
        {snapshot.evidence.map(item => <div key={item.id} style={{ marginTop: 12, overflowWrap: 'anywhere' }}><strong>{evidenceSourceLabel(item)}</strong><p>{evidenceValue(item, timeZone)}</p><p className="caption">Evidence ID: {item.id}</p><p className="caption">Provenance: {typeof item.raw_data.provenance === 'string' ? item.raw_data.provenance : 'User-submitted'}{item.raw_data.category === 'DEMO' ? ' · DEMO' : ''}</p><time className="caption" dateTime={item.observed_at}>{formatDate(item.observed_at, timeZone)}</time></div>)}
      </details>
      <details><summary>Evaluation history ({snapshot.evaluations.length})</summary>{snapshot.evaluations.map(item => <p className="caption" key={item.id}>{item.result} · {formatDate(item.created_at, timeZone)}</p>)}</details>
      <details><summary>Activity timeline ({snapshot.activity.length})</summary>{snapshot.activity.length ? <ol>{[...snapshot.activity].sort((a, b) => a.occurred_at.localeCompare(b.occurred_at)).map(item => <li key={item.audit_event_id}><p>{auditActionLabel(item)}</p><p className="caption">{auditSourceLabel(item)} · {formatDate(item.occurred_at, timeZone)}</p></li>)}</ol> : <p>No audit events returned.</p>}</details>
    </section>}
  </article>;
}

export function DemoScenarios({ onSaved }: { onSaved: () => void }) {
  const { session } = useAuth();
  // Never retain another account's local run references across an auth change.
  return <section aria-label="Three CountOn demo scenarios" className="section">
    <div className="section-heading"><h2>Three moments of trust</h2><span className="caption">Real records. Demonstration evidence.</span></div>
    <p>Running a demo creates one normal expectation and approves its named demo source for your account. Evidence is SIMULATED, not a live Ring, Bee or mailbox import. Records remain visible in your dashboard.</p>
    <p className="caption">Friday means the upcoming Friday in your browser’s timezone. A positive Ring observation is used; absence never proves nondelivery. Bee records a commitment, not its fulfillment.</p>
    <p className="caption">In-app alerts respect your saved notification preferences. Refresh reads saved records; it never creates another demo.</p>
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(100%, 280px), 1fr))', gap: 20, margin: '24px 0 40px' }}>{demoScenarios.map(scenario => <ScenarioCard key={`${session?.user.id ?? 'signed-out'}:${scenario.id}`} scenario={scenario} onSaved={onSaved} />)}</div>
  </section>;
}
