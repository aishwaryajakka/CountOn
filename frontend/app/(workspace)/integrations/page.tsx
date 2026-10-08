'use client';
import { useState } from 'react';
import { Link2, ShieldCheck } from 'lucide-react';
import { api } from '@/lib/api';
import { useResource } from '@/hooks/use-resource';
import { ConnectAccountModal, IntegrationCard } from '@/components/integration';
import { EmptyState, ErrorState, IconBox, Loading, PageHeader } from '@/components/ui';
const load = (signal: AbortSignal) => api.integrations(signal);
export default function Integrations() {
  const state = useResource(load); const [modal, setModal] = useState(false);
  return <><PageHeader eyebrow="The right context, in one place" title="Connected Accounts" description="Your sources help CountOn understand what actually happened." action={<button className="button primary" onClick={() => setModal(true)}>+ Connect account</button>} /><div className="card connection-intro"><IconBox icon={ShieldCheck} /><div><h2>Your sources. Your clarity.</h2><p>These account records describe where evidence can come from. Demo connections are clearly labeled; live provider access is not configured.</p></div></div><section className="section"><div className="section-heading"><h2>Your connections{state.data ? ` (${state.data.length})` : ''}</h2><span className="caption">No extra noise</span></div>{state.loading ? <Loading /> : state.error ? <ErrorState error={state.error} retry={state.reload} /> : state.data?.length ? <div className="grid two">{state.data.map(item => <IntegrationCard item={item} key={item.id} />)}</div> : <EmptyState title="No connected accounts yet." description="Your account records will appear here once they’re added." icon={Link2} action={<button className="button secondary" onClick={() => setModal(true)}>Explore connections</button>} />}</section><div className="soft-card connection-bottom"><h3>More context, thoughtfully connected.</h3><p>Email, calendars, utilities, deliveries and more. Future connections will ask for your permission first.</p><button className="text-link" onClick={() => setModal(true)}>Explore supported providers →</button></div>{modal && <ConnectAccountModal onClose={() => setModal(false)} />}</>;
}
