'use client';
import Link from 'next/link';
import { ArrowDownRight, ArrowRight, ArrowUpRight, CalendarDays, CheckCircle2, Clock3, Lightbulb, Moon, Package, Wrench, Zap, type LucideIcon } from 'lucide-react';
import type { Evidence, Evaluation, Expectation, WatchedExpectation } from '@/lib/types';
import { contextSignals, displayTitle, evidenceValue, expectedText, formatDate, getExpectationPresentationStatus, humanize, latestMetricEvidence, number, observedText, reasoningText } from '@/lib/presentation';
import { useIdentity } from './auth-provider';
import { Badge, IconBox } from './ui';

export function expectationIcon(expectation: Expectation): LucideIcon {
  const title = displayTitle(expectation);
  return title === 'Electricity bill' ? Zap : title === 'Package delivery' ? Package : title === 'Plumber appointment' ? Wrench : title.includes('meetings') ? Moon : CalendarDays;
}
export function ExpectationCard({ row }: { row: WatchedExpectation }) {
  const { expectation, latest } = row;
  const status = getExpectationPresentationStatus(expectation, latest);
  const { timeZone } = useIdentity();
  return <article className={`card expectation-card ${status === 'attention' ? 'attention-card' : ''}`}><div className="card-top"><IconBox icon={expectationIcon(expectation)} tone={status === 'attention' ? 'orange' : 'blue'} /><Badge status={status} /></div><h3><Link href={`/expectations/${expectation.id}`}>{displayTitle(expectation)}</Link></h3><p className="claim">“{expectation.claim}”</p><div className="source-chips">{expectation.evidence_sources.map(source => <span key={source}>{humanize(source)}</span>)}</div><div className="card-bottom"><span><Clock3 size={14} />{formatDate(latest?.created_at ?? expectation.updated_at, timeZone)}</span><Link className="icon-button" href={`/expectations/${expectation.id}`} aria-label={`View ${displayTitle(expectation)}`}><ArrowRight size={18} /></Link></div></article>;
}
export function ComparisonCards({ expectation, evaluation, evidence }: { expectation: Expectation; evaluation: Evaluation | null; evidence: Evidence[] }) {
  const observedEvidence = evidence.find(item => item.id === evaluation?.observed.evidence_id) ?? latestMetricEvidence(evidence, expectation.metric);
  const unit = observedEvidence?.unit;
  const status = getExpectationPresentationStatus(expectation, evaluation);
  const target = expectation.target_value ?? expectation.baseline;
  const actual = evaluation?.observed.value;
  const difference = typeof actual === 'number' && target != null ? actual - target : null;
  return <div className="comparison-grid"><div className="comparison expected"><span className="overline">What you expected</span><strong>{expectedText(expectation, unit)}</strong><p>Your criteria for {expectation.metric ? humanize(expectation.metric).toLowerCase() : 'this expectation'}.</p></div><div className={`comparison observed ${status}`}><div className="section-heading"><span className="overline">Latest evaluated observation</span><Badge status={status} /></div><strong>{observedText(evaluation, unit)}</strong><p>{difference != null ? `Difference from target: ${difference > 0 ? '+' : ''}${number(difference, unit)}` : evaluation ? 'Based on the latest evaluation.' : 'An evaluation has not been recorded yet.'}</p></div></div>;
}
export function EvidenceContext({ evaluation, evidence }: { evaluation: Evaluation | null; evidence: Evidence[] }) {
  const signals = contextSignals(evidence);
  return <div className="explanation"><IconBox icon={Lightbulb} tone="blue" /><div><h3>What the evidence tells us</h3><p>{reasoningText(evaluation)}</p>{signals.length > 0 && <><div className="signal-chips">{signals.map(signal => <span key={signal.label} className={signal.value > 0 ? 'up' : 'down'}>{signal.value > 0 ? <ArrowUpRight size={15} /> : <ArrowDownRight size={15} />}{signal.label}: {number(signal.value, 'percent')}</span>)}</div><p className="caption">These observations add context. They do not establish the cause of the change.</p></>}</div></div>;
}
export function AttentionCard({ row, evidence }: { row: WatchedExpectation; evidence: Evidence[] }) {
  return <article className="card priority-card"><div className="priority-heading"><IconBox icon={expectationIcon(row.expectation)} tone="orange" /><div><div className="title-badge"><h2>{displayTitle(row.expectation)}</h2><Badge status="attention" /></div><p>{row.expectation.claim}</p></div></div><ComparisonCards expectation={row.expectation} evaluation={row.latest} evidence={evidence} /><EvidenceContext evaluation={row.latest} evidence={evidence} /><div className="priority-footer"><span className="caption">Based on recorded evidence</span><Link className="text-link" href={`/expectations/${row.expectation.id}`}>See why <ArrowRight size={17} /></Link></div></article>;
}
export function EvidenceCard({ item }: { item: Evidence }) {
  const { timeZone } = useIdentity();
  return <article className="card evidence-card"><IconBox icon={item.metric === 'total_cost' ? Zap : CalendarDays} /><span className="overline">{humanize(item.metric ?? 'Observation')}</span><strong>{evidenceValue(item, timeZone)}</strong><p>{humanize(item.source)}</p><footer><time dateTime={item.observed_at}>{formatDate(item.observed_at, timeZone)}</time><span>{new Intl.NumberFormat(undefined, { style: 'percent', maximumFractionDigits: 0 }).format(item.confidence)} confidence</span></footer></article>;
}
export function Timeline({ expectation, evidence, evaluations }: { expectation: Expectation; evidence: Evidence[]; evaluations: Evaluation[] }) {
  const { timeZone } = useIdentity();
  const events = [{ id: expectation.id, at: expectation.created_at, title: 'Expectation created', description: expectation.claim, tone: 'blue', rank: 0 }, ...evidence.map(item => ({ id: item.id, at: item.observed_at, title: `${humanize(item.source)} observed`, description: `${humanize(item.metric ?? 'Observation')}: ${evidenceValue(item, timeZone)}`, tone: 'blue', rank: 1 })), ...evaluations.map(item => ({ id: item.id, at: item.created_at, title: item.result === 'MISMATCH' ? 'Mismatch detected' : item.result === 'MATCH' ? 'Matched' : 'Waiting for evidence', description: reasoningText(item), tone: item.result === 'MISMATCH' ? 'orange' : 'blue', rank: 2 }))].sort((a, b) => Date.parse(a.at) - Date.parse(b.at) || a.rank - b.rank || a.id.localeCompare(b.id));
  return <section className="card timeline-card"><div className="section-heading"><h2>Timeline</h2><span className="caption">Recorded activity</span></div><ol className="timeline">{events.map(event => <li key={event.id} className={event.tone}><span className="timeline-node" aria-hidden="true" /><div><strong>{event.title}</strong><p>{event.description}</p></div><time dateTime={event.at}>{formatDate(event.at, timeZone)}</time></li>)}</ol></section>;
}
export function HealthyCard() { return <div className="card healthy-card"><IconBox icon={CheckCircle2} tone="green" /><div><h2>Everything looks as expected.</h2><p>CountOn is still watching in the background.</p><span className="caption">Evidence updates appear when they’re available.</span></div></div>; }
