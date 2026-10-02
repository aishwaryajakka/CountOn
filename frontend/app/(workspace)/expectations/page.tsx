'use client';
import { useState } from 'react';
import { useBoard } from '@/components/app-shell';
import { ExpectationCard } from '@/components/expectation';
import { EmptyState, ErrorState, Loading, NewExpectationLink, PageHeader } from '@/components/ui';
import { getExpectationPresentationStatus, statusLabels, type PresentationStatus } from '@/lib/presentation';

const filters: { value: 'all' | PresentationStatus; label: string }[] = [{ value: 'all', label: 'All' }, { value: 'monitoring', label: 'Monitoring' }, { value: 'attention', label: 'Needs attention' }, { value: 'match', label: 'Matched' }, { value: 'waiting', label: 'Waiting' }];
export default function Expectations() {
  const board = useBoard(); const [filter, setFilter] = useState<'all' | PresentationStatus>('all');
  const rows = board.data ?? [];
  const filtered = rows.filter(row => filter === 'all' || getExpectationPresentationStatus(row.expectation, row.latest) === filter);
  return <><PageHeader title="Expectations" description="Everything CountOn is currently watching for you." action={<NewExpectationLink />} /><div className="filters" aria-label="Filter expectations">{filters.map(item => <button className={`filter ${filter === item.value ? 'selected' : ''}`} key={item.value} onClick={() => setFilter(item.value)} aria-pressed={filter === item.value}>{item.label}<span>{item.value === 'all' ? rows.length : rows.filter(row => getExpectationPresentationStatus(row.expectation, row.latest) === item.value).length}</span></button>)}</div>{board.loading ? <Loading /> : board.error ? <ErrorState error={board.error} retry={board.reload} /> : !rows.length ? <EmptyState title="You’re not counting on anything yet." description="Start with one thing you’d like a little more clarity on." action={<NewExpectationLink first />} /> : !filtered.length ? <EmptyState title="Nothing here right now." description="Your other expectations are still available under All." /> : <>{(['attention', 'monitoring', 'match', 'waiting', 'resolved', 'cancelled'] as PresentationStatus[]).map(status => {
    const items = filtered.filter(row => getExpectationPresentationStatus(row.expectation, row.latest) === status);
    return items.length ? <section className="section expectation-group" key={status}><div className="section-heading"><h2><span className={`group-dot ${status}`} />{statusLabels[status]}</h2><span className="caption">{items.length} expectation{items.length === 1 ? '' : 's'}</span></div><div className="grid two">{items.map(row => <ExpectationCard key={row.expectation.id} row={row} />)}</div></section> : null;
  })}</>}</>;
}
