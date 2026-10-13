'use client';

import { useCallback, useMemo } from 'react';
import { useBoard } from '@/components/app-shell';
import { useIdentity } from '@/components/auth-provider';
import { EmptyState, ErrorState, Loading, PageHeader } from '@/components/ui';
import { EvidenceTimeline } from '@/components/evidence-timeline';
import { displayTitle, evaluationLabels, formatDate } from '@/lib/presentation';
import { api } from '@/lib/api';
import type { Evidence } from '@/lib/types';
import { useResource } from '@/hooks/use-resource';

export default function Activity() {
  const board = useBoard();
  const { timeZone } = useIdentity();
  const rows = useMemo(() => board.data ?? [], [board.data]);

  const loadEvidence = useCallback(async (signal: AbortSignal): Promise<Evidence[]> => {
    if (!rows.length) return [];
    const results = await Promise.all(
      rows.map(async (row) => {
        try {
          return await api.evidence(row.expectation.id, signal);
        } catch {
          return [];
        }
      })
    );
    return results.flat();
  }, [rows]);

  const evidenceState = useResource(loadEvidence);

  const events = rows
    .flatMap((row) => [
      {
        id: row.expectation.id,
        at: row.expectation.created_at,
        title: 'Expectation created',
        detail: displayTitle(row.expectation),
      },
      ...(row.latest
        ? [
            {
              id: row.latest.id,
              at: row.latest.created_at,
              title: 'Evaluation recorded',
              detail: `${displayTitle(row.expectation)} · ${
                evaluationLabels[row.latest.result]
              }`,
            },
          ]
        : []),
    ])
    .sort((a, b) => Date.parse(b.at) - Date.parse(a.at));

  return (
    <>
      <PageHeader
        title="Activity & Evidence Timeline"
        description="A complete chronological log of expectations, deterministic evaluations, and incoming evidence."
      />

      {board.loading ? (
        <Loading />
      ) : board.error ? (
        <ErrorState error={board.error} retry={board.reload} />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          {/* Incoming Evidence Timeline */}
          {evidenceState.loading ? (
            <Loading label="Loading evidence timeline..." />
          ) : evidenceState.error ? (
            <ErrorState error={evidenceState.error} retry={evidenceState.reload} />
          ) : (
            <EvidenceTimeline
              evidenceList={evidenceState.data ?? []}
              expectations={rows.map((r) => r.expectation)}
              title="Incoming Evidence Stream"
              subtitle="All observations recorded across Ring, Bee, email, and utility providers"
            />
          )}

          {/* Lifecycle Activity */}
          <section className="section">
            <div className="section-heading">
              <h2>Expectation Lifecycle Events</h2>
              <span className="caption">Created and evaluated expectations</span>
            </div>

            {events.length ? (
              <section className="card activity-list">
                {events.map((event) => (
                  <div key={event.id}>
                    <span className="status-dot" />
                    <div>
                      <strong>{event.title}</strong>
                      <p>{event.detail}</p>
                    </div>
                    <time dateTime={event.at}>{formatDate(event.at, timeZone)}</time>
                  </div>
                ))}
              </section>
            ) : (
              <EmptyState
                title="A quiet start."
                description="Your expectations and evaluations will appear here as they’re recorded."
              />
            )}
          </section>
        </div>
      )}
    </>
  );
}
