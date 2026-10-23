'use client';
import Link from 'next/link';
import { ArrowDownRight, ArrowRight, ArrowUpRight, CalendarDays, CheckCircle2, Clock3, Lightbulb, Moon, Package, Settings, Wrench, Zap, type LucideIcon } from 'lucide-react';
import type { Evidence, Evaluation, Expectation, WatchedExpectation } from '@/lib/types';
import { contextSignals, displayTitle, evidenceValue, expectedText, formatDate, getExpectationPresentationStatus, humanize, evidenceSourceLabel, latestMetricEvidence, number, observedText, reasoningText } from '@/lib/presentation';
import { useIdentity } from './auth-provider';
import { Badge, IconBox } from './ui';

export function expectationIcon(expectation: Expectation): LucideIcon {
  const title = displayTitle(expectation);
  return title === 'Electricity bill' ? Zap : title === 'Package delivery' ? Package : title === 'Plumber appointment' ? Wrench : title.includes('meetings') ? Moon : CalendarDays;
}
export function ExpectationCard({ row, onManage }: { row: WatchedExpectation; onManage?: (expectation: Expectation) => void }) {
  const { expectation, latest } = row;
  const status = getExpectationPresentationStatus(expectation, latest);
  const { timeZone } = useIdentity();

  return (
    <article className={`card expectation-card ${status === 'attention' ? 'attention-card' : ''}`}>
      <div className="card-top">
        <IconBox icon={expectationIcon(expectation)} tone={status === 'attention' ? 'orange' : 'blue'} />
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <Badge status={status} />
          {onManage && (
            <button
              className="icon-button"
              type="button"
              onClick={() => onManage(expectation)}
              aria-label={`Manage ${displayTitle(expectation)}`}
              title="Edit or manage lifecycle"
              style={{ width: '28px', height: '28px', padding: '4px' }}
            >
              <Settings size={15} />
            </button>
          )}
        </div>
      </div>

      <h3>
        <Link href={`/expectations/${expectation.id}`}>{displayTitle(expectation)}</Link>
      </h3>
      <p className="claim">“{expectation.claim}”</p>

      {/* Structured Monitoring Criteria Summary */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: '0.5rem',
          margin: '0.6rem 0',
          padding: '0.6rem 0.75rem',
          backgroundColor: 'var(--color-bg-app, #f8fafc)',
          borderRadius: '8px',
          fontSize: '0.8rem',
          border: '1px solid var(--color-border, #e6ebf2)',
        }}
      >
        <div>
          <span className="overline" style={{ fontSize: '0.65rem' }}>Expected</span>
          <span style={{ fontWeight: 600, display: 'block', color: 'var(--color-brand-primary, #1a5fd7)' }}>
            {expectedText(expectation)}
          </span>
        </div>
        <div>
          <span className="overline" style={{ fontSize: '0.65rem' }}>Observed</span>
          <span
            style={{
              fontWeight: 600,
              display: 'block',
              color: status === 'attention' ? 'var(--color-status-attention, #ac3d10)' : 'var(--color-text-primary, #2d3142)',
            }}
          >
            {observedText(latest)}
          </span>
        </div>
        <div>
          <span className="overline" style={{ fontSize: '0.65rem' }}>Deadline</span>
          <span className="caption" style={{ display: 'block' }}>
            {expectation.deadline ? formatDate(expectation.deadline, timeZone) : 'No deadline'}
          </span>
        </div>
        <div>
          <span className="overline" style={{ fontSize: '0.65rem' }}>Last Evaluated</span>
          <span className="caption" style={{ display: 'block' }}>
            {latest ? formatDate(latest.created_at, timeZone) : 'Awaiting signal'}
          </span>
        </div>
      </div>

      <div className="source-chips">
        {expectation.evidence_sources.map((source) => (
          <span key={source}>{humanize(source)}</span>
        ))}
        {expectation.evidence_sources.length === 0 && <span className="caption">No bound sources</span>}
      </div>

      <div className="card-bottom">
        <span>
          <Clock3 size={14} />
          {expectation.evidence_sources.length} source{expectation.evidence_sources.length === 1 ? '' : 's'} ·{' '}
          {formatDate(latest?.created_at ?? expectation.updated_at, timeZone)}
        </span>
        <Link className="icon-button" href={`/expectations/${expectation.id}`} aria-label={`View ${displayTitle(expectation)}`}>
          <ArrowRight size={18} />
        </Link>
      </div>
    </article>
  );
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
  const isSimulated = item.source.endsWith('_simulator') || item.raw_data.simulated === true;
  const provTag = isSimulated ? 'SIMULATED' : typeof item.raw_data.provenance === 'string' ? item.raw_data.provenance : 'Provenance not recorded';

  return (
    <article className="card evidence-card" style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '0.5rem' }}>
        <IconBox icon={item.metric === 'total_cost' ? Zap : CalendarDays} />
        <span
          style={{
            fontSize: '0.675rem',
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            padding: '0.15rem 0.5rem',
            borderRadius: '4px',
            backgroundColor: isSimulated ? '#fef3c7' : '#edf3ff',
            color: isSimulated ? '#92400e' : '#1a5fd7',
            border: `1px solid ${isSimulated ? '#fde68a' : '#dce7fa'}`,
          }}
        >
          {provTag}
        </span>
      </div>
      <span className="overline">{humanize(item.metric ?? 'Observation')}</span>
      <strong>{evidenceValue(item, timeZone)}</strong>
      <p>{evidenceSourceLabel(item)}</p>
      {isSimulated && (
        <span className="caption" style={{ color: '#92400e', fontSize: '0.725rem' }}>
          Hardware simulation fixture · Not physical device
        </span>
      )}
      <footer style={{ marginTop: 'auto', paddingTop: '0.5rem', borderTop: '1px solid var(--color-border, #e6ebf2)' }}>
        <time dateTime={item.observed_at}>{formatDate(item.observed_at, timeZone)}</time>
        <span>{new Intl.NumberFormat(undefined, { style: 'percent', maximumFractionDigits: 0 }).format(item.confidence)} confidence</span>
      </footer>
    </article>
  );
}
export function Timeline({ expectation, evidence, evaluations }: { expectation: Expectation; evidence: Evidence[]; evaluations: Evaluation[] }) {
  const { timeZone } = useIdentity();
  const events = [{ id: expectation.id, at: expectation.created_at, title: 'Expectation created', description: expectation.claim, tone: 'blue', rank: 0 }, ...evidence.map(item => ({ id: item.id, at: item.observed_at, title: `${evidenceSourceLabel(item)} observed`, description: `${humanize(item.metric ?? 'Observation')}: ${evidenceValue(item, timeZone)}`, tone: 'blue', rank: 1 })), ...evaluations.map(item => ({ id: item.id, at: item.created_at, title: item.result === 'MISMATCH' ? 'Mismatch detected' : item.result === 'MATCH' ? 'Matched' : 'Waiting for evidence', description: reasoningText(item), tone: item.result === 'MISMATCH' ? 'orange' : 'blue', rank: 2 }))].sort((a, b) => Date.parse(a.at) - Date.parse(b.at) || a.rank - b.rank || a.id.localeCompare(b.id));
  return <section className="card timeline-card"><div className="section-heading"><h2>Timeline</h2><span className="caption">Recorded activity</span></div><ol className="timeline">{events.map(event => <li key={event.id} className={event.tone}><span className="timeline-node" aria-hidden="true" /><div><strong>{event.title}</strong><p>{event.description}</p></div><time dateTime={event.at}>{formatDate(event.at, timeZone)}</time></li>)}</ol></section>;
}
export function HealthyCard() { return <div className="card healthy-card"><IconBox icon={CheckCircle2} tone="green" /><div><h2>Everything looks as expected.</h2><p>CountOn is still watching in the background.</p><span className="caption">Evidence updates appear when they’re available.</span></div></div>; }
export { RealityDecisionCard } from './reality-decision-card';
