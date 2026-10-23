'use client';

import Link from 'next/link';
import { useIdentity } from '@/components/auth-provider';
import { Avatar } from '@/components/app-shell';
import { PageHeader } from '@/components/ui';
import { AccountSecurity } from '@/components/account-security';
import { NotificationPreferences } from '@/components/notification-preferences';
import { ArrowRight, Link2 } from 'lucide-react';

export default function Settings() {
  const { name, email, timeZone } = useIdentity();

  return (
    <>
      <PageHeader
        eyebrow="Preferences & Workspace"
        title="Settings"
        description="Manage your identity, notification interruption policy, and connected evidence integrations."
      />

      <section className="card settings-card" style={{ marginBottom: '1.5rem' }}>
        <div className="profile-heading">
          <Avatar />
          <div>
            <h2>{name}</h2>
            <p>{email}</p>
          </div>
        </div>
        <dl>
          <div>
            <dt>Name</dt>
            <dd>{name}</dd>
          </div>
          <div>
            <dt>Email</dt>
            <dd>{email}</dd>
          </div>
          <div>
            <dt>Timezone</dt>
            <dd>{timeZone ?? Intl.DateTimeFormat().resolvedOptions().timeZone}</dd>
          </div>
        </dl>
        <p className="caption">
          Identity details come from your authenticated account. Sign-in methods are managed by Supabase Auth. Mailbox/calendar permissions are separate.
        </p>
      </section>

      {/* Integration Navigation Card */}
      <section
        className="card"
        style={{
          marginBottom: '1.5rem',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <span
            style={{
              width: '40px',
              height: '40px',
              borderRadius: '10px',
              backgroundColor: '#edf3ff',
              color: '#1a5fd7',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Link2 size={20} />
          </span>
          <div>
            <h3 style={{ margin: 0, fontSize: '1rem' }}>Connected Accounts & Hardware Health</h3>
            <p className="caption">Review live Gmail/Outlook sync health and simulated Ring/Bee hardware fixtures.</p>
          </div>
        </div>
        <Link className="button secondary" href="/settings/integrations">
          Manage integrations <ArrowRight size={15} />
        </Link>
      </section>

      {/* Interruption & Notification Preferences */}
      <div style={{ marginBottom: '1.5rem' }}>
        <NotificationPreferences />
      </div>

      {/* Account Security & Amazon Linking */}
      <AccountSecurity />
    </>
  );
}
