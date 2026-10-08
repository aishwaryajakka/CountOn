'use client';
import { useState } from 'react';
import { useBoard } from '@/components/app-shell';
import Link from 'next/link';
import { Bell, ShieldCheck } from 'lucide-react';
import { api } from '@/lib/api';
import { useResource } from '@/hooks/use-resource';
import { NotificationCard } from '@/components/notification';
import { EmptyState, ErrorState, Loading, PageHeader } from '@/components/ui';
const load = (signal: AbortSignal) => api.notifications(signal);
export default function Notifications() {
  const state = useResource(load); const board = useBoard(); const [filter, setFilter] = useState('active');
  const items = (state.data ?? []).filter(item => filter === 'all' || (filter === 'unread' ? item.status === 'pending' || item.status === 'sent' : item.status !== 'dismissed'));
  return <><PageHeader eyebrow="Only what’s worth your attention" title="Notifications" description="CountOn only alerts you when something needs your attention. Matched expectations stay quiet." /><div className="filters" aria-label="Filter notifications">{[{ value: 'active', label: 'Active' }, { value: 'unread', label: 'Unread' }, { value: 'all', label: 'All' }].map(item => <button className={`filter ${filter === item.value ? 'selected' : ''}`} aria-pressed={filter === item.value} key={item.value} onClick={() => setFilter(item.value)}>{item.label}</button>)}</div><div className="notification-layout"><div>{state.loading ? <Loading /> : state.error ? <ErrorState error={state.error} retry={state.reload} /> : items.length ? <div className="notification-list">{items.map(item => <NotificationCard key={item.id} item={item} refresh={state.reload} row={board.data?.find(row => row.expectation.id === item.expectation_id)} />)}</div> : <EmptyState title="Nothing needs your attention." description="Matched expectations stay quiet. Take a breath — there’s nothing to review here." icon={Bell} />}</div><aside><div className="card notification-aside"><span className="eyebrow">A LITTLE LESS UNCERTAINTY</span><h2>What are you counting on?</h2><p>Start with something that matters to you. We’ll help you make it clear.</p><Link className="button primary full" href="/expectations/new">Create an expectation</Link></div><div className="soft-card"><ShieldCheck size={25} /><h3>Silence is success.</h3><p>There’s no score to chase. When things match your expectations, you can simply carry on.</p></div></aside></div></>;
}
