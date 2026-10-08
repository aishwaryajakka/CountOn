'use client';
import { useIdentity } from '@/components/auth-provider';
import { Avatar } from '@/components/app-shell';
import { PageHeader } from '@/components/ui';
export default function Settings() {
  const { name, email, timeZone } = useIdentity();
  return <><PageHeader title="Profile / Settings" description="Your personal CountOn workspace." /><section className="card settings-card"><div className="profile-heading"><Avatar /><div><h2>{name}</h2><p>{email}</p></div></div><dl><div><dt>Name</dt><dd>{name}</dd></div><div><dt>Email</dt><dd>{email}</dd></div><div><dt>Timezone</dt><dd>{timeZone ?? Intl.DateTimeFormat().resolvedOptions().timeZone}</dd></div></dl><p className="caption">Identity details come from your authenticated account. Profile editing and notification delivery preferences aren’t available yet.</p></section></>;
}
