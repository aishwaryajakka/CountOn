'use client';

import { useState, type FormEvent } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Clock3,
  ShieldCheck,
  Sparkles,
  Zap,
} from 'lucide-react';
import { api, ApiError } from '@/lib/api';
import type { Comparison, ExpectationCreate, ExpectationType } from '@/lib/types';
import { comparisonLabels, humanize, number } from '@/lib/presentation';
import { manualExpectation } from '@/lib/manual-expectation';
import { useBoard } from '@/components/app-shell';
import { IconBox, QuietNote } from '@/components/ui';

interface Preset {
  title: string;
  claim: string;
  type: ExpectationType;
  metric: string;
  comparison: Comparison;
  target: string;
  baseline: string;
  sources: string;
  threshold: string;
  deadlineOffsetDays?: number;
}

const presets: Preset[] = [
  {
    title: 'Electricity Bill',
    claim: 'My next electric bill should be lower than last month.',
    type: 'numeric_comparison',
    metric: 'total_cost',
    comparison: 'less_than',
    target: '142.10',
    baseline: '150.00',
    sources: 'utility_bill, utility_usage',
    threshold: '5',
  },
  {
    title: 'Package Delivery',
    claim: 'Expecting package delivery at the front door today.',
    type: 'boolean',
    metric: 'package_detected',
    comparison: 'equal',
    target: '1',
    baseline: '',
    sources: 'ring_doorbell, delivery_notice',
    threshold: '0',
    deadlineOffsetDays: 1,
  },
  {
    title: 'Service Appointment',
    claim: 'Plumber appointment should be confirmed for Friday.',
    type: 'boolean',
    metric: 'appointment_confirmed',
    comparison: 'equal',
    target: '1',
    baseline: '',
    sources: 'bee_conversation, email_confirmation',
    threshold: '0',
  },
];

