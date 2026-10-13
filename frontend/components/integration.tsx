'use client';
import { useState } from 'react';
import { providers, consentUrl } from '@/lib/providers';
import { ProviderAccount } from './provider-account';
import { CalendarDays, Camera, Mail, Package, Radio, Zap } from 'lucide-react';
import type { Integration } from '@/lib/types';
import { formatDate, humanize } from '@/lib/presentation';
import { useIdentity } from './auth-provider';
import { IconBox, Modal } from './ui';

export const providerLabels = { google: 'Google', microsoft: 'Microsoft', ring: 'Ring', bee: 'Bee', utility: 'Utility', delivery: 'Delivery' };
const icons = { email: Mail, calendar: CalendarDays, camera: Camera, wearable: Radio, utility: Zap, delivery: Package };
export function IntegrationCard({ item, reload = () => {} }: { item: Integration; reload?: () => void }) {
  const { timeZone } = useIdentity();
  const demo = item.metadata.demo || item.metadata.mock;
  return <article className="card integration-card"><div className="integration-heading"><IconBox icon={icons[item.connection_type]} tone={item.connection_type === 'email' || item.connection_type === 'utility' ? 'orange' : 'blue'} /><div><h3>{item.display_name ?? `${providerLabels[item.provider]} ${humanize(item.connection_type)}`}</h3><p>{providerLabels[item.provider]} · {humanize(item.connection_type)}</p></div></div>{demo && <span className="demo-badge">Demo connection</span>}<div className="integration-status"><span>{demo ? 'Modeled account' : 'Account record'}</span><span className={`badge ${item.status === 'connected' ? 'monitoring' : item.status === 'error' ? 'attention' : 'waiting'}`}><span className="status-dot" />{humanize(item.status)}</span></div><p className="caption">{item.last_synced_at ? `Last synced ${formatDate(item.last_synced_at, timeZone)}` : 'No successful sync recorded'}{item.failure_status ? ` · ${humanize(item.failure_status)}` : item.credential_state === 'not_configured' ? ' · Live access not configured' : ''}</p>{!demo && ['google', 'microsoft'].includes(item.provider) && <ProviderAccount item={item} reload={reload} />}</article>;
}
export function ConnectAccountModal({ onClose }: { onClose: () => void }) {
  const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null);
  async function connect(provider: 'google' | 'microsoft', kind: 'email' | 'calendar') {
    setBusy(true); setError(null);
    try {
      const enabled = await providers.capabilities();
      if (!enabled[provider]) throw new Error(`${providerLabels[provider]} authorization is not configured on this backend.`);
      const connection = await providers.create(provider, kind);
      const result = await providers.authorize(connection.id);
      window.location.assign(consentUrl(result.authorization_url));
    } catch (e) { setError(e instanceof Error ? e.message : 'Could not start authorization.'); } finally { setBusy(false); }
  }
  return <Modal title="Connect an account" onClose={onClose}><p>Authorize read-only access, then select a mailbox or calendar to synchronize. No messages or events are changed.</p><div className="provider-list">{([['google', 'email', 'Gmail'], ['microsoft', 'email', 'Outlook'], ['google', 'calendar', 'Google Calendar'], ['microsoft', 'calendar', 'Microsoft Calendar']] as const).map(([provider, kind, name]) => <div key={name}><strong>{name}</strong><button className="button secondary" disabled={busy} onClick={() => connect(provider, kind)}>Connect</button></div>)}</div><p className="caption">Utilities, carriers, Ring and Bee do not have live connectors here. Amazon order evidence uses authorized email or user-entered facts.</p>{error && <p role="alert">{error}</p>}<button className="button secondary full" onClick={onClose}>Close</button></Modal>;
}
