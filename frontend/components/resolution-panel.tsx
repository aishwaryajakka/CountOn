'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  ArrowRight,
  CheckCircle2,
  Edit3,
  ExternalLink,
  Hourglass,
  RefreshCw,
  ShieldAlert,
  Sparkles,
} from 'lucide-react';
import type { Evaluation, Evidence, Expectation } from '@/lib/types';
import {
  expectedText,
  formatDate,
  getExpectationPresentationStatus,
  latestMetricEvidence,
  number,
  observedText,
} from '@/lib/presentation';
import { useIdentity } from './auth-provider';
import { api } from '@/lib/api';

interface ResolutionPanelProps {
  expectation: Expectation;
  evaluation: Evaluation | null;
  evidence?: Evidence[];
  onManage?: () => void;
  onRefresh?: () => void;
  onAskWhy?: () => void;
  className?: string;
}

export function ResolutionPanel({
  expectation,
  evaluation,
  evidence = [],
  onManage,
  onRefresh,
  onAskWhy,
  className = '',
}: ResolutionPanelProps) {
  const { timeZone } = useIdentity();
  const status = getExpectationPresentationStatus(expectation, evaluation);
  const [resolving, setResolving] = useState(false);
  const [resolvedMsg, setResolvedMsg] = useState<string | null>(null);

  const observedItem =
    evaluation
      ? evidence.find((item) => item.id === evaluation.observed.evidence_id)
      : latestMetricEvidence(evidence, expectation.metric);
  const unit = observedItem?.unit;

  const target = evaluation?.expected.target;
  const actual = (evaluation?.observed as { value?: unknown })?.value;
  const difference = typeof actual === 'number' && typeof target === 'number' && Number.isFinite(actual) && Number.isFinite(target) ? actual - target : null;

  async function handleResolve() {
    if (resolving) return;
    setResolving(true);
    try {
      await api.updateExpectation(expectation.id, { status: 'resolved' });
      setResolvedMsg('Expectation marked as resolved.');
      onRefresh?.();
    } catch {
      setResolvedMsg('Could not resolve expectation. Try again later.');
    } finally {
      setResolving(false);
    }
  }

  if (status === 'resolved' || status === 'cancelled') return null;

  // 1. MISMATCH RESOLUTION PANEL
  if (status === 'attention') {
    return (
      <section
        className={`card resolution-panel mismatch-panel ${className}`}
        style={{
          padding: '1.5rem',
          backgroundColor: '#fffaf8',
          border: '1.5px solid #fed7aa',
          borderRadius: '16px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '1rem' }}>
          <span
            style={{
              width: '36px',
              height: '36px',
              borderRadius: '10px',
              backgroundColor: '#ffedd5',
              color: '#c2410c',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <ShieldAlert size={20} />
          </span>
          <div>
            <h3 style={{ margin: 0, color: '#9a3412', fontSize: '1.1rem' }}>CountOn detected a mismatch</h3>
            <p className="caption" style={{ color: '#c2410c' }}>
              Reality disagreed with your expected conditions.
            </p>
          </div>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
            gap: '1rem',
            padding: '1rem',
            backgroundColor: '#ffffff',
            borderRadius: '12px',
            border: '1px solid #fed7aa',
            marginBottom: '1.25rem',
          }}
        >
          <div>
            <span className="overline" style={{ fontSize: '0.7rem' }}>
              Expected
            </span>
            <strong style={{ display: 'block', fontSize: '1.05rem', marginTop: '3px' }}>
              {expectedText(expectation, unit, evaluation)}
            </strong>
          </div>

          <div>
            <span className="overline" style={{ fontSize: '0.7rem' }}>
              Observed
            </span>
            <strong style={{ display: 'block', fontSize: '1.05rem', color: '#c2410c', marginTop: '3px' }}>
              {observedText(evaluation, unit)}
            </strong>
          </div>

          {difference != null && (
            <div>
              <span className="overline" style={{ fontSize: '0.7rem' }}>
                Variance
              </span>
              <strong style={{ display: 'block', fontSize: '1.05rem', color: '#c2410c', marginTop: '3px' }}>
                {difference > 0 ? '+' : ''}
                {number(difference, unit)}
              </strong>
            </div>
          )}
        </div>

        {resolvedMsg && (
          <p style={{ margin: '0 0 1rem', fontSize: '0.85rem', color: '#15803d', fontWeight: 600 }}>
            {resolvedMsg}
          </p>
        )}

        <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <Link
            className="button primary"
            href={`/alexa?expectationId=${expectation.id}&starter=${encodeURIComponent("Why did it fail?")}`}
            onClick={() => onAskWhy?.()}
          >
            <Sparkles size={16} />
            Ask CountOn Why
          </Link>

          {onManage && (
            <button className="button secondary" onClick={onManage}>
              <Edit3 size={15} />
              Update Criteria
            </button>
          )}

          <button className="button ghost" onClick={handleResolve} disabled={resolving}>
            <CheckCircle2 size={15} />
            {resolving ? 'Resolving…' : 'Mark Resolved'}
          </button>

          <a href="#evidence-section" className="text-link" style={{ marginLeft: 'auto', fontSize: '0.85rem' }}>
            Investigate evidence <ArrowRight size={14} />
          </a>
        </div>
      </section>
    );
  }

  // 2. UNKNOWN / WAITING FOR EVIDENCE PANEL
  if (status === 'waiting' || status === 'monitoring') {
    return (
      <section
        className={`card resolution-panel unknown-panel ${className}`}
        style={{
          padding: '1.5rem',
          backgroundColor: '#f8fafc',
          border: '1px solid #e2e8f0',
          borderRadius: '16px',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '1rem' }}>
          <span
            style={{
              width: '36px',
              height: '36px',
              borderRadius: '10px',
              backgroundColor: '#e2e8f0',
              color: '#475569',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <Hourglass size={19} />
          </span>
          <div>
            <h3 style={{ margin: 0, color: '#1e293b', fontSize: '1.05rem' }}>WAITING FOR EVIDENCE</h3>
            <p className="caption">
              CountOn can’t verify this yet. Missing evidence is not failure — monitoring remains active.
            </p>
          </div>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
            gap: '1rem',
            padding: '1rem',
            backgroundColor: '#ffffff',
            borderRadius: '12px',
            border: '1px solid #e2e8f0',
            marginBottom: '1.25rem',
          }}
        >
          <div>
            <span className="overline" style={{ fontSize: '0.7rem' }}>
              Expected Condition
            </span>
            <strong style={{ display: 'block', fontSize: '0.95rem', marginTop: '2px' }}>
              {expectedText(expectation, unit, evaluation)}
            </strong>
          </div>

          <div>
            <span className="overline" style={{ fontSize: '0.7rem' }}>
              Evidence Signals
            </span>
            <strong style={{ display: 'block', fontSize: '0.95rem', marginTop: '2px' }}>
              {evidence.length} observation{evidence.length === 1 ? '' : 's'} recorded
            </strong>
          </div>

          <div>
            <span className="overline" style={{ fontSize: '0.7rem' }}>
              Deadline
            </span>
            <strong style={{ display: 'block', fontSize: '0.95rem', marginTop: '2px' }}>
              {expectation.deadline ? formatDate(expectation.deadline, timeZone) : 'No explicit deadline'}
            </strong>
          </div>

          <div>
            <span className="overline" style={{ fontSize: '0.7rem' }}>
              Status
            </span>
            <strong style={{ display: 'block', fontSize: '0.95rem', color: '#64748b', marginTop: '2px' }}>
              UNKNOWN — Still Watching
            </strong>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <Link className="button secondary" href="/demos">
            <ExternalLink size={15} />
            Test with Simulator
          </Link>

          {onRefresh && (
            <button className="button ghost" onClick={onRefresh}>
              <RefreshCw size={15} />
              Re-check Now
            </button>
          )}

          <span className="caption" style={{ marginLeft: 'auto' }}>
            CountOn stays quiet until verified evidence arrives.
          </span>
        </div>
      </section>
    );
  }

  // 3. MATCH STATE PANEL
  return (
    <section
      className={`card resolution-panel match-panel ${className}`}
      style={{
        padding: '1.5rem',
        backgroundColor: '#f0fdf4',
        border: '1px solid #bbf7d0',
        borderRadius: '16px',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', marginBottom: '0.75rem' }}>
        <span
          style={{
            width: '36px',
            height: '36px',
            borderRadius: '10px',
            backgroundColor: '#dcfce7',
            color: '#15803d',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <CheckCircle2 size={20} />
        </span>
        <div>
          <h3 style={{ margin: 0, color: '#166534', fontSize: '1.05rem' }}>Confirmed by Evidence</h3>
          <p className="caption" style={{ color: '#15803d' }}>
            Silence is success. All observations align with your expected criteria.
          </p>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap', alignItems: 'center', marginTop: '1rem' }}>
        {onManage && (
          <button className="button secondary" onClick={onManage}>
            <Edit3 size={15} />
            Edit Criteria
          </button>
        )}
        <button className="button ghost" onClick={handleResolve} disabled={resolving}>
          <CheckCircle2 size={15} />
          {resolving ? 'Resolving…' : 'Mark Resolved'}
        </button>
      </div>
    </section>
  );
}
