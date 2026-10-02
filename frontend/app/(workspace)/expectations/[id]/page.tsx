'use client';
import { use, useCallback } from 'react';
import Link from 'next/link';
import { ArrowLeft, Link2, ShieldCheck } from 'lucide-react';
import { api } from '@/lib/api';
import { useResource } from '@/hooks/use-resource';
import { Badge, EmptyState, ErrorState, Loading } from '@/components/ui';
import { ComparisonCards, EvidenceCard, EvidenceContext, Timeline } from '@/components/expectation';
import { displayTitle, getExpectationPresentationStatus, humanize } from '@/lib/presentation';

export default function ExpectationDetail({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const load = useCallback(async (signal: AbortSignal) => {
    const expectation = await api.expectation(id, signal);
    const [evidence, evaluations] = await Promise.all([api.evidence(id, signal), api.evaluations(id, signal)]);
    const latest = evaluations.length ? await api.latest(id, signal) : null;
    return { expectation, evidence, evaluations, latest };
  }, [id]);
  const state = useResource(load);
  return <><Link className="back-link" href="/expectations"><ArrowLeft size={17} />Back to Expectations</Link>{state.loading ? <Loading label="Loading expectation" /> : state.error ? <ErrorState error={state.error} retry={state.reload} /> : state.data && <><header className="detail-header"><div className="title-badge"><h1>{displayTitle(state.data.expectation)}</h1><Badge status={getExpectationPresentationStatus(state.data.expectation, state.data.latest)} /></div><p className="claim">“{state.data.expectation.claim}”</p></header><div className="detail-layout"><div className="detail-main"><ComparisonCards expectation={state.data.expectation} evaluation={state.data.latest} evidence={state.data.evidence} /><section className="card explanation-card"><EvidenceContext evaluation={state.data.latest} evidence={state.data.evidence} /><p className="caption reasoning-note"><ShieldCheck size={15} />Deterministic evaluation · no AI-generated explanation</p></section><section className="section"><div className="section-heading"><h2>Evidence gathered</h2><span className="caption">{state.data.evidence.length} recorded observations</span></div>{state.data.evidence.length ? <div className="evidence-grid">{state.data.evidence.map(item => <EvidenceCard item={item} key={item.id} />)}</div> : <EmptyState title="Waiting for evidence" description="Observations for this expectation will appear here when they’re available." />}</section><Timeline expectation={state.data.expectation} evidence={state.data.evidence} evaluations={state.data.evaluations} /></div><aside className="detail-aside"><section className="card"><h2><Link2 size={19} />Sources used</h2><p>Evidence sources associated with this expectation.</p><ul className="source-list">{state.data.expectation.evidence_sources.map(source => <li key={source}><span className="status-dot" />{humanize(source)}</li>)}</ul>{!state.data.expectation.evidence_sources.length && <p>No sources specified yet.</p>}<Link className="button secondary full" href="/integrations">View connected accounts</Link></section><section className="soft-card"><ShieldCheck size={23} /><h3>A clear record</h3><p>The latest relevant observation is selected by when it was observed, even if it arrived later.</p><p className="caption">Context can explain what changed; it doesn’t prove why.</p></section></aside></div></>}</>;
}
