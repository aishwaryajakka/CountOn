'use client';

import { useState } from 'react';
import Link from 'next/link';
import { Sparkles, Check, X, Edit2, CalendarDays, Mail, Zap, Package } from 'lucide-react';
import { api } from '@/lib/api';
import type { ExpectationCreate } from '@/lib/types';
import { IconBox } from './ui';

export interface RecommendedExpectation {
  id: string;
  source: 'google' | 'microsoft' | 'utility' | 'delivery';
  sourceLabel: string;
  claim: string;
  type: 'boolean' | 'numeric_comparison';
  metric: string;
  comparison?: 'less_than' | 'equal';
  baseline?: number;
  materiality_threshold: number;
  evidence_sources: string[];
  rationale: string;
}

const defaultRecommendations: RecommendedExpectation[] = [
  {
    id: 'rec_amazon_delivery',
    source: 'delivery',
    sourceLabel: 'Email Receipt (Amazon)',
    claim: 'Package delivery from Amazon order #112-8821 expected by 8:00 PM Friday',
    type: 'boolean',
    metric: 'delivered',
    comparison: 'equal',
    materiality_threshold: 0,
    evidence_sources: ['ring', 'gmail'],
    rationale: 'Detected from your shipping confirmation email. CountOn can watch for Ring delivery confirmation.',
  },
  {
    id: 'rec_dentist_appt',
    source: 'google',
    sourceLabel: 'Google Calendar',
    claim: 'Dentist appointment with Dr. Aris confirmed for Friday at 2:00 PM',
    type: 'boolean',
    metric: 'appointment_confirmed',
    comparison: 'equal',
    materiality_threshold: 0,
    evidence_sources: ['google_calendar'],
    rationale: 'Found on your connected calendar. Monitor for schedule changes or cancellations.',
  },
  {
    id: 'rec_water_bill',
    source: 'utility',
    sourceLabel: 'Utility Provider',
    claim: 'Next municipal water bill should remain under $68.00',
    type: 'numeric_comparison',
    metric: 'total_cost',
    comparison: 'less_than',
    baseline: 68.0,
    materiality_threshold: 0.05,
    evidence_sources: ['utility_statement'],
    rationale: 'Based on 6-month seasonal utility baseline. Alerts you only if a billing spike occurs.',
  },
];

export function AiRecommendations({ onAccepted }: { onAccepted?: () => void }) {
  const [recommendations, setRecommendations] = useState<RecommendedExpectation[]>(defaultRecommendations);
  const [acceptedIds, setAcceptedIds] = useState<Set<string>>(new Set());
  const [busyId, setBusyId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  if (!recommendations.length) return null;

  async function handleAccept(rec: RecommendedExpectation) {
    setBusyId(rec.id);
    setErrorMessage(null);

    try {
      const payload: ExpectationCreate = {
        claim: rec.claim,
        type: rec.type,
        metric: rec.metric,
        comparison: rec.comparison,
        baseline: rec.baseline,
        materiality_threshold: rec.materiality_threshold,
        evidence_sources: rec.evidence_sources,
      };

      await api.createExpectation(payload);
      setAcceptedIds((prev) => new Set([...prev, rec.id]));
      onAccepted?.();
      setTimeout(() => {
        setRecommendations((prev) => prev.filter((r) => r.id !== rec.id));
      }, 1500);
    } catch (err) {
      setErrorMessage(err instanceof Error ? err.message : 'Failed to save expectation');
    } finally {
      setBusyId(null);
    }
  }

  function handleDismiss(id: string) {
    setRecommendations((prev) => prev.filter((r) => r.id !== id));
  }

  const icons = {
    google: CalendarDays,
    microsoft: Mail,
    utility: Zap,
    delivery: Package,
  };

  return (
    <section className="card" style={{ padding: '1.5rem', marginBottom: '1.5rem', backgroundColor: '#fcfdff', border: '1px solid #dbeafe' }}>
      <div className="section-heading" style={{ marginBottom: '1rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <Sparkles size={20} color="#2563eb" />
          <div>
            <h2 style={{ margin: 0, fontSize: '1.1rem' }}>Suggested Expectations</h2>
            <span className="caption">Discovered from your connected email, calendar, and utility context</span>
          </div>
        </div>
        <span className="demo-badge" style={{ backgroundColor: '#eff6ff', color: '#1d4ed8', border: '1px solid #bfdbfe' }}>
          AI Recommendation Review
        </span>
      </div>

      {errorMessage && (
        <div style={{ padding: '0.6rem 0.85rem', marginBottom: '0.75rem', backgroundColor: '#fef2f2', border: '1px solid #fecaca', borderRadius: '6px', color: '#991b1b', fontSize: '0.85rem' }}>
          {errorMessage}
        </div>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        {recommendations.map((rec) => {
          const Icon = icons[rec.source] ?? Sparkles;
          const isAccepted = acceptedIds.has(rec.id);
          const isBusy = busyId === rec.id;

          return (
            <div
              key={rec.id}
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: '1rem',
                padding: '1rem',
                borderRadius: '10px',
                backgroundColor: isAccepted ? '#f0fdf4' : '#ffffff',
                border: `1px solid ${isAccepted ? '#bbf7d0' : '#e2e8f0'}`,
                transition: 'all 0.2s ease',
              }}
            >
              <div style={{ display: 'flex', gap: '0.85rem', alignItems: 'flex-start', flex: 1, minWidth: '280px' }}>
                <IconBox icon={Icon} tone={rec.source === 'utility' ? 'orange' : 'blue'} />
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', marginBottom: '0.2rem' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 600, color: '#64748b', textTransform: 'uppercase' }}>
                      {rec.sourceLabel}
                    </span>
                  </div>
                  <strong style={{ fontSize: '0.95rem', display: 'block', color: '#0f172a' }}>
                    “{rec.claim}”
                  </strong>
                  <p style={{ margin: '0.25rem 0 0', fontSize: '0.825rem', color: '#475569' }}>
                    {rec.rationale}
                  </p>
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                {isAccepted ? (
                  <span style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', color: '#16a34a', fontWeight: 600, fontSize: '0.875rem' }}>
                    <Check size={16} /> Saved & Monitored
                  </span>
                ) : (
                  <>
                    <button
                      className="button primary"
                      onClick={() => handleAccept(rec)}
                      disabled={isBusy}
                      style={{ fontSize: '0.825rem', padding: '0.4rem 0.8rem' }}
                    >
                      <Check size={14} />
                      {isBusy ? 'Saving...' : 'Accept'}
                    </button>
                    <Link
                      href={`/expectations/new?claim=${encodeURIComponent(rec.claim)}`}
                      className="button secondary"
                      style={{ fontSize: '0.825rem', padding: '0.4rem 0.8rem', display: 'flex', alignItems: 'center', gap: '0.3rem' }}
                    >
                      <Edit2 size={13} />
                      Edit
                    </Link>
                    <button
                      className="button ghost"
                      onClick={() => handleDismiss(rec.id)}
                      disabled={isBusy}
                      title="Dismiss suggestion"
                      style={{ fontSize: '0.825rem', padding: '0.4rem 0.6rem' }}
                    >
                      <X size={15} />
                    </button>
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
