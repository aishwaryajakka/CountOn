'use client';

import Link from 'next/link';
import {
  Activity,
  AlertTriangle,
  CheckCircle2,
  Hourglass,
  ShieldCheck,
  Sparkles,
} from 'lucide-react';
import type { Evaluation, Evidence, Expectation } from '@/lib/types';
import {
  expectedText,
  formatDate,
  getExpectationPresentationStatus,
  humanize,
  latestMetricEvidence,
  number,
  observedText,
  reasoningText,
  statusLabels,
} from '@/lib/presentation';
import { useIdentity } from './auth-provider';
import { Badge, IconBox } from './ui';

export function getEvaluatorName(type: Expectation['type']): string {
  switch (type) {
    case 'numeric_comparison':
      return 'NumericEvaluator';
    case 'boolean':
      return 'BooleanEvaluator';
    case 'temporal':
    case 'event':
      return 'TemporalEvaluator';
    default:
      return 'DeterministicEvaluator';
  }
}

export function getSourceProvenanceTag(source: string, item?: Evidence): { label: string; simulated: boolean } {
  if (source.endsWith('_simulator') || item?.raw_data.simulated === true) {
    return { label: source.includes('ring') ? 'SIMULATED_RING' : source.includes('bee') ? 'SIMULATED_BEE' : 'SIMULATED', simulated: true };
  }
  const provenance = item?.raw_data.provenance;
  return { label: typeof provenance === 'string' ? provenance : 'Provenance not recorded', simulated: false };
}

interface RealityDecisionCardProps {
  expectation: Expectation;
  evaluation: Evaluation | null;
  evidence?: Evidence[];
  onAskWhy?: () => void;
  showActions?: boolean;
  className?: string;
}

