'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import {
  Bell,
  CheckCircle2,
  Hourglass,
  RefreshCw,
  Sparkles,
  FlaskConical,
  ArrowRight,
  Radio,
} from 'lucide-react';
import { useBoard } from '@/components/app-shell';
import { useIdentity } from '@/components/auth-provider';
import { AttentionCard, ExpectationCard, HealthyCard } from '@/components/expectation';
import { EvidenceTimeline } from '@/components/evidence-timeline';
import { ExpectationActionsModal } from '@/components/expectation-actions-modal';
import { Badge, EmptyState, ErrorState, IconBox, Loading, NewExpectationLink, PageHeader, QuietNote } from '@/components/ui';
import { api } from '@/lib/api';
import type { Evidence, Expectation } from '@/lib/types';
import { getExpectationPresentationStatus, summary } from '@/lib/presentation';
import { useResource } from '@/hooks/use-resource';
import {
  generateRingEvent,
  ringEventToEvidence,
  generateBeeEvent,
  beeEventToEvidence,
} from '@/lib/simulators';

export default function Dashboard() {
  const board = useBoard();
  const { firstName } = useIdentity();
  const rows = board.data ?? [];
  const counts = summary(rows);

  const [managingExp, setManagingExp] = useState<Expectation | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());
  const [simMessage, setSimMessage] = useState<string | null>(null);
  const [simBusy, setSimBusy] = useState(false);

  // Auto-refresh poll every 8 seconds for real-time MATCH, UNKNOWN, MISMATCH updates
  useEffect(() => {
    const timer = setInterval(() => {
      board.reload();
      setLastUpdated(new Date());
    }, 8000);
    return () => clearInterval(timer);
  }, [board]);

  const attention = rows.filter(
    (row) => getExpectationPresentationStatus(row.expectation, row.latest) === 'attention'
  );
  const priority = attention.find((row) => row.expectation.metric === 'total_cost') ?? attention[0];
  const priorityId = priority?.expectation.id;

  // Load priority supporting evidence
  const loadPriorityEvidence = useCallback(
    (signal: AbortSignal) => (priorityId ? api.evidence(priorityId, signal) : Promise.resolve([])),
    [priorityId]
  );
  const priorityEvidence = useResource(loadPriorityEvidence);

  // Load multi-source evidence across active expectations for the Evidence Timeline
  const loadTimelineEvidence = useCallback(
    async (signal: AbortSignal): Promise<Evidence[]> => {
      if (!rows.length) return [];
      const sampled = rows.slice(0, 6);
      const results = await Promise.all(
        sampled.map(async (row) => {
          try {
            return await api.evidence(row.expectation.id, signal);
          } catch {
            return [];
          }
        })
      );
      return results.flat();
    },
    [rows]
  );
  const timelineResource = useResource(loadTimelineEvidence);

  // Quick simulator action
  async function runQuickSim(scenario: 'ring_delivery' | 'ring_missing' | 'bee_confirm' | 'bee_cancel') {
    setSimBusy(true);
    setSimMessage(null);

    try {
      if (scenario === 'ring_delivery' || scenario === 'ring_missing') {
        const targetRow = rows.find(
          (r) =>
            r.expectation.metric === 'delivered' ||
            r.expectation.metric === 'package_detected' ||
            r.expectation.claim.toLowerCase().includes('package')
        ) ?? rows[0];

        if (!targetRow) {
          setSimMessage('No expectation found to attach Ring evidence to.');
          return;
        }

        const kind = scenario === 'ring_delivery' ? 'package_detected' : 'package_not_detected';
        const raw = generateRingEvent(kind, {
          metric: targetRow.expectation.metric ?? 'package_detected',
        });
        const ev = ringEventToEvidence(raw);
        await api.addEvidence(targetRow.expectation.id, ev);
        await api.evaluate(targetRow.expectation.id);
        setSimMessage(
          scenario === 'ring_delivery'
            ? 'Ring package delivery simulated -> Evaluated as MATCH'
            : 'Ring package missing simulated -> Evaluated as MISMATCH'
        );
      } else {
        const targetRow = rows.find(
          (r) =>
            r.expectation.metric === 'appointment_confirmed' ||
            r.expectation.claim.toLowerCase().includes('plumber') ||
            r.expectation.claim.toLowerCase().includes('landlord')
        ) ?? rows[0];

        if (!targetRow) {
          setSimMessage('No expectation found to attach Bee context to.');
          return;
        }

        const isConfirm = scenario === 'bee_confirm';
        const raw = generateBeeEvent({
          speaker: 'Landlord',
          summary: isConfirm
            ? 'Spoke with landlord: Plumber confirmed for Friday 10:00 AM.'
            : 'Spoke with landlord: Plumber cancelled Friday due to an emergency.',
          metric: targetRow.expectation.metric ?? 'appointment_confirmed',
          confirmed: isConfirm,
        });
        const ev = beeEventToEvidence(raw);
        await api.addEvidence(targetRow.expectation.id, ev);
        await api.evaluate(targetRow.expectation.id);
        setSimMessage(
          isConfirm
            ? 'Bee context simulated: Plumber confirmed -> Evaluated as MATCH'
            : 'Bee context simulated: Plumber cancelled -> Evaluated as MISMATCH'
        );
      }

      board.reload();
      priorityEvidence.reload();
      timelineResource.reload();
      setLastUpdated(new Date());
    } catch (err) {
      setSimMessage(err instanceof Error ? `Simulation failed: ${err.message}` : 'Failed to simulate');
    } finally {
      setSimBusy(false);
    }
  }

  return (
    <>
      <PageHeader
        eyebrow="A little clarity, every day"
        title={`Welcome back, ${firstName}`}
        description={
          board.data
            ? rows.length
              ? `CountOn is watching ${rows.length} expectation${
                  rows.length === 1 ? '' : 's'
                } for you.`
              : 'A quieter way to keep track of what matters.'
            : 'Your expectations, with a little less uncertainty.'
        }
        action={
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <button
              className="button secondary"
              onClick={() => {
                board.reload();
                priorityEvidence.reload();
                timelineResource.reload();
                setLastUpdated(new Date());
              }}
              style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}
              title="Refresh evaluations"
            >
              <RefreshCw size={15} />
              Refresh
            </button>
            <NewExpectationLink />
          </div>
        }
      />

      {/* Real-time Status Bar */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          padding: '0.6rem 1rem',
          backgroundColor: 'rgba(37, 99, 235, 0.05)',
          borderRadius: '10px',
          margin: '-0.75rem 0 1.25rem',
          fontSize: '0.85rem',
          color: 'var(--text-secondary, #475569)',
          flexWrap: 'wrap',
          gap: '0.5rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span
            style={{
              width: '8px',
              height: '8px',
              borderRadius: '50%',
              backgroundColor: '#16a34a',
              display: 'inline-block',
              boxShadow: '0 0 0 2px rgba(22, 163, 74, 0.2)',
            }}
          />
          <strong style={{ color: '#0f172a' }}>Real-time updates active</strong>
          <span>· Watching evaluations and evidence</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <span>Updated {lastUpdated.toLocaleTimeString()}</span>
          <Link
            href="/demos"
            style={{
              fontWeight: 600,
              color: 'var(--primary, #2563eb)',
              display: 'flex',
              alignItems: 'center',
              gap: '0.25rem',
              textDecoration: 'none',
            }}
          >
            Interactive Demos <ArrowRight size={14} />
          </Link>
        </div>
      </div>

      {simMessage && (
        <div
          className="soft-card"
          style={{
            margin: '0 0 1.25rem',
            padding: '0.75rem 1rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.5rem',
            backgroundColor: '#eff6ff',
            border: '1px solid #bfdbfe',
            color: '#1e40af',
          }}
        >
          <Sparkles size={16} />
          <span>{simMessage}</span>
        </div>
      )}

      {board.loading ? (
        <Loading />
      ) : board.error ? (
        <ErrorState error={board.error} retry={board.reload} />
      ) : !rows.length ? (
        <EmptyState
          title="Nothing being monitored yet."
          description="Tell CountOn what you’re counting on. We’ll help you follow the evidence."
          action={<NewExpectationLink first />}
        />
      ) : (
        <>
          {/* Summary Status Cards */}
          <div className="summary-grid">
            {[
              {
                status: 'match' as const,
                value: counts.match,
                icon: CheckCircle2,
                copy: 'MATCH · Confirmed by evidence',
                tone: 'green' as const,
              },
              {
                status: 'attention' as const,
                value: counts.attention,
                icon: Bell,
                copy: 'MISMATCH · Needs closer look',
                tone: 'orange' as const,
              },
              {
                status: 'waiting' as const,
                value: counts.waiting,
                icon: Hourglass,
                copy: 'UNKNOWN · Awaiting observations',
                tone: 'gray' as const,
              },
            ].map((item) => (
              <div className="card summary-card" key={item.status}>
                <IconBox icon={item.icon} tone={item.tone} />
                <div>
                  <div className="summary-value">
                    <strong>{item.value}</strong>
                    <Badge status={item.status} />
                  </div>
                  <p>{item.copy}</p>
                </div>
              </div>
            ))}
          </div>

          {/* Quick Simulation Bar */}
          <section
            className="card"
            style={{
              padding: '1.25rem',
              marginBottom: '1.5rem',
              border: '1px dashed var(--border-color, #cbd5e1)',
              backgroundColor: '#fafbfc',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: '0.75rem',
                marginBottom: '0.75rem',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <FlaskConical size={18} color="var(--primary, #2563eb)" />
                <h3 style={{ margin: 0, fontSize: '0.95rem' }}>Simulator Quick Actions</h3>
                <span className="caption">Test Ring & Bee context without physical devices</span>
              </div>
              <Link href="/demos" className="text-link" style={{ fontSize: '0.85rem' }}>
                Full interactive demos <ArrowRight size={14} />
              </Link>
            </div>

            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              <button
                className="button secondary"
                onClick={() => runQuickSim('ring_delivery')}
                disabled={simBusy}
                style={{ fontSize: '0.825rem', padding: '0.4rem 0.75rem' }}
              >
                Ring: Package Delivered (MATCH)
              </button>
              <button
                className="button ghost"
                onClick={() => runQuickSim('ring_missing')}
                disabled={simBusy}
                style={{ fontSize: '0.825rem', padding: '0.4rem 0.75rem' }}
              >
                Ring: Package Missing (MISMATCH)
              </button>
              <button
                className="button secondary"
                onClick={() => runQuickSim('bee_confirm')}
                disabled={simBusy}
                style={{ fontSize: '0.825rem', padding: '0.4rem 0.75rem' }}
              >
                Bee: Plumber Confirmed (MATCH)
              </button>
              <button
                className="button ghost"
                onClick={() => runQuickSim('bee_cancel')}
                disabled={simBusy}
                style={{ fontSize: '0.825rem', padding: '0.4rem 0.75rem' }}
              >
                Bee: Plumber Cancelled (MISMATCH)
              </button>
            </div>
          </section>

          {/* Attention Card (Priority Mismatch) */}
          {priority ? (
            <section className="section">
              <div className="section-heading">
                <h2>
                  <span className="signal" />
                  Needs your attention
                </h2>
                <span className="caption">Clear signal from evaluated observations</span>
              </div>
              {priorityEvidence.loading ? (
                <Loading label="Loading supporting evidence" />
              ) : priorityEvidence.error ? (
                <ErrorState error={priorityEvidence.error} retry={priorityEvidence.reload} />
              ) : (
                <AttentionCard row={priority} evidence={priorityEvidence.data ?? []} />
              )}
            </section>
          ) : (
            <section className="section">
              <HealthyCard />
            </section>
          )}

          {/* Active Expectations Grid with Manage Lifecycle Action */}
          <section className="section">
            <div className="section-heading">
              <h2>Active Expectations</h2>
              <span className="caption">{rows.length} total being watched</span>
            </div>
            <div className="grid two">
              {rows.map((row) => (
                <ExpectationCard
                  row={row}
                  key={row.expectation.id}
                  onManage={(exp) => setManagingExp(exp)}
                />
              ))}
            </div>
          </section>

          {/* Evidence Timeline across sources */}
          <section className="section">
            {timelineResource.loading ? (
              <Loading label="Loading recent evidence..." />
            ) : timelineResource.error ? (
              <ErrorState error={timelineResource.error} retry={timelineResource.reload} />
            ) : (
              <EvidenceTimeline
                evidenceList={timelineResource.data ?? []}
                expectations={rows.map((r) => r.expectation)}
                title="Evidence Timeline"
                subtitle="Recent observations from Ring, Bee, email, and utility accounts"
                limit={8}
              />
            )}
          </section>

          <QuietNote>When things match what you expected, there’s nothing you need to do.</QuietNote>
        </>
      )}

      {/* Expectation Lifecycle Management Modal */}
      {managingExp && (
        <ExpectationActionsModal
          expectation={managingExp}
          isOpen={!!managingExp}
          onClose={() => setManagingExp(null)}
          onUpdated={() => {
            board.reload();
            priorityEvidence.reload();
            timelineResource.reload();
          }}
        />
      )}
    </>
  );
}
