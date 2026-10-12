'use client';

import { use, useCallback, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, Check, Edit3, FlaskConical, Link2, Pause, Play, ShieldCheck, Sparkles } from 'lucide-react';
import { ArrowLeft, Link2, ShieldCheck } from 'lucide-react';
import { SourceBinding } from '@/components/source-binding';
import { TrackingControls } from '@/components/tracking-controls';
import { api } from '@/lib/api';
import { useResource } from '@/hooks/use-resource';
import { Badge, EmptyState, ErrorState, Loading } from '@/components/ui';
import { ComparisonCards, EvidenceCard, EvidenceContext, Timeline } from '@/components/expectation';
import { displayTitle, getExpectationPresentationStatus, humanize } from '@/lib/presentation';
import { ExpectationActionsModal } from '@/components/expectation-actions-modal';
import {
  generateRingEvent,
  ringEventToEvidence,
  generateBeeEvent,
  beeEventToEvidence,
  createUtilityBillEvidence,
} from '@/lib/simulators';

export default function ExpectationDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [manageOpen, setManageOpen] = useState(false);
  const [simBusy, setSimBusy] = useState(false);
  const [simMessage, setSimMessage] = useState<string | null>(null);

  const load = useCallback(async (signal: AbortSignal) => {
    const expectation = await api.expectation(id, signal);
    const [evidence, evaluations] = await Promise.all([
      api.evidence(id, signal),
      api.evaluations(id, signal),
    ]);
    const latest = evaluations.length ? await api.latest(id, signal) : null;
    return { expectation, evidence, evaluations, latest };
  }, [id]);

  const state = useResource(load);

  async function triggerSimulation(type: 'ring_match' | 'ring_mismatch' | 'bee_confirm' | 'bee_cancel' | 'utility_high' | 'utility_low') {
    if (!state.data) return;
    setSimBusy(true);
    setSimMessage(null);
    const exp = state.data.expectation;

    try {
      let evidencePayload;
      if (type === 'ring_match') {
        const raw = generateRingEvent('package_detected', { metric: exp.metric ?? 'package_detected' });
        evidencePayload = ringEventToEvidence(raw);
        setSimMessage('Simulated Ring package delivery (MATCH)');
      } else if (type === 'ring_mismatch') {
        const raw = generateRingEvent('package_not_detected', { metric: exp.metric ?? 'package_detected' });
        evidencePayload = ringEventToEvidence(raw);
        setSimMessage('Simulated Ring no package present (MISMATCH)');
      } else if (type === 'bee_confirm') {
        const raw = generateBeeEvent({
          speaker: 'Landlord',
          summary: 'Plumber is confirmed for Friday at 10:00 AM.',
          metric: exp.metric ?? 'appointment_confirmed',
          confirmed: true,
        });
        evidencePayload = beeEventToEvidence(raw);
        setSimMessage('Simulated Bee conversation confirmation (MATCH)');
      } else if (type === 'bee_cancel') {
        const raw = generateBeeEvent({
          speaker: 'Landlord',
          summary: 'The plumber had an emergency and cannot come on Friday. We need to reschedule.',
          metric: exp.metric ?? 'appointment_confirmed',
          confirmed: false,
        });
        evidencePayload = beeEventToEvidence(raw);
        setSimMessage('Simulated Bee conversation cancellation (MISMATCH)');
      } else if (type === 'utility_high') {
        evidencePayload = createUtilityBillEvidence(162);
        setSimMessage('Simulated utility bill of $162.00 (MISMATCH)');
      } else {
        evidencePayload = createUtilityBillEvidence(130);
        setSimMessage('Simulated utility bill of $130.00 (MATCH)');
      }

      await api.addEvidence(exp.id, evidencePayload);
      await api.evaluate(exp.id);
      state.reload();
    } catch (err) {
      setSimMessage(err instanceof Error ? `Simulation error: ${err.message}` : 'Failed to simulate');
    } finally {
      setSimBusy(false);
    }
  }

  const exp = state.data?.expectation;
  const isRing = exp?.evidence_sources.some((s) => s.toLowerCase().includes('ring')) || exp?.metric?.includes('package');
  const isBee = exp?.evidence_sources.some((s) => s.toLowerCase().includes('bee')) || exp?.claim.toLowerCase().includes('plumber') || exp?.claim.toLowerCase().includes('landlord');
  const isUtility = exp?.evidence_sources.some((s) => s.toLowerCase().includes('utility')) || exp?.metric === 'total_cost';

  return (
    <>
      <Link className="back-link" href="/expectations">
        <ArrowLeft size={17} />
        Back to Expectations
      </Link>

      {state.loading ? (
        <Loading label="Loading expectation" />
      ) : state.error ? (
        <ErrorState error={state.error} retry={state.reload} />
      ) : (
        state.data && (
          <>
            <header className="detail-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '1rem' }}>
              <div>
                <div className="title-badge">
                  <h1>{displayTitle(state.data.expectation)}</h1>
                  <Badge status={getExpectationPresentationStatus(state.data.expectation, state.data.latest)} />
                </div>
                <p className="claim">“{state.data.expectation.claim}”</p>
              </div>

              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <button className="button secondary" onClick={() => setManageOpen(true)}>
                  <Edit3 size={16} />
                  Manage / Edit
                </button>
              </div>
            </header>

            {simMessage && (
              <div
                className="soft-card"
                style={{
                  margin: '1rem 0',
                  padding: '0.75rem 1rem',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  color: 'var(--text-color, #1e293b)',
                }}
              >
                <Sparkles size={16} color="var(--primary, #2563eb)" />
                <span>{simMessage}</span>
              </div>
            )}

            <div className="detail-layout">
              <div className="detail-main">
                <ComparisonCards
                  expectation={state.data.expectation}
                  evaluation={state.data.latest}
                  evidence={state.data.evidence}
                />

                <section className="card explanation-card">
                  <EvidenceContext evaluation={state.data.latest} evidence={state.data.evidence} />
                  <p className="caption reasoning-note">
                    <ShieldCheck size={15} />
                    Deterministic evaluation · no AI-generated explanation
                  </p>
                </section>

                {/* Evidence Simulator Quick Controls for this Expectation */}
                <section className="card" style={{ padding: '1.25rem', backgroundColor: '#fbfcfd' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <FlaskConical size={18} color="var(--primary, #2563eb)" />
                      <strong style={{ fontSize: '0.95rem' }}>Simulate Evidence</strong>
                    </div>
                    <span className="caption">Test without physical devices</span>
                  </div>

                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    {isRing && (
                      <>
                        <button
                          className="button secondary"
                          onClick={() => triggerSimulation('ring_match')}
                          disabled={simBusy}
                        >
                          Simulate Package Delivered (MATCH)
                        </button>
                        <button
                          className="button ghost"
                          onClick={() => triggerSimulation('ring_mismatch')}
                          disabled={simBusy}
                        >
                          Simulate No Package (MISMATCH)
                        </button>
                      </>
                    )}

                    {isBee && (
                      <>
                        <button
                          className="button secondary"
                          onClick={() => triggerSimulation('bee_confirm')}
                          disabled={simBusy}
                        >
                          Simulate Plumber Confirmed (MATCH)
                        </button>
                        <button
                          className="button ghost"
                          onClick={() => triggerSimulation('bee_cancel')}
                          disabled={simBusy}
                        >
                          Simulate Plumber Cancelled (MISMATCH)
                        </button>
                      </>
                    )}

                    {isUtility && (
                      <>
                        <button
                          className="button secondary"
                          onClick={() => triggerSimulation('utility_low')}
                          disabled={simBusy}
                        >
                          Simulate Bill $130.00 (MATCH)
                        </button>
                        <button
                          className="button ghost"
                          onClick={() => triggerSimulation('utility_high')}
                          disabled={simBusy}
                        >
                          Simulate Bill $162.00 (MISMATCH)
                        </button>
                      </>
                    )}

                    {!isRing && !isBee && !isUtility && (
                      <>
                        <button
                          className="button secondary"
                          onClick={() => triggerSimulation('ring_match')}
                          disabled={simBusy}
                        >
                          Simulate Positive Confirmation
                        </button>
                        <button
                          className="button ghost"
                          onClick={() => triggerSimulation('ring_mismatch')}
                          disabled={simBusy}
                        >
                          Simulate Negative Observation
                        </button>
                      </>
                    )}
                  </div>
                </section>

                <section className="section">
                  <div className="section-heading">
                    <h2>Evidence gathered</h2>
                    <span className="caption">{state.data.evidence.length} recorded observations</span>
                  </div>
                  {state.data.evidence.length ? (
                    <div className="evidence-grid">
                      {state.data.evidence.map((item) => (
                        <EvidenceCard item={item} key={item.id} />
                      ))}
                    </div>
                  ) : (
                    <EmptyState
                      title="Waiting for evidence"
                      description="Observations for this expectation will appear here when they’re available."
                    />
                  )}
                </section>

                <Timeline
                  expectation={state.data.expectation}
                  evidence={state.data.evidence}
                  evaluations={state.data.evaluations}
                />
              </div>

              <aside className="detail-aside">
                <section className="card">
                  <h2>
                    <Link2 size={19} />
                    Sources used
                  </h2>
                  <p>Evidence sources associated with this expectation.</p>
                  <ul className="source-list">
                    {state.data.expectation.evidence_sources.map((source) => (
                      <li key={source}>
                        <span className="status-dot" />
                        {humanize(source)}
                      </li>
                    ))}
                  </ul>
                  {!state.data.expectation.evidence_sources.length && <p>No sources specified yet.</p>}
                  <Link className="button secondary full" href="/integrations">
                    View connected accounts
                  </Link>
                </section>

                <section className="soft-card">
                  <ShieldCheck size={23} />
                  <h3>A clear record</h3>
                  <p>The latest relevant observation is selected by when it was observed, even if it arrived later.</p>
                  <p className="caption">Context can explain what changed; it doesn’t prove why.</p>
                </section>
              </aside>
            </div>

            {/* Modal for Editing / Pausing / Resolving */}
            {exp && (
              <ExpectationActionsModal
                expectation={exp}
                isOpen={manageOpen}
                onClose={() => setManageOpen(false)}
                onUpdated={() => state.reload()}
              />
            )}
          </>
        )
      )}
    </>
  );
  const state = useResource(load, 30000);
  return <><Link className="back-link" href="/expectations"><ArrowLeft size={17} />Back to Expectations</Link>{state.loading ? <Loading label="Loading expectation" /> : state.error ? <ErrorState error={state.error} retry={state.reload} /> : state.data && <><header className="detail-header"><div className="title-badge"><h1>{displayTitle(state.data.expectation)}</h1><Badge status={getExpectationPresentationStatus(state.data.expectation, state.data.latest)} /></div><p className="claim">“{state.data.expectation.claim}”</p></header><div className="detail-layout"><div className="detail-main"><ComparisonCards expectation={state.data.expectation} evaluation={state.data.latest} evidence={state.data.evidence} /><section className="card explanation-card"><EvidenceContext evaluation={state.data.latest} evidence={state.data.evidence} /><p className="caption reasoning-note"><ShieldCheck size={15} />Deterministic evaluation · no AI-generated explanation</p></section><section className="section"><div className="section-heading"><h2>Evidence gathered</h2><span className="caption">{state.data.evidence.length} recorded observations</span></div>{state.data.evidence.length ? <div className="evidence-grid">{state.data.evidence.map(item => <EvidenceCard item={item} key={item.id} />)}</div> : <EmptyState title="Waiting for evidence" description="Observations for this expectation will appear here when they’re available." />}</section><Timeline expectation={state.data.expectation} evidence={state.data.evidence} evaluations={state.data.evaluations} /></div><aside className="detail-aside"><TrackingControls key={id} expectation={state.data.expectation} refresh={state.reload} /><section className="card"><h2><Link2 size={19} />Sources used</h2><p>Evidence sources associated with this expectation.</p><ul className="source-list">{state.data.expectation.evidence_sources.map(source => <li key={source}><span className="status-dot" />{humanize(source)}</li>)}</ul>{!state.data.expectation.evidence_sources.length && <p>No sources specified yet.</p>}<Link className="button secondary full" href="/integrations">View connected accounts</Link><SourceBinding expectationId={id} /></section><section className="soft-card"><ShieldCheck size={23} /><h3>A clear record</h3><p>The latest relevant observation is selected by when it was observed, even if it arrived later.</p><p className="caption">Context can explain what changed; it doesn’t prove why.</p></section></aside></div></>}</>;
}
