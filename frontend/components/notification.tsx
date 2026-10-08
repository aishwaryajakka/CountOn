'use client';
import { useState } from 'react';
import Link from 'next/link';
import { ArrowRight, Bell, Check, X } from 'lucide-react';
import { api } from '@/lib/api';
import type { Notification, WatchedExpectation } from '@/lib/types';
import { formatDate, humanize, notificationTitle } from '@/lib/presentation';
import { useIdentity } from './auth-provider';
import { IconBox } from './ui';
export function NotificationCard({ item, refresh, row }: { item: Notification; refresh: () => void; row?: WatchedExpectation }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null);
  const { timeZone } = useIdentity();
  async function update(status: 'read' | 'dismissed') {
    setBusy(true); setError(null);
    try { await api.updateNotification(item.id, status); refresh(); }
    catch { setError('That change didn’t save. Your notification is unchanged; please try again.'); }
    finally { setBusy(false); }
  }
  return <article className={`card notification-card ${item.status === 'dismissed' ? 'dismissed' : ''}`}><IconBox icon={Bell} tone="orange" /><div className="notification-body"><span className="overline">{humanize(item.status)} · In-app notification</span><h2>{notificationTitle(item, row)}</h2><p>{row ? item.message : 'There’s a change worth looking at. Open the expectation to see the evidence.'}</p><time className="caption" dateTime={item.created_at}>{formatDate(item.created_at, timeZone)}</time><div className="actions"><Link className="button primary" href={`/expectations/${item.expectation_id}`}>View expectation <ArrowRight size={16} /></Link>{item.status !== 'read' && item.status !== 'dismissed' && <button className="button ghost" onClick={() => update('read')} disabled={busy}><Check size={15} />Mark as read</button>}{item.status !== 'dismissed' && <button className="button ghost" onClick={() => update('dismissed')} disabled={busy}><X size={15} />Dismiss</button>}</div>{error && <p role="alert" className="inline-error">{error}</p>}</div></article>;
}
