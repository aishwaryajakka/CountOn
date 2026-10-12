'use client';

import { useState, type FormEvent } from 'react';
import { Check, Edit3, Pause, Play, Trash2, X, AlertTriangle } from 'lucide-react';
import { api, ApiError } from '@/lib/api';
import type { Comparison, Expectation, ExpectationStatus, ExpectationUpdate } from '@/lib/types';
import { comparisonLabels } from '@/lib/presentation';

interface ExpectationActionsModalProps {
  expectation: Expectation;
  isOpen: boolean;
  onClose: () => void;
  onUpdated: () => void;
}

export function ExpectationActionsModal({
  expectation,
  isOpen,
  onClose,
  onUpdated,
}: ExpectationActionsModalProps) {
  const [claim, setClaim] = useState(expectation.claim);
  const [metric, setMetric] = useState(expectation.metric ?? '');
  const [comparison, setComparison] = useState<Comparison>(expectation.comparison ?? 'less_than');
  const [target, setTarget] = useState(
    expectation.target_value != null ? String(expectation.target_value) : ''
  );
  const [threshold, setThreshold] = useState(String(expectation.materiality_threshold * 100));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!isOpen) return null;

  const isPaused = expectation.status === 'cancelled';
  const isResolved = expectation.status === 'resolved';

  async function handleSave(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);

    const updatePayload: Partial<ExpectationUpdate> = {
      claim: claim.trim(),
      metric: metric.trim() || undefined,
      materiality_threshold: Math.max(0, Math.min(100, Number(threshold) || 5)) / 100,
    };

    if (expectation.type === 'numeric_comparison') {
      updatePayload.comparison = comparison;
      updatePayload.target_value = target ? Number(target) : undefined;
    }

    try {
      await api.updateExpectation(expectation.id, updatePayload);
      setBusy(false);
      onUpdated();
      onClose();
    } catch (err) {
      setBusy(false);
      setError(err instanceof Error ? err.message : 'Could not save changes.');
    }
  }

  async function handleTogglePause() {
    setBusy(true);
    setError(null);
    const newStatus: ExpectationStatus = isPaused ? 'monitoring' : 'cancelled';
    try {
      await api.updateExpectation(expectation.id, { status: newStatus });
      setBusy(false);
      onUpdated();
      onClose();
    } catch (err) {
      setBusy(false);
      setError(err instanceof Error ? err.message : 'Could not update status.');
    }
  }

  async function handleResolve() {
    setBusy(true);
    setError(null);
    try {
      await api.updateExpectation(expectation.id, { status: 'resolved' });
      setBusy(false);
      onUpdated();
      onClose();
    } catch (err) {
      setBusy(false);
      setError(err instanceof Error ? err.message : 'Could not resolve expectation.');
    }
  }

  return (
    <div className="drawer-backdrop" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000 }} onClick={onClose}>
      <div
        className="card"
        style={{
          maxWidth: '540px',
          width: '90%',
          maxHeight: '90vh',
          overflowY: 'auto',
          padding: '1.75rem',
          backgroundColor: 'var(--surface, #ffffff)',
          borderRadius: '16px',
          boxShadow: '0 20px 40px rgba(0,0,0,0.15)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
          <div>
            <span className="overline">Manage Expectation</span>
            <h2 style={{ margin: '0.25rem 0 0', fontSize: '1.25rem' }}>Edit or update lifecycle</h2>
          </div>
          <button className="icon-button" onClick={onClose} aria-label="Close modal">
            <X size={19} />
          </button>
        </div>

        {error && (
          <p role="alert" className="inline-error" style={{ marginBottom: '1rem' }}>
            {error}
          </p>
        )}

        {/* Quick Lifecycle Action Buttons */}
        <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1.5rem', flexWrap: 'wrap' }}>
          <button
            type="button"
            className={`button ${isPaused ? 'primary' : 'secondary'}`}
            onClick={handleTogglePause}
            disabled={busy || isResolved}
            style={{ flex: 1, minWidth: '130px' }}
          >
            {isPaused ? <Play size={16} /> : <Pause size={16} />}
            {isPaused ? 'Resume Monitoring' : 'Pause Expectation'}
          </button>

          {!isResolved && (
            <button
              type="button"
              className="button secondary"
              onClick={handleResolve}
              disabled={busy}
              style={{ flex: 1, minWidth: '130px' }}
            >
              <Check size={16} />
              Mark as Resolved
            </button>
          )}

          {isResolved && (
            <button
              type="button"
              className="button secondary"
              onClick={() => {
                setBusy(true);
                api.updateExpectation(expectation.id, { status: 'monitoring' })
                  .then(() => { setBusy(false); onUpdated(); onClose(); })
                  .catch((err) => { setBusy(false); setError(err instanceof Error ? err.message : 'Error'); });
              }}
              disabled={busy}
              style={{ flex: 1, minWidth: '130px' }}
            >
              <Play size={16} />
              Re-open Expectation
            </button>
          )}
        </div>

        <form onSubmit={handleSave}>
          <div style={{ marginBottom: '1rem' }}>
            <label htmlFor="edit-claim" style={{ display: 'block', fontWeight: 600, marginBottom: '0.4rem' }}>
              Claim description
            </label>
            <textarea
              id="edit-claim"
              value={claim}
              onChange={(e) => setClaim(e.target.value)}
              rows={3}
              required
              style={{ width: '100%', borderRadius: '8px', padding: '0.6rem' }}
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '1rem' }}>
            <div>
              <label htmlFor="edit-metric" style={{ display: 'block', fontWeight: 600, marginBottom: '0.4rem' }}>
                Metric
              </label>
              <input
                id="edit-metric"
                value={metric}
                onChange={(e) => setMetric(e.target.value)}
                placeholder="e.g. package_detected"
                style={{ width: '100%', borderRadius: '8px', padding: '0.6rem' }}
              />
            </div>

            <div>
              <label htmlFor="edit-tolerance" style={{ display: 'block', fontWeight: 600, marginBottom: '0.4rem' }}>
                Tolerance (%)
              </label>
              <input
                id="edit-tolerance"
                type="number"
                min="0"
                max="100"
                step="any"
                value={threshold}
                onChange={(e) => setThreshold(e.target.value)}
                style={{ width: '100%', borderRadius: '8px', padding: '0.6rem' }}
              />
            </div>
          </div>

          {expectation.type === 'numeric_comparison' && (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', marginBottom: '1rem' }}>
              <div>
                <label htmlFor="edit-comparison" style={{ display: 'block', fontWeight: 600, marginBottom: '0.4rem' }}>
                  Comparison
                </label>
                <select
                  id="edit-comparison"
                  value={comparison}
                  onChange={(e) => setComparison(e.target.value as Comparison)}
                  style={{ width: '100%', borderRadius: '8px', padding: '0.6rem' }}
                >
                  {Object.entries(comparisonLabels).map(([val, lbl]) => (
                    <option key={val} value={val}>{lbl}</option>
                  ))}
                </select>
              </div>

              <div>
                <label htmlFor="edit-target" style={{ display: 'block', fontWeight: 600, marginBottom: '0.4rem' }}>
                  Target value
                </label>
                <input
                  id="edit-target"
                  type="number"
                  step="any"
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                  style={{ width: '100%', borderRadius: '8px', padding: '0.6rem' }}
                />
              </div>
            </div>
          )}

          <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1.5rem' }}>
            <button type="button" className="button ghost" onClick={onClose} disabled={busy}>
              Cancel
            </button>
            <button type="submit" className="button primary" disabled={busy}>
              {busy ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
