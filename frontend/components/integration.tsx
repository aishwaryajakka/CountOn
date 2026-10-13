'use client';
import { useState } from 'react';
import { CalendarDays, Camera, Check, Link2, Mail, Package, Radio, Zap } from 'lucide-react';
import type { Integration, IntegrationCreate } from '@/lib/types';
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
  onRefresh,
}: {
  item: Integration;
  onRefresh?: () => void;
}) {
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
        {onRefresh && (
          <button
            type="button"
            className="button subtle"
            style={{ fontSize: '0.75rem', padding: '0.2rem 0.5rem', color: 'var(--text-muted)' }}
            onClick={async () => {
              try {
                await api.deleteIntegration(item.id);
                onRefresh();
              } catch (e) {
                console.error('Failed to disconnect integration:', e);
              }
            }}
          >
            Disconnect
          </button>
        )}
      </div>
    </article>
  );
}

const supportedIntegrations: Array<{
  id: string;
  provider: 'google' | 'microsoft' | 'ring' | 'bee' | 'utility' | 'delivery';
  connection_type: 'email' | 'calendar' | 'camera' | 'wearable' | 'utility' | 'delivery';
  title: string;
  category: string;
  scopes: string[];
  description: string;
  isSimulated?: boolean;
}> = [
  {
    id: 'google-gmail',
    provider: 'google',
    connection_type: 'email',
    title: 'Google Gmail',
    category: 'Email Receipts & Confirmations',
    scopes: ['https://www.googleapis.com/auth/gmail.readonly'],
    description: 'Read-only access to messages for shipping confirmations, receipts, and order updates.',
  },
  {
    id: 'google-calendar',
    provider: 'google',
    connection_type: 'calendar',
    title: 'Google Calendar',
    category: 'Calendar & Appointments',
    scopes: ['https://www.googleapis.com/auth/calendar.readonly'],
    description: 'View scheduled events, meeting times, and calendar appointments.',
  },
  {
    id: 'ms-outlook',
    provider: 'microsoft',
    connection_type: 'email',
    title: 'Microsoft Outlook',
    category: 'Email Receipts & Confirmations',
    scopes: ['Mail.Read'],
    description: 'Read-only access to Outlook email receipts, bills, and confirmation notices.',
  },
  {
    id: 'ms-calendar',
    provider: 'microsoft',
    connection_type: 'calendar',
    title: 'Microsoft Calendar',
    category: 'Calendar & Appointments',
    scopes: ['Calendars.Read'],
    description: 'Read-only access to Outlook calendar events and appointment schedules.',
  },
  {
    id: 'ring-camera',
    provider: 'ring',
    connection_type: 'camera',
    title: 'Ring Video Doorbell',
    category: 'Smart Home / Simulated Camera',
    scopes: ['devices.read', 'events.read'],
    description: 'Simulated Ring camera for package detection, doorbell rings, and motion events.',
    isSimulated: true,
  },
  {
    id: 'bee-wearable',
    provider: 'bee',
    connection_type: 'wearable',
    title: 'Bee AI Wearable',
    category: 'Voice Context / Simulated Wearable',
    scopes: ['transcripts.read'],
    description: 'Simulated audio context for spoken agreements, appointments, and conversation notes.',
    isSimulated: true,
  },
];

export function ConnectAccountModal({
  onClose,
  onConnected,
}: {
  onClose: () => void;
  onConnected?: () => void;
}) {
  const [connectingId, setConnectingId] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  async function handleConnect(integration: typeof supportedIntegrations[number]) {
    setConnectingId(integration.id);
    setErrorMessage(null);
    setSuccessMessage(null);

    try {
      const payload: IntegrationCreate = {
        provider: integration.provider,
        connection_type: integration.connection_type,
        display_name: integration.title,
        status: 'connected',
        scopes: integration.scopes,
        metadata: {
          mock: true,
          demo: false,
          account_kind: 'personal',
        },
      };

      await api.createIntegration(payload);
      setSuccessMessage(`Successfully connected ${integration.title}!`);
      onConnected?.();
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to connect account');
    } finally {
      setConnectingId(null);
    }
  }

  return (
    <Modal title="Connect an Account or Source" onClose={onClose}>
      <p style={{ margin: '0 0 1rem', fontSize: '0.925rem', color: '#475569' }}>
        Connect your authorized email, calendar, or simulated devices. CountOn uses these sources to deterministically evaluate what you’re counting on.
      </p>

      {successMessage && (
        <div style={{ padding: '0.75rem', marginBottom: '1rem', backgroundColor: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '8px', color: '#166534', display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.875rem' }}>
          <Check size={16} />
          {successMessage}
        </div>
      )}

      {errorMessage && (
        <div style={{ padding: '0.75rem', marginBottom: '1rem', backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '8px', color: '#991b1b', fontSize: '0.875rem' }}>
          {errorMessage}
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', maxHeight: '380px', overflowY: 'auto' }}>
        {supportedIntegrations.map((item) => {
          const Icon = icons[item.connection_type] ?? Link2;
          const isConnecting = connectingId === item.id;

          return (
            <div
              key={item.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '0.875rem',
                borderRadius: '8px',
                border: '1px solid #e2e8f0',
                backgroundColor: '#ffffff',
                gap: '0.75rem',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <IconBox icon={Icon} tone={item.isSimulated ? 'orange' : 'blue'} />
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                    <strong style={{ fontSize: '0.95rem' }}>{item.title}</strong>
                    {item.isSimulated && (
                      <span className="demo-badge" style={{ backgroundColor: '#fef3c7', color: '#92400e', fontSize: '0.7rem' }}>
                        SIMULATED
                      </span>
                    )}
                  </div>
                  <p style={{ margin: '0.15rem 0 0', fontSize: '0.8rem', color: '#64748b' }}>
                    {item.description}
                  </p>
                  <span style={{ fontSize: '0.75rem', color: '#94a3b8' }}>
                    Scopes: {item.scopes.map((s) => s.split('/').pop()).join(', ')}
                  </span>
                </div>
              </div>

              <button
                className="button secondary"
                onClick={() => handleConnect(item)}
                disabled={isConnecting}
                style={{ flexShrink: 0, fontSize: '0.85rem' }}
              >
                {isConnecting ? 'Connecting...' : '+ Connect'}
              </button>
            </div>
          );
        })}
      </div>

      <div style={{ marginTop: '1.25rem', paddingTop: '1rem', borderTop: '1px solid #e2e8f0', display: 'flex', justifyContent: 'flex-end' }}>
        <button className="button primary" onClick={onClose}>
          Done
        </button>
      </div>
    </Modal>
  );
}