export function RealityDecisionCard({
  expectation,
  evaluation,
  evidence = [],
  onAskWhy,
  showActions = true,
  className = '',
}: RealityDecisionCardProps) {
  const { timeZone } = useIdentity();
  const status = getExpectationPresentationStatus(expectation, evaluation);
  const evaluatorName = getEvaluatorName(expectation.type);

  const observedItem =
    evaluation
      ? evidence.find((item) => item.id === evaluation.observed.evidence_id)
      : latestMetricEvidence(evidence, expectation.metric);
  const unit = observedItem?.unit;

  const target = evaluation?.expected.target;
  const actual = (evaluation?.observed as { value?: unknown })?.value;
  const difference = typeof actual === 'number' && typeof target === 'number' && Number.isFinite(actual) && Number.isFinite(target) ? actual - target : null;

  const sources = expectation.evidence_sources.map(source => getSourceProvenanceTag(source, evidence.find(item => item.source === source)));
  const hasSimulated = sources.some((s) => s.simulated);

  // The persisted evaluator includes tolerance, chronology and evidence policy.
  // Display its reasoning instead of recomputing a potentially different verdict.
  const formula = reasoningText(evaluation);

  return (
    <div
      className={`card reality-decision-card ${status === 'attention' ? 'attention-card' : ''} ${className}`}
      style={{
        padding: '1.5rem',
        border:
          status === 'attention'
            ? '1.5px solid var(--color-brand-accent, #f26327)'
            : '1px solid var(--color-border, #e6ebf2)',
        borderRadius: '16px',
        backgroundColor: 'var(--color-bg-surface, #ffffff)',
      }}
    >
      {/* Step 1 & Header: Thesis Pipeline Flow */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '0.75rem',
          borderBottom: '1px solid var(--color-border, #e6ebf2)',
          paddingBottom: '0.75rem',
          marginBottom: '1rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <IconBox
            icon={status === 'attention' ? AlertTriangle : status === 'match' ? CheckCircle2 : Hourglass}
            tone={status === 'attention' ? 'orange' : status === 'match' ? 'green' : 'blue'}
          />
          <div>
            <span
              className="overline"
              style={{
                fontSize: '0.7rem',
                letterSpacing: '0.08em',
                fontWeight: 700,
                color: 'var(--color-text-secondary, #667085)',
              }}
            >
              CountOn Reality Engine
            </span>
            <strong style={{ fontSize: '1rem', display: 'block', color: 'var(--color-text-primary, #2d3142)' }}>
              {status === 'resolved' || status === 'cancelled'
                ? statusLabels[status]
                : status === 'attention'
                ? 'Mismatch Detected'
                : status === 'match'
                ? 'Quiet Match'
                : 'Waiting for Evidence'}
            </strong>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span
            style={{
              fontSize: '0.75rem',
              fontWeight: 600,
              padding: '0.2rem 0.6rem',
              borderRadius: '99px',
              backgroundColor: 'var(--color-bg-secondary, #f3f6fa)',
              color: 'var(--color-brand-primary, #1a5fd7)',
            }}
          >
            {evaluatorName}
          </span>
          <Badge status={status} />
        </div>
      </div>

      {/* Step 2: Architecture Pipeline Diagram */}
      <div
        className="pipeline-flow"
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))',
          gap: '0.75rem',
          marginBottom: '1.25rem',
          backgroundColor: 'var(--color-bg-app, #f8fafc)',
          padding: '0.875rem',
          borderRadius: '12px',
          border: '1px solid var(--color-border, #e6ebf2)',
        }}
      >
        {/* Expected */}
        <div style={{ padding: '0.4rem 0.5rem' }}>
          <span className="overline" style={{ fontSize: '0.65rem' }}>
            1. Expected
          </span>
          <strong
            style={{
              display: 'block',
              fontSize: '0.9rem',
              color: 'var(--color-brand-primary, #1a5fd7)',
              marginTop: '2px',
            }}
          >
            {expectedText(expectation, unit, evaluation)}
          </strong>
          <span className="caption" style={{ fontSize: '0.7rem' }}>
            Criteria defined
          </span>
        </div>

        {/* Observed */}
        <div style={{ padding: '0.4rem 0.5rem', borderLeft: '1px solid var(--color-border, #e6ebf2)' }}>
          <span className="overline" style={{ fontSize: '0.65rem' }}>
            2. Observed
          </span>
          <strong
            style={{
              display: 'block',
              fontSize: '0.9rem',
              color: status === 'attention' ? 'var(--color-status-attention, #ac3d10)' : 'var(--color-text-primary, #2d3142)',
              marginTop: '2px',
            }}
          >
            {observedText(evaluation, unit)}
          </strong>
          <span className="caption" style={{ fontSize: '0.7rem' }}>
            {observedItem ? `${formatDate(observedItem.observed_at, timeZone)}` : 'No signal yet'}
          </span>
        </div>

        {/* Deterministic Evaluation */}
        <div style={{ padding: '0.4rem 0.5rem', borderLeft: '1px solid var(--color-border, #e6ebf2)' }}>
          <span className="overline" style={{ fontSize: '0.65rem' }}>
            3. Deterministic Result
          </span>
          <strong
            style={{
              display: 'block',
              fontSize: '0.9rem',
              color:
                evaluation?.result === 'MATCH'
                  ? 'var(--color-status-match, #237a53)'
                  : evaluation?.result === 'MISMATCH'
                  ? 'var(--color-status-attention, #ac3d10)'
                  : 'var(--color-status-waiting, #566174)',
              marginTop: '2px',
            }}
          >
            {evaluation?.result ?? 'UNKNOWN'}
          </strong>
          <span className="caption" style={{ fontSize: '0.7rem', display: 'block', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {formula}
          </span>
        </div>

        {/* Evidence Signals */}
        <div style={{ padding: '0.4rem 0.5rem', borderLeft: '1px solid var(--color-border, #e6ebf2)' }}>
          <span className="overline" style={{ fontSize: '0.65rem' }}>
            4. Evidence Context
          </span>
          <strong style={{ display: 'block', fontSize: '0.9rem', marginTop: '2px' }}>
            {evidence.length} signal{evidence.length === 1 ? '' : 's'}
          </strong>
          <span className="caption" style={{ fontSize: '0.7rem' }}>
            {hasSimulated ? 'Simulated fixture' : 'Recorded source metadata'}
          </span>
        </div>
      </div>

      {/* Difference / Insight Callout if Mismatch */}
      {status === 'attention' && difference != null && (
        <div
          style={{
            padding: '0.75rem 1rem',
            backgroundColor: 'var(--color-soft-orange, #fff1ea)',
            border: '1px solid #fed7aa',
            borderRadius: '10px',
            marginBottom: '1rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '0.5rem',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <AlertTriangle size={17} color="var(--color-brand-accent, #f26327)" />
            <span style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--color-status-attention, #ac3d10)' }}>
              Variance: {difference > 0 ? '+' : ''}
              {number(difference, unit)} from target threshold
            </span>
          </div>
          <span className="caption" style={{ color: 'var(--color-status-attention, #ac3d10)', fontWeight: 500 }}>
            Deterministic exception
          </span>
        </div>
      )}

      {/* Source Provenance Chips */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          flexWrap: 'wrap',
          marginBottom: showActions ? '1rem' : 0,
        }}
      >
        <span className="caption" style={{ fontWeight: 600 }}>
          Sources:
        </span>
        {expectation.evidence_sources.map((src) => {
          const prov = getSourceProvenanceTag(src, evidence.find(item => item.source === src));
          return (
            <span
              key={src}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.35rem',
                fontSize: '0.75rem',
                padding: '0.2rem 0.5rem',
                borderRadius: '6px',
                backgroundColor: prov.simulated ? '#fef3c7' : '#edf3ff',
                color: prov.simulated ? '#92400e' : '#1a5fd7',
                border: `1px solid ${prov.simulated ? '#fde68a' : '#dce7fa'}`,
                fontWeight: 600,
              }}
            >
              {humanize(src)} · {prov.label}
            </span>
          );
        })}
        {hasSimulated && (
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.25rem',
              fontSize: '0.725rem',
              padding: '0.2rem 0.5rem',
              borderRadius: '6px',
              backgroundColor: '#fffbeb',
              color: '#b45309',
              border: '1px solid #fde68a',
              fontWeight: 600,
            }}
          >
            SIMULATED (NO LIVE HARDWARE)
          </span>
        )}
        {expectation.evidence_sources.length === 0 && (
          <span className="caption">No bound sources</span>
        )}
      </div>

      {/* Actions */}
      {showActions && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: '0.75rem',
            paddingTop: '0.75rem',
            borderTop: '1px solid var(--color-border, #e6ebf2)',
          }}
        >
          <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
            <Link className="button secondary" href={`/expectations/${expectation.id}`} style={{ fontSize: '0.825rem' }}>
              <Activity size={15} />
              View Evidence & History
            </Link>

            {status === 'attention' && (
              <Link
                className="button primary"
                href={`/alexa?expectationId=${expectation.id}&starter=${encodeURIComponent("Why did it fail?")}`}
                onClick={() => onAskWhy?.()}
                style={{ fontSize: '0.825rem' }}
              >
                <Sparkles size={15} />
                Ask CountOn Why
              </Link>
            )}
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--color-text-secondary, #667085)', fontSize: '0.75rem' }}>
            <ShieldCheck size={14} color="var(--color-status-match, #237a53)" />
            <span>Deterministic engine decides · AI never votes on outcome</span>
          </div>
        </div>
      )}
    </div>
  );
}
