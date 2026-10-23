'use client';

import { useCallback, useMemo } from 'react';
import Link from 'next/link';
import { useState } from 'react';
import { useBoard } from '@/components/app-shell';
import { useIdentity } from '@/components/auth-provider';
import { EmptyState, ErrorState, Loading, PageHeader } from '@/components/ui';
import { EvidenceTimeline } from '@/components/evidence-timeline';
import { auditActionLabel, auditSourceLabel, displayTitle, evaluationLabels, formatDate, humanize } from '@/lib/presentation';
import { api } from '@/lib/api';
import type { AuditEvent, Evidence } from '@/lib/types';
import { useResource } from '@/hooks/use-resource';

export default function Activity() {
  const board = useBoard();
  const { timeZone } = useIdentity();
  const rows = useMemo(() => board.data ?? [], [board.data]);

  const loadEvidence = useCallback(async (signal: AbortSignal): Promise<Evidence[]> => {
    if (!rows.length) return [];
    const results = await Promise.all(
      rows.map(row => api.evidence(row.expectation.id, signal))
    );
    return results.flat();
  }, [rows]);

  const evidenceState = useResource(loadEvidence, 30000);
  const [expectationFilter, setExpectationFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [resultFilter, setResultFilter] = useState('');
  const [afterFilter, setAfterFilter] = useState('');
  const [beforeFilter, setBeforeFilter] = useState('');
  const loadAudit = useCallback(
    (signal: AbortSignal): Promise<AuditEvent[]> => api.auditEvents({
      expectationId: expectationFilter || undefined,
      source: sourceFilter || undefined,
      result: resultFilter || undefined,
      after: afterFilter ? `${afterFilter}T00:00:00Z` : undefined,
      before: beforeFilter ? `${beforeFilter}T23:59:59.999Z` : undefined,
    }, signal),
    [expectationFilter, sourceFilter, resultFilter, afterFilter, beforeFilter],
  );
  const auditState = useResource(loadAudit, 30000);
  const [categoryFilter, setCategoryFilter] = useState<'all' | 'expectations' | 'evidence' | 'evaluations' | 'actions'>('all');

  const filteredAuditData = useMemo(() => {
    const list = auditState.data ?? [];
    if (categoryFilter === 'all') return list;
    if (categoryFilter === 'evidence') return list.filter((e) => !!e.evidence);
    if (categoryFilter === 'evaluations') return list.filter((e) => !!e.result_status);
    if (categoryFilter === 'expectations') return list.filter((e) => e.action_taken.toLowerCase().includes('expectation'));
    if (categoryFilter === 'actions') return list.filter((e) => !e.evidence && !e.result_status);
    return list;
  }, [auditState.data, categoryFilter]);


  const events = (auditState.data ?? []).filter(event =>
    /^(EXPECTATION_|EVALUATION_|EXPLANATION_|NOTIFICATION_|CLARIFICATION_)/.test(event.event_type)
  ).map(event => ({
    id: event.audit_event_id, at: event.occurred_at,
    title: auditActionLabel(event), detail: event.expectation?.claim ?? 'Account activity',
  }));

  return (
    <>
      <PageHeader
        title="Activity & Evidence Timeline"
        description="Persisted audit history and recorded evidence for your account."
        action={<button className="button secondary" onClick={() => { board.reload(); evidenceState.reload(); auditState.reload(); }}>Refresh</button>}
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

          <section className="section">
            <div className="section-heading">
              <h2>Audit History</h2>
              <span className="caption">Persisted, redacted account activity</span>
            </div>
            <div className="filters" aria-label="Activity categories" style={{ marginBottom: '1rem' }}>
              {[
                { value: 'all', label: 'All Activity' },
                { value: 'expectations', label: 'Expectations' },
                { value: 'evidence', label: 'Evidence Ingestion' },
                { value: 'evaluations', label: 'Evaluations' },
                { value: 'actions', label: 'User Actions' },
              ].map((cat) => (
                <button
                  key={cat.value}
                  className={`filter ${categoryFilter === cat.value ? 'selected' : ''}`}
                  onClick={() => setCategoryFilter(cat.value as typeof categoryFilter)}
                  aria-pressed={categoryFilter === cat.value}
                >
                  {cat.label}
                </button>
              ))}
            </div>

            <div className="form-grid" aria-label="Audit history filters">
              <label>Expectation<select value={expectationFilter} onChange={(event) => setExpectationFilter(event.target.value)}><option value="">All expectations</option>{rows.map(({ expectation }) => <option key={expectation.id} value={expectation.id}>{displayTitle(expectation)}</option>)}</select></label>
              <label>Source<select value={sourceFilter} onChange={(event) => setSourceFilter(event.target.value)}><option value="">All sources</option>{['ALEXA','ALEXA_WEB','WEB','MCP','GMAIL','OUTLOOK','GOOGLE','MICROSOFT','RING','BEE'].map(source => <option key={source} value={source}>{humanize(source.toLowerCase())}</option>)}</select></label>
              <label>Result<select value={resultFilter} onChange={(event) => setResultFilter(event.target.value)}><option value="">All results</option>{(['MATCH','UNKNOWN','MISMATCH'] as const).map(result => <option key={result} value={result}>{evaluationLabels[result]}</option>)}</select></label>
              <label>From<input type="date" value={afterFilter} onChange={(event) => setAfterFilter(event.target.value)} /></label>
              <label>Through<input type="date" value={beforeFilter} onChange={(event) => setBeforeFilter(event.target.value)} /></label>
            </div>
            {auditState.loading ? (
              <Loading label="Loading audit history..." />
            ) : auditState.error ? (
              <ErrorState error={auditState.error} retry={auditState.reload} />
            ) : filteredAuditData.length ? (
              <section className="card" role="table" aria-label="Audit History" style={{ overflowX: 'auto' }}>
                <div
                  role="row"
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1.5fr 1.2fr 1fr .8fr 1.1fr 1fr',
                    gap: '1rem',
                    padding: '1rem',
                    borderBottom: '1px solid var(--border-color, #e2e8f0)',
                    minWidth: '52rem',
                  }}
                >
                  {['Expectation', 'Evidence', 'Source', 'Result', 'Action', 'Timestamp'].map((label) => (
                    <strong role="columnheader" key={label}>{label}</strong>
                  ))}
                </div>
                {filteredAuditData.map((event) => (
                  <div
                    key={event.audit_event_id}
                    role="row"
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '1.5fr 1.2fr 1fr .8fr 1.1fr 1fr',
                      gap: '1rem',
                      padding: '1rem',
                      borderBottom: '1px solid var(--border-color, #e2e8f0)',
                      alignItems: 'center',
                      minWidth: '52rem',
                    }}
                  >
                    <span role="cell">{event.expectation ? <Link href={`/expectations/${event.expectation.id}`}>{event.expectation.claim}</Link> : 'Account activity'}</span>
                    <span role="cell">{event.evidence ? Object.values(event.evidence.value).filter(value => ['string','number','boolean'].includes(typeof value)).slice(0, 2).join(' · ') || 'Evidence recorded' : '—'}</span>
                    <span role="cell">{auditSourceLabel(event)}</span>
                    <span role="cell">{event.result_status ? evaluationLabels[event.result_status] : '—'}</span>
                    <span role="cell">{auditActionLabel(event)}</span>
                    <time role="cell" dateTime={event.occurred_at}>
                      {formatDate(event.occurred_at, timeZone)}
                    </time>
                  </div>
                ))}
              </section>
            ) : (
              <EmptyState
                title="No audit events yet."
                description="Security-relevant and monitoring actions will appear here after they are persisted."
              />
            )}
          </section>

          {/* Lifecycle Activity */}
          <section className="section">
            <div className="section-heading">
              <h2>Expectation Lifecycle Events</h2>
              <span className="caption">Persisted lifecycle audit events</span>
            </div>

            {auditState.loading ? <Loading label="Loading lifecycle history" /> : auditState.error ? <ErrorState error={auditState.error} retry={auditState.reload} /> : events.length ? (
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
