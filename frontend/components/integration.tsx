'use client';
import { useState } from 'react';
import { providers, consentUrl } from '@/lib/providers';
import { ProviderAccount } from './provider-account';
import { CalendarDays, Camera, Link2, Mail, Package, Radio, Zap } from 'lucide-react';
import type { Integration } from '@/lib/types';
import { formatDate, humanize } from '@/lib/presentation';
import { useIdentity } from './auth-provider';
import { IconBox, Modal } from './ui';
import { api } from '@/lib/api';

export const providerLabels: Record<string, string> = {
  google: 'Google',
  microsoft: 'Microsoft',
  ring: 'Ring',
  bee: 'Bee',
  utility: 'Utility',
  delivery: 'Delivery',
};

const icons: Record<string, typeof Mail> = {
  email: Mail,
  calendar: CalendarDays,
  camera: Camera,
  wearable: Radio,
  utility: Zap,
  delivery: Package,
};

export function IntegrationCard({
  item,
  reload,
  onRefresh,
}: {
  item: Integration;
  reload?: () => void;
  onRefresh?: () => void;
}) {
  const triggerRefresh = reload ?? onRefresh;
  const { timeZone } = useIdentity();
  const demo = item.metadata.demo || item.metadata.mock;
  const isSimulated = item.provider === 'ring' || item.provider === 'bee';
  const isAmazonDelivery = item.provider === 'delivery' || item.display_name?.toLowerCase().includes('amazon');

  return (
    <article className="card integration-card" style={{ padding: '1.25rem' }}>
      <div className="integration-heading">
        <IconBox
          icon={icons[item.connection_type] ?? Link2}
          tone={item.connection_type === 'email' || item.connection_type === 'utility' ? 'orange' : 'blue'}
        />
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            <h3 style={{ margin: 0 }}>
              {isAmazonDelivery
                ? 'Amazon (Email-derived)'
                : (item.display_name ?? `${providerLabels[item.provider]} ${humanize(item.connection_type)}`)}
            </h3>
            {isSimulated && (
              <span className="demo-badge" style={{ backgroundColor: '#fef3c7', color: '#92400e', border: '1px solid #fde68a' }}>
                SIMULATED (NO LIVE HARDWARE)
              </span>
            )}
            {demo && !isSimulated && (
              <span className="demo-badge">Demo connection</span>
            )}
          </div>
          <p style={{ margin: '0.2rem 0 0', fontSize: '0.875rem', color: '#64748b' }}>
            {providerLabels[item.provider]} · {humanize(item.connection_type)}
          </p>
        </div>
      </div>

      {isAmazonDelivery && (
        <div
          style={{
            margin: '0.75rem 0',
            padding: '0.5rem 0.75rem',
            backgroundColor: '#f8fafc',
            borderRadius: '6px',
            fontSize: '0.8rem',
            color: '#475569',
            border: '1px solid #e2e8f0',
          }}
        >
          <strong>Email-Derived Evidence:</strong> Order status is extracted from authenticated email receipts. Does not imply direct Amazon Retail API authorization.
        </div>
      )}

      {/* Permissions / Scopes display */}
      {item.scopes && item.scopes.length > 0 && (
        <div style={{ margin: '0.75rem 0', fontSize: '0.8rem' }}>
          <span style={{ fontWeight: 600, color: '#475569' }}>Granted permissions:</span>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', marginTop: '0.25rem' }}>
            {item.scopes.map((scope) => {
              const label = scope.includes('/') ? scope.split('/').pop() : scope;
              return (
                <span
                  key={scope}
                  style={{
                    backgroundColor: '#f1f5f9',
                    padding: '0.15rem 0.45rem',
                    borderRadius: '4px',
                    fontSize: '0.75rem',
                    color: '#334155',
                  }}
                  title={scope}
                >
                  {label}
                </span>
              );
            })}
          </div>
        </div>
      )}

      {/* Status indicator */}
      <div className="integration-status" style={{ marginTop: '0.75rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: '0.85rem' }}>
          {isSimulated ? 'Simulated device source' : demo ? 'Modeled account' : 'Connected source'}
        </span>
        <span
          className={`badge ${
            item.status === 'connected' ? 'monitoring' : item.status === 'error' ? 'attention' : 'waiting'
          }`}
        >
          <span className="status-dot" />
          {isSimulated ? 'Simulated' : humanize(item.status)}
        </span>
      </div>

      {item.status === 'error' && (
        <div
          style={{
            marginTop: '0.5rem',
            padding: '0.5rem 0.75rem',
            backgroundColor: '#fef2f2',
            border: '1px solid #fecaca',
            borderRadius: '6px',
            color: '#991b1b',
            fontSize: '0.8rem',
          }}
        >
          Connection sync error: Token expired or authorization revoked. Re-authentication required.
        </div>
      )}

      <div style={{ marginTop: '0.6rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <p className="caption" style={{ margin: 0 }}>
          {item.last_synced_at ? `Last synced ${formatDate(item.last_synced_at, timeZone)}` : 'No sync recorded'} ·{' '}
          {item.credential_state === 'not_configured' ? 'Live access not configured' : 'Active credentials'}
        </p>
      </div>

      {!demo && ['google', 'microsoft'].includes(item.provider) ? (
        <ProviderAccount item={item} reload={triggerRefresh ?? (() => {})} />
      ) : (
        triggerRefresh && (
          <div style={{ marginTop: '0.6rem', display: 'flex', justifyContent: 'flex-end' }}>
            <button
              type="button"
              className="button subtle"
              style={{ fontSize: '0.75rem', padding: '0.2rem 0.5rem', color: 'var(--text-muted)' }}
              onClick={async () => {
                try {
                  await api.deleteIntegration(item.id);
                  triggerRefresh();
                } catch (e) {
                  console.error('Failed to disconnect integration:', e);
                }
              }}
            >
              Disconnect
            </button>
          </div>
        )
      )}
    </article>
  );
}

const simulatedSources = [
  {
    provider: 'ring' as const,
    connection_type: 'camera' as const,
    title: 'Ring Video Doorbell',
    description: 'Simulated doorbell rings and motion events without live physical hardware.',
    scopes: ['devices.read', 'events.read'],
  },
  {
    provider: 'bee' as const,
    connection_type: 'wearable' as const,
    title: 'Bee AI Wearable',
    description: 'Simulated audio context for spoken agreements and notes.',
    scopes: ['transcripts.read'],
  },
];

export function ConnectAccountModal({
  onClose,
  onConnected,
}: {
  onClose: () => void;
  onConnected?: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function connect(provider: 'google' | 'microsoft', kind: 'email' | 'calendar') {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const enabled = await providers.capabilities();
      if (!enabled[provider]) throw new Error(`${providerLabels[provider]} authorization is not configured on this backend.`);
      const connection = await providers.create(provider, kind);
      const result = await providers.authorize(connection.id);
      window.location.assign(consentUrl(result.authorization_url));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not start authorization.');
    } finally {
      setBusy(false);
    }
  }

  async function connectSimulated(source: (typeof simulatedSources)[number]) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.createIntegration({
        provider: source.provider,
        connection_type: source.connection_type,
        display_name: source.title,
        status: 'connected',
        scopes: source.scopes,
        metadata: { mock: true, demo: false, account_kind: 'personal' },
      });
      setNotice(`Simulated ${source.title} added successfully.`);
      onConnected?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not add simulated source.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <Modal title="Connect an account" onClose={onClose}>
      <p>Authorize read-only access, then select a mailbox or calendar to synchronize. No messages or events are changed.</p>
      
      <div className="provider-list">
        {([
          ['google', 'email', 'Gmail'],
          ['microsoft', 'email', 'Outlook'],
          ['google', 'calendar', 'Google Calendar'],
          ['microsoft', 'calendar', 'Microsoft Calendar'],
        ] as const).map(([provider, kind, name]) => (
          <div key={name} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.5rem 0' }}>
            <strong>{name}</strong>
            <button className="button secondary" disabled={busy} onClick={() => connect(provider, kind)}>
              Connect
            </button>
          </div>
        ))}
      </div>

      <div style={{ marginTop: '1.25rem', paddingTop: '1rem', borderTop: '1px solid #e2e8f0' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
          <strong style={{ fontSize: '0.875rem', color: '#475569' }}>Simulated Device Sources</strong>
          <span className="demo-badge" style={{ backgroundColor: '#fef3c7', color: '#92400e', fontSize: '0.7rem' }}>
            SIMULATED
          </span>
        </div>
        <div className="provider-list">
          {simulatedSources.map((source) => (
            <div key={source.title} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.5rem 0' }}>
              <div>
                <strong>{source.title}</strong>
                <p style={{ margin: '0.1rem 0 0', fontSize: '0.8rem', color: '#64748b' }}>{source.description}</p>
              </div>
              <button className="button secondary" disabled={busy} onClick={() => connectSimulated(source)}>
                + Add Simulated
              </button>
            </div>
          ))}
        </div>
      </div>

      <p className="caption" style={{ marginTop: '1rem' }}>
        Utilities, carriers, Ring and Bee do not have live connectors here. Amazon order evidence uses authorized email or user-entered facts.
      </p>

      {error && <p role="alert">{error}</p>}
      {notice && <p role="status">{notice}</p>}

      <button className="button secondary full" style={{ marginTop: '0.75rem' }} onClick={onClose}>
        Close
      </button>
    </Modal>
  );
}