export default function CreateExpectation() {
  const router = useRouter();
  const board = useBoard();

  const [claim, setClaim] = useState('');
  const [type, setType] = useState<ExpectationType>('numeric_comparison');
  const [metric, setMetric] = useState('');
  const [comparison, setComparison] = useState<Comparison>('less_than');
  const [target, setTarget] = useState('');
  const [baseline, setBaseline] = useState('');
  const [deadline, setDeadline] = useState('');
  const [sources, setSources] = useState('');
  const [threshold, setThreshold] = useState('5');

  const [stage, setStage] = useState<'claim' | 'manual' | 'preview'>('claim');
  const [preview, setPreview] = useState<ExpectationCreate | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [requestId, setRequestId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  function applyPreset(p: Preset) {
    setClaim(p.claim);
    setType(p.type);
    setMetric(p.metric);
    setComparison(p.comparison);
    setTarget(p.target);
    setBaseline(p.baseline);
    setSources(p.sources);
    setThreshold(p.threshold);
    if (p.deadlineOffsetDays) {
      const d = new Date();
      d.setDate(d.getDate() + p.deadlineOffsetDays);
      setDeadline(d.toISOString().slice(0, 16));
    } else {
      setDeadline('');
    }
    setStage('manual');
    setError(null);
  }

  function interpret(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      const validated = manualExpectation({
        claim,
        type,
        metric,
        comparison,
        target,
        sources,
        threshold,
        baseline: baseline || undefined,
        deadline: deadline || undefined,
      });
      setPreview(validated);
      setStage('preview');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Check the fields and try again.');
    }
  }

  async function create() {
    if (!preview || busy) return;
    setBusy(true);
    setError(null);
    setRequestId(null);
    try {
      const row = await api.createExpectation(preview);
      board.reload();
      router.push(`/expectations/${row.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Your expectation didn’t save. Please try again.');
      setRequestId(err instanceof ApiError ? err.requestId ?? null : null);
      setBusy(false);
    }
  }

  // Live preview text computation
  const liveExpectedCondition =
    type === 'numeric_comparison'
      ? `${comparisonLabels[comparison] ?? 'Target'} ${target ? `$${target}` : '$0.00'}`
      : type === 'boolean'
      ? 'Confirmation event (TRUE)'
      : 'Temporal arrival verified against deadline';

  return (
    <>
      <Link href="/expectations" className="back-link">
        <ArrowLeft size={17} />
        Back to Expectations
      </Link>

      <div className="create-wrap">
        <header className="create-header">
          <span className="eyebrow">ONE LESS THING ON YOUR MIND</span>
          <h1>
            {stage === 'preview'
              ? 'Here’s what I’ll watch'
              : 'What are you counting on?'}
          </h1>
          <p>
            {stage === 'preview'
              ? 'Take a moment to check the details. You’re in control.'
              : 'Tell us what you expect. Start with something you want to monitor.'}
          </p>
        </header>

        {/* Step indicator */}
        <div className="step-strip" aria-label="Setup progress">
          <span className={stage === 'claim' ? 'current' : ''}>01 · Your expectation</span>
          <span className={stage === 'manual' ? 'current' : ''}>02 · Set the criteria</span>
          <span className={stage === 'preview' ? 'current' : ''}>03 · Confirm</span>
        </div>

        {/* Quick Presets Section */}
        {stage !== 'preview' && (
          <div
            style={{
              marginBottom: '1.5rem',
              padding: '1rem 1.25rem',
              backgroundColor: 'var(--color-bg-surface, #ffffff)',
              borderRadius: '12px',
              border: '1px solid var(--color-border, #e6ebf2)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.6rem' }}>
              <Sparkles size={16} color="var(--color-brand-primary, #1a5fd7)" />
              <strong style={{ fontSize: '0.875rem' }}>Quick presets to get started:</strong>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              {presets.map((preset) => (
                <button
                  key={preset.title}
                  type="button"
                  className="button secondary"
                  onClick={() => applyPreset(preset)}
                  style={{ fontSize: '0.8rem', padding: '0.35rem 0.75rem' }}
                >
                  {preset.title}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* STAGE 1: Claim In Free Text */}
        {stage === 'claim' && (
          <form
            className="card create-card"
            onSubmit={(event) => {
              event.preventDefault();
              if (claim.trim()) {
                setStage('manual');
                setError(null);
              }
            }}
          >
            <label htmlFor="claim">In your own words</label>
            <textarea
              id="claim"
              autoFocus
              value={claim}
              onChange={(event) => setClaim(event.target.value)}
              placeholder="e.g. My next electric bill should stay under $142.10, or Package delivered by 8 PM."
              required
              rows={4}
              maxLength={5000}
            />

            <div className="create-hint">
              <ShieldCheck size={18} />
              <span>We’ll help you define exact deterministic criteria for matching.</span>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: '1rem' }}>
              <Link href="/alexa" className="text-link" style={{ fontSize: '0.85rem' }}>
                Or use conversational Alexa+ setup →
              </Link>
              <button className="button primary" type="submit" disabled={!claim.trim()}>
                Set Criteria <ArrowRight size={17} />
              </button>
            </div>
          </form>
        )}

        {/* STAGE 2: Structured Criteria Builder */}
        {stage === 'manual' && (
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.4fr) minmax(280px, 1fr)', gap: '1.5rem', alignItems: 'flex-start' }}>
            <form className="card create-card" onSubmit={interpret}>
              <div className="manual-notice">
                <strong>Visual Expectation Builder</strong>
                <Link href="/alexa">Conversational Mode</Link>
                <p>Define structured criteria below. Real observations will be evaluated deterministically.</p>
              </div>

              <label htmlFor="edit-claim">Expectation description</label>
              <textarea
                id="edit-claim"
                value={claim}
                onChange={(event) => setClaim(event.target.value)}
                required
                rows={2}
                placeholder="What are you counting on?"
              />

              <div className="form-grid">
                <div>
                  <label htmlFor="type">Evaluation type</label>
                  <select
                    id="type"
                    value={type}
                    onChange={(event) => setType(event.target.value as ExpectationType)}
                  >
                    <option value="numeric_comparison">Numeric comparison (NumericEvaluator)</option>
                    <option value="boolean">Boolean confirmation (BooleanEvaluator)</option>
                    <option value="temporal">Temporal deadline (TemporalEvaluator)</option>
                    <option value="event">Event check (TemporalEvaluator)</option>
                  </select>
                </div>

                <div>
                  <label htmlFor="metric">Metric to watch</label>
                  <input
                    id="metric"
                    value={metric}
                    onChange={(event) => setMetric(event.target.value)}
                    placeholder="e.g. total_cost, package_detected"
                    maxLength={100}
                    required
                  />
                  {/* Quick Metric suggestion chips */}
                  <div style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap', marginTop: '0.3rem' }}>
                    {['total_cost', 'package_detected', 'appointment_confirmed', 'reply_received'].map((m) => (
                      <button
                        key={m}
                        type="button"
                        onClick={() => setMetric(m)}
                        style={{
                          fontSize: '0.7rem',
                          background: '#f1f5f9',
                          border: '1px solid #cbd5e1',
                          borderRadius: '4px',
                          padding: '0.1rem 0.4rem',
                          cursor: 'pointer',
                        }}
                      >
                        {m}
                      </button>
                    ))}
                  </div>
                </div>

                {type === 'numeric_comparison' && (
                  <>
                    <div>
                      <label htmlFor="comparison">Comparison operator</label>
                      <select
                        id="comparison"
                        value={comparison}
                        onChange={(event) => setComparison(event.target.value as Comparison)}
                      >
                        {Object.entries(comparisonLabels).map(([val, lbl]) => (
                          <option value={val} key={val}>
                            {lbl}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label htmlFor="target">Target threshold</label>
                      <input
                        id="target"
                        type="number"
                        step="any"
                        value={target}
                        onChange={(event) => setTarget(event.target.value)}
                        placeholder="e.g. 142.10"
                        required
                      />
                    </div>

                    <div>
                      <label htmlFor="baseline">Baseline reference (optional)</label>
                      <input
                        id="baseline"
                        type="number"
                        step="any"
                        value={baseline}
                        onChange={(event) => setBaseline(event.target.value)}
                        placeholder="e.g. 150.00"
                      />
                    </div>
                  </>
                )}

                <div>
                  <label htmlFor="deadline">Deadline (optional)</label>
                  <input
                    id="deadline"
                    type="datetime-local"
                    value={deadline}
                    onChange={(event) => setDeadline(event.target.value)}
                  />
                </div>

                <div className="span-two">
                  <label htmlFor="sources">Evidence sources</label>
                  <input
                    id="sources"
                    value={sources}
                    onChange={(event) => setSources(event.target.value)}
                    placeholder="e.g. utility_bill, ring_doorbell, bee_wearable"
                  />
                  <div style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap', marginTop: '0.3rem' }}>
                    {['utility_bill', 'ring_doorbell', 'bee_wearable', 'gmail', 'outlook'].map((s) => (
                      <button
                        key={s}
                        type="button"
                        onClick={() => setSources(sources ? `${sources}, ${s}` : s)}
                        style={{
                          fontSize: '0.7rem',
                          background: '#edf3ff',
                          color: '#1a5fd7',
                          border: '1px solid #dce7fa',
                          borderRadius: '4px',
                          padding: '0.1rem 0.4rem',
                          cursor: 'pointer',
                        }}
                      >
                        +{s}
                      </button>
                    ))}
                  </div>
                </div>

                <div>
                  <label htmlFor="tolerance">Tolerance (%)</label>
                  <input
                    id="tolerance"
                    type="number"
                    min="0"
                    max="100"
                    step="any"
                    value={threshold}
                    onChange={(event) => setThreshold(event.target.value)}
                    required
                  />
                </div>
              </div>

              {error && (
                <p className="inline-error" role="alert">
                  {error}
                </p>
              )}

              <div className="actions" style={{ marginTop: '1.25rem' }}>
                <button className="button primary" type="submit">
                  Preview & Confirm <ArrowRight size={17} />
                </button>
                <button className="button ghost" type="button" onClick={() => setStage('claim')}>
                  Back
                </button>
                <Link href="/expectations" className="button ghost" style={{ marginLeft: 'auto' }}>
                  Cancel
                </Link>
              </div>
            </form>

            {/* LIVE PREVIEW BOX */}
            <aside
              className="card"
              style={{
                padding: '1.5rem',
                backgroundColor: '#f8fafc',
                border: '1.5px solid var(--color-brand-primary, #1a5fd7)',
                borderRadius: '16px',
                position: 'sticky',
                top: '2rem',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.75rem' }}>
                <Zap size={18} color="var(--color-brand-primary, #1a5fd7)" />
                <strong style={{ fontSize: '0.95rem' }}>CountOn will monitor:</strong>
              </div>

              <div
                style={{
                  padding: '1rem',
                  backgroundColor: '#ffffff',
                  borderRadius: '10px',
                  border: '1px solid #e2e8f0',
                  marginBottom: '1rem',
                }}
              >
                <span className="overline" style={{ fontSize: '0.675rem' }}>
                  {metric || 'metric_name'}
                </span>
                <strong style={{ display: 'block', fontSize: '1.15rem', color: 'var(--color-brand-primary, #1a5fd7)', margin: '0.2rem 0' }}>
                  {liveExpectedCondition}
                </strong>
                {deadline && (
                  <span className="caption" style={{ display: 'flex', alignItems: 'center', gap: '0.3rem', marginTop: '0.3rem' }}>
                    <Clock3 size={13} />
                    by {new Date(deadline).toLocaleDateString()} {new Date(deadline).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </span>
                )}
                {threshold !== '0' && (
                  <span className="caption" style={{ display: 'block', marginTop: '0.2rem' }}>
                    ± {threshold}% materiality tolerance
                  </span>
                )}
              </div>

              <dl style={{ fontSize: '0.825rem', margin: '0 0 1rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.25rem 0' }}>
                  <dt style={{ color: 'var(--color-text-secondary, #667085)' }}>Check</dt>
                  <dd style={{ fontWeight: 600 }}>{humanize(type)}</dd>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', padding: '0.25rem 0' }}>
                  <dt style={{ color: 'var(--color-text-secondary, #667085)' }}>Sources</dt>
                  <dd style={{ fontWeight: 600 }}>{sources ? sources.split(',').length : 0} configured</dd>
                </div>
              </dl>

              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.4rem',
                  color: '#15803d',
                  fontSize: '0.8rem',
                  fontWeight: 600,
                  backgroundColor: '#dcfce7',
                  padding: '0.4rem 0.6rem',
                  borderRadius: '6px',
                }}
              >
                <CheckCircle2 size={15} />
                <span>Ready to monitor</span>
              </div>
            </aside>
          </div>
        )}

        {/* STAGE 3: Final Confirmation & Submit */}
        {stage === 'preview' && preview && (
          <section className="card create-card preview-card">
            <IconBox icon={CheckCircle2} />
            <span className="demo-badge">Manually defined · deterministic criteria</span>
            <h2>“{preview.claim}”</h2>

            <dl>
              <div>
                <dt>What I’ll watch</dt>
                <dd>{humanize(preview.metric ?? 'Expectation')}</dd>
              </div>
              <div>
                <dt>Expected behavior</dt>
                <dd>
                  {preview.type === 'numeric_comparison' && preview.comparison
                    ? `${comparisonLabels[preview.comparison]} ${number(preview.target_value ?? 0)}`
                    : preview.type === 'boolean'
                    ? 'Confirmation (TRUE)'
                    : 'A recorded event checked against its deadline'}
                </dd>
              </div>
              <div>
                <dt>Deadline</dt>
                <dd>{preview.deadline ? new Date(preview.deadline).toLocaleString() : 'No explicit deadline'}</dd>
              </div>
              <div>
                <dt>Evidence sources</dt>
                <dd>{preview.evidence_sources.map(humanize).join(', ') || 'Not specified'}</dd>
              </div>
              <div>
                <dt>Tolerance</dt>
                <dd>{number(preview.materiality_threshold * 100, 'percent')}</dd>
              </div>
            </dl>

            {error && (
              <p className="inline-error" role="alert">
                {error}
                {requestId && <span className="caption">Request reference: {requestId}</span>}
              </p>
            )}

            <div className="actions" style={{ marginTop: '1.5rem' }}>
              <button className="button primary" onClick={create} disabled={busy}>
                {busy ? 'Saving your expectation…' : 'Start monitoring'}
                <ArrowRight size={17} />
              </button>
              <button
                className="button ghost"
                onClick={() => {
                  setStage('manual');
                  setError(null);
                }}
                disabled={busy}
              >
                Edit
              </button>
              <Link href="/expectations" className="button ghost" style={{ marginLeft: 'auto' }}>
                Cancel
              </Link>
            </div>
            <p className="caption">
              After saving, you can connect an authorized source and review the tracking schedule.
            </p>
          </section>
        )}

        <QuietNote>A little clarity starts with knowing what you expect.</QuietNote>
      </div>
    </>
  );
}
