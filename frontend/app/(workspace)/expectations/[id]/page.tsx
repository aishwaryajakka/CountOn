'use client';

import { use, useCallback, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, Edit3, FlaskConical, Link2, ShieldCheck, Sparkles } from 'lucide-react';
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

  const state = useResource(load, 30000);

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

      } else if (type === 'ring_mismatch') {
        const raw = generateRingEvent('package_not_detected', { metric: exp.metric ?? 'package_detected' });
        evidencePayload = ringEventToEvidence(raw);

      } else if (type === 'bee_confirm') {
        const raw = generateBeeEvent({
          speaker: 'Landlord',
          summary: 'Plumber is confirmed for Friday at 10:00 AM.',
          metric: exp.metric ?? 'appointment_confirmed',
          confirmed: true,
        });
        evidencePayload = beeEventToEvidence(raw);

      } else if (type === 'bee_cancel') {
        const raw = generateBeeEvent({
          speaker: 'Landlord',
          summary: 'The plumber had an emergency and cannot come on Friday. We need to reschedule.',
          metric: exp.metric ?? 'appointment_confirmed',
          confirmed: false,
        });
        evidencePayload = beeEventToEvidence(raw);

      } else if (type === 'utility_high') {
        evidencePayload = createUtilityBillEvidence(162);

      } else {
        evidencePayload = createUtilityBillEvidence(130);

      }

      await api.addEvidence(exp.id, evidencePayload);
      const evaluation = await api.evaluate(exp.id, `simulation:${evidencePayload.external_event_id}`);
      setSimMessage(`SIMULATED evidence · Backend evaluation: ${evaluation.result}`);
      state.reload();
    } catch (err) {
      setSimMessage(err instanceof Error ? `Simulation error: ${err.message}` : 'Failed to simulate');
    } finally {
      setSimBusy(false);
    }
  }

  const exp = state.data?.expectation;
  const active = exp && !['resolved', 'cancelled'].includes(exp.status);
  const isRing = active && ['boolean', 'event', 'temporal'].includes(exp.type) && ['package_detected', 'delivered', 'package_delivery', 'delivery_reported'].includes(exp.metric ?? '');
  const isBee = active && exp.type === 'boolean' && exp.metric === 'appointment_confirmed';
  const isUtility = active && exp.type === 'numeric_comparison' && exp.metric === 'total_cost';

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
                    <span className="caption">SIMULATED · live Ring/Bee connections unavailable</span>
                  </div>

                  <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                    {isRing && (
                      <>
                        <button
                          className="button secondary"
                          onClick={() => triggerSimulation('ring_match')}
                          disabled={simBusy}
                        >
                          Simulate Package Delivered
                        </button>
                        <button
                          className="button ghost"
                          onClick={() => triggerSimulation('ring_mismatch')}
                          disabled={simBusy}
                        >
                          Simulate No Package Detected
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
                          Simulate Plumber Confirmed
                        </button>
                        <button
                          className="button ghost"
                          onClick={() => triggerSimulation('bee_cancel')}
                          disabled={simBusy}
                        >
                          Simulate Plumber Cancelled
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
                          Simulate Bill $130.00
                        </button>
                        <button
                          className="button ghost"
                          onClick={() => triggerSimulation('utility_high')}
                          disabled={simBusy}
                        >
                          Simulate Bill $162.00
                        </button>
                      </>
                    )}

                    {!isRing && !isBee && !isUtility && <p>No compatible simulator for these conditions.</p>}
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
                <TrackingControls key={id} expectation={state.data.expectation} refresh={state.reload} />
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
                  <SourceBinding key={id} expectationId={id} />
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
            {exp && manageOpen && (
              <ExpectationActionsModal
                expectation={exp}
                key={exp.id}
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
}
