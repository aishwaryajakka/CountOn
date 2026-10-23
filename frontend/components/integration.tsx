'use client';

import { useState } from 'react';
import { CalendarDays, Camera, Mail, Package, Radio, Zap } from 'lucide-react';
import type { Integration } from '@/lib/types';
import { formatDate, humanize } from '@/lib/presentation';
import { useIdentity } from './auth-provider';
import { IconBox, Modal } from './ui';
import { api } from '@/lib/api';

export const providerLabels = { google: 'Google', microsoft: 'Microsoft', ring: 'Ring', bee: 'Bee', utility: 'Utility', delivery: 'Delivery' };
const icons = { email: Mail, calendar: CalendarDays, camera: Camera, wearable: Radio, utility: Zap, delivery: Package };
export function IntegrationCard({ item }: { item: Integration }) {
  const { timeZone } = useIdentity();
  const demo = item.metadata.demo || item.metadata.mock;
  return <article className="card integration-card"><div className="integration-heading"><IconBox icon={icons[item.connection_type]} tone={item.connection_type === 'email' || item.connection_type === 'utility' ? 'orange' : 'blue'} /><div><h3>{item.display_name ?? `${providerLabels[item.provider]} ${humanize(item.connection_type)}`}</h3><p>{providerLabels[item.provider]} · {humanize(item.connection_type)}</p></div></div>{demo && <span className="demo-badge">Demo connection</span>}<div className="integration-status"><span>{demo ? 'Modeled account' : 'Account record'}</span><span className={`badge ${item.status === 'connected' ? 'monitoring' : item.status === 'error' ? 'attention' : 'waiting'}`}><span className="status-dot" />{humanize(item.status)}</span></div><p className="caption">{item.last_synced_at ? `Last synced ${formatDate(item.last_synced_at, timeZone)}` : 'No sync recorded'} · {item.credential_state === 'not_configured' ? 'Live access not configured' : ''}</p></article>;
}

export function ConnectAccountModal({ onClose }: { onClose: () => void }) {
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function connectGoogle() {
    setConnecting(true);
    setError(null);

    try {
      await api.startGoogleOAuth();
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'Could not start Google sign-in. Please try again.'
      );
      setConnecting(false);
    }
  }

  return (
    <Modal title="Connect an account" onClose={onClose}>
      <p>Connect an external account to bring relevant evidence into CountOn.</p>

      <div className="provider-list">
        {Object.entries(providerLabels).map(([key, name]) => (
          <div key={key}>
            <strong>{name}</strong>
            {key === 'google' ? (
              <button
                className="button secondary"
                onClick={connectGoogle}
                disabled={connecting}
              >
                {connecting ? 'Connecting…' : 'Connect Google Account'}
              </button>
            ) : (
              <span className="demo-badge">Coming soon</span>
            )}
          </div>
        ))}
      </div>

      {error && <p className="inline-error" role="alert">{error}</p>}

      <p className="caption">
        Google sign-in will request permission to connect your account.
      </p>

      <button className="button primary full" onClick={onClose}>
        Close
      </button>
    </Modal>
  );
}
