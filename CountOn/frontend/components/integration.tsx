'use client';
import { CalendarDays, Camera, Mail, Package, Radio, Zap } from 'lucide-react';
import type { Integration } from '@/lib/types';
import { formatDate, humanize } from '@/lib/presentation';
import { useIdentity } from './auth-provider';
import { IconBox, Modal } from './ui';

export const providerLabels = { google: 'Google', microsoft: 'Microsoft', ring: 'Ring', bee: 'Bee', utility: 'Utility', delivery: 'Delivery' };
const icons = { email: Mail, calendar: CalendarDays, camera: Camera, wearable: Radio, utility: Zap, delivery: Package };
export function IntegrationCard({ item }: { item: Integration }) {
  const { timeZone } = useIdentity();
  const demo = item.metadata.demo || item.metadata.mock;
  return <article className="card integration-card"><div className="integration-heading"><IconBox icon={icons[item.connection_type]} tone={item.connection_type === 'email' || item.connection_type === 'utility' ? 'orange' : 'blue'} /><div><h3>{item.display_name ?? `${providerLabels[item.provider]} ${humanize(item.connection_type)}`}</h3><p>{providerLabels[item.provider]} · {humanize(item.connection_type)}</p></div></div>{demo && <span className="demo-badge">Demo connection</span>}<div className="integration-status"><span>{demo ? 'Modeled account' : 'Account record'}</span><span className={`badge ${item.status === 'connected' ? 'monitoring' : item.status === 'error' ? 'attention' : 'waiting'}`}><span className="status-dot" />{humanize(item.status)}</span></div><p className="caption">{item.last_synced_at ? `Last synced ${formatDate(item.last_synced_at, timeZone)}` : 'No sync recorded'} · {item.credential_state === 'not_configured' ? 'Live access not configured' : ''}</p></article>;
}
export function ConnectAccountModal({ onClose }: { onClose: () => void }) {
  return <Modal title="Connect an account" onClose={onClose}><p>Bring the right context to what you’re counting on. Live provider connections are coming soon.</p><div className="provider-list">{Object.entries(providerLabels).map(([key, name]) => <div key={key}><strong>{name}</strong><span className="demo-badge">Coming soon</span></div>)}</div><p className="caption">Existing demo connections contain modeled data. No OAuth authorization or live access is performed here.</p><button className="button primary full" onClick={onClose}>Got it</button></Modal>;
}
