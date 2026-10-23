'use client';

import Link from 'next/link';
import { useCallback } from 'react';
import { PageHeader, Loading, ErrorState } from '@/components/ui';
import { api } from '@/lib/api';
import { useResource } from '@/hooks/use-resource';

export default function QualityDashboard() {
  const load = useCallback((signal: AbortSignal) => api.auditEvents({}, signal), []);
  const history = useResource(load);
  const explanations = history.data?.filter(row => row.event_type === 'EXPLANATION_GENERATED') ?? [];
  return <div>
    <PageHeader title="AI Verification & Quality Hub" description="Inspect persisted CountOn activity. Deterministic evaluation remains authoritative." />
    <section className="card" style={{ padding: '1.5rem' }}>
      <h2>Recorded explanations</h2>
      {history.loading ? <Loading /> : history.error ? <ErrorState error={history.error} retry={history.reload} /> : <>
        <p>{explanations.length} explanation events in your audit history.</p>
        <Link href="/activity" className="button secondary">Inspect source and evaluation history</Link>
      </>}
    </section>
    <section className="card" style={{ padding: '1.5rem', marginTop: '1rem' }}>
      <h2>Human review and benchmark suite</h2>
      <p>A persisted human-review queue and an authenticated cloud benchmark API are not implemented. No model accuracy, token cost or latency result is inferred here.</p>
      <p>Developers can run the documented offline orchestration evaluation; synthetic agreement is separate from human and live-model acceptance.</p>
    </section>
    <section className="card" style={{ padding: '1.5rem', marginTop: '1rem' }}>
      <h2>Recommendations</h2>
      <p>Review actual source-plan suggestions and selected Bee imports in Connected Accounts. A general recommendation inbox is not implemented.</p>
      <Link href="/integrations" className="button secondary">Connected Accounts</Link>
    </section>
  </div>;
}
