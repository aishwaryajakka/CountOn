'use client';
import { useCallback } from 'react';
import { Bell, CheckCircle2, Hourglass } from 'lucide-react';
import { useBoard } from '@/components/app-shell';
import { useIdentity } from '@/components/auth-provider';
import { AttentionCard, ExpectationCard, HealthyCard } from '@/components/expectation';
import { Badge, EmptyState, ErrorState, IconBox, Loading, NewExpectationLink, PageHeader, QuietNote } from '@/components/ui';
import { api } from '@/lib/api';
import { getExpectationPresentationStatus, summary } from '@/lib/presentation';
import { useResource } from '@/hooks/use-resource';

export default function Dashboard() {
  const board = useBoard();
  const { firstName } = useIdentity();
  const rows = board.data ?? [];
  const counts = summary(rows);
  const attention = rows.filter(row => getExpectationPresentationStatus(row.expectation, row.latest) === 'attention');
  const priority = attention.find(row => row.expectation.metric === 'total_cost') ?? attention[0];
  const id = priority?.expectation.id;
  const loadEvidence = useCallback((signal: AbortSignal) => id ? api.evidence(id, signal) : Promise.resolve([]), [id]);
  const evidence = useResource(loadEvidence);
  return <><PageHeader eyebrow="A little clarity, every day" title={`Welcome back, ${firstName}`} description={board.data ? rows.length ? `CountOn is watching ${rows.length} expectation${rows.length === 1 ? '' : 's'} for you.` : 'A quieter way to keep track of what matters.' : 'Your expectations, with a little less uncertainty.'} action={<NewExpectationLink />} />
    {board.loading ? <Loading /> : board.error ? <ErrorState error={board.error} retry={board.reload} /> : !rows.length ? <EmptyState title="Nothing being monitored yet." description="Tell CountOn what you’re counting on. We’ll help you follow the evidence." action={<NewExpectationLink first />} /> : <>
      <div className="summary-grid">{[{ status: 'match' as const, value: counts.match, icon: CheckCircle2, copy: 'Confirmed by the evidence', tone: 'green' }, { status: 'attention' as const, value: counts.attention, icon: Bell, copy: 'Worth a closer look', tone: 'orange' }, { status: 'waiting' as const, value: counts.waiting, icon: Hourglass, copy: 'Not determined yet', tone: 'gray' }].map(item => <div className="card summary-card" key={item.status}><IconBox icon={item.icon} tone={item.tone} /><div><div className="summary-value"><strong>{item.value}</strong><Badge status={item.status} /></div><p>{item.copy}</p></div></div>)}</div>
      {priority ? <section className="section"><div className="section-heading"><h2><span className="signal" />Needs your attention</h2><span className="caption">A clear signal, not more noise</span></div>{evidence.loading ? <Loading label="Loading supporting evidence" /> : evidence.error ? <ErrorState error={evidence.error} retry={evidence.reload} /> : <AttentionCard row={priority} evidence={evidence.data ?? []} />}</section> : <section className="section"><HealthyCard /></section>}
      <section className="section"><div className="section-heading"><h2>Everything else</h2><span className="caption">{rows.length - (priority ? 1 : 0)} expectations</span></div><div className="grid two">{rows.filter(row => row.expectation.id !== id).map(row => <ExpectationCard row={row} key={row.expectation.id} />)}</div></section><QuietNote>When things match what you expected, there’s nothing you need to do.</QuietNote>
    </>}
  </>;
}
