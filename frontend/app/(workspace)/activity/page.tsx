'use client';
import { useBoard } from '@/components/app-shell';
import { useIdentity } from '@/components/auth-provider';
import { EmptyState, ErrorState, Loading, PageHeader } from '@/components/ui';
import { displayTitle, evaluationLabels, formatDate } from '@/lib/presentation';
export default function Activity() {
  const board = useBoard(); const { timeZone } = useIdentity();
  const events = (board.data ?? []).flatMap(row => [{ id: row.expectation.id, at: row.expectation.created_at, title: 'Expectation created', detail: displayTitle(row.expectation) }, ...(row.latest ? [{ id: row.latest.id, at: row.latest.created_at, title: 'Evaluation recorded', detail: `${displayTitle(row.expectation)} · ${evaluationLabels[row.latest.result]}` }] : [])]).sort((a, b) => Date.parse(b.at) - Date.parse(a.at));
  return <><PageHeader title="Activity" description="A lightweight record of expectations and their latest evaluations." /><div className="soft-card"><p>This is a limited view derived from your expectations. It isn’t a complete audit history.</p></div>{board.loading ? <Loading /> : board.error ? <ErrorState error={board.error} retry={board.reload} /> : events.length ? <section className="card activity-list">{events.map(event => <div key={event.id}><span className="status-dot" /><div><strong>{event.title}</strong><p>{event.detail}</p></div><time dateTime={event.at}>{formatDate(event.at, timeZone)}</time></div>)}</section> : <EmptyState title="A quiet start." description="Your expectations and evaluations will appear here as they’re recorded." />}</>;
}
