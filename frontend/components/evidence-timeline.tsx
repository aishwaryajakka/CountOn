'use client';

import { useMemo } from 'react';
import { Camera, Clock3, Mail, Mic, Zap, Package, Activity } from 'lucide-react';
import type { Evidence, Expectation } from '@/lib/types';
import { formatDate, humanize, evidenceSourceLabel, evidenceValue } from '@/lib/presentation';
import { useIdentity } from './auth-provider';

export interface TimelineEventItem {
  id: string;
  source: string;
  sourceLabel: string;
  metric: string | null;
  observedAt: string;
  valueText: string;
  summary?: string;
  confidence: number;
  expectationClaim?: string;
  device?: string;
  speaker?: string;
}

export function sourceIcon(source: string) {
  const s = source.toLowerCase();
  if (s.includes('ring') || s.includes('camera')) return Camera;
  if (s.includes('bee') || s.includes('wearable')) return Mic;
  if (s.includes('utility') || s.includes('tariff') || s.includes('electric')) return Zap;
  if (s.includes('mail') || s.includes('gmail') || s.includes('outlook')) return Mail;
  if (s.includes('delivery')) return Package;
  return Activity;
}

export function sourceBadgeColor(source: string): { bg: string; color: string; border: string } {
  const s = source.toLowerCase();
  if (s.includes('ring')) return { bg: '#e0f2fe', color: '#0369a1', border: '#bae6fd' };
  if (s.includes('bee')) return { bg: '#fef3c7', color: '#b45309', border: '#fde68a' };
  if (s.includes('utility')) return { bg: '#dcfce7', color: '#15803d', border: '#bbf7d0' };
  if (s.includes('mail')) return { bg: '#f3e8ff', color: '#7e22ce', border: '#e9d5ff' };
  return { bg: '#f1f5f9', color: '#475569', border: '#e2e8f0' };
}

interface EvidenceTimelineProps {
  evidenceList: Evidence[];
  expectations?: Expectation[];
  title?: string;
  subtitle?: string;
  limit?: number;
}

export function EvidenceTimeline({
  evidenceList,
  expectations = [],
  title = 'Evidence Timeline',
  subtitle = 'Incoming Ring, Bee, email, and utility events with timestamps',
  limit,
}: EvidenceTimelineProps) {
  const { timeZone } = useIdentity();

  const expectationMap = useMemo(() => {
    const map = new Map<string, string>();
    expectations.forEach((exp) => map.set(exp.id, exp.claim));
    return map;
  }, [expectations]);

  const sortedEvents: TimelineEventItem[] = useMemo(() => {
    const list = [...(evidenceList ?? [])].sort(
      (a, b) => Date.parse(b.observed_at) - Date.parse(a.observed_at)
    );
    const sliced = limit ? list.slice(0, limit) : list;

    return sliced.map((item) => {
      const raw = item.raw_data || {};
      const val = item.value || {};
      const summary =
        typeof val.summary === 'string'
          ? val.summary
          : typeof raw.description === 'string'
          ? raw.description
          : undefined;

      const speaker = typeof val.speaker === 'string' ? val.speaker : undefined;
      const device = typeof val.device === 'string' ? val.device : undefined;

      return {
        id: item.id,
        source: item.source,
        sourceLabel: evidenceSourceLabel(item),
        metric: item.metric,
        observedAt: item.observed_at,
        valueText: evidenceValue(item, timeZone),
        summary,
        confidence: item.confidence,
        expectationClaim: expectationMap.get(item.expectation_id),
        device,
        speaker,
      };
    });
  }, [evidenceList, limit, expectationMap, timeZone]);

  if (!sortedEvents.length) {
    return (
      <div className="card" style={{ padding: '2rem', textAlign: 'center' }}>
        <Clock3 size={32} style={{ margin: '0 auto 0.75rem', opacity: 0.4 }} />
        <h3>No evidence recorded yet</h3>
        <p className="caption">
          Incoming events from Ring, Bee, email, and utilities will appear here in chronological order.
        </p>
      </div>
    );
  }

  return (
    <section className="card timeline-card" style={{ padding: '1.5rem' }}>
      <div className="section-heading" style={{ marginBottom: '1.25rem' }}>
        <div>
          <h2 style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', margin: 0 }}>
            <Activity size={20} />
            {title}
          </h2>
          <span className="caption">{subtitle}</span>
        </div>
        <span className="demo-badge" style={{ alignSelf: 'flex-start' }}>
          {sortedEvents.length} event{sortedEvents.length === 1 ? '' : 's'}
        </span>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
        {sortedEvents.map((event) => {
          const Icon = sourceIcon(event.source);
          const badgeColors = sourceBadgeColor(event.source);

          return (
            <div
              key={event.id}
              style={{
                display: 'flex',
                gap: '1rem',
                padding: '0.875rem 1rem',
                backgroundColor: 'var(--surface-subtle, #f8fafc)',
                border: '1px solid var(--border-color, #e2e8f0)',
                borderRadius: '12px',
                alignItems: 'flex-start',
              }}
            >
              {/* Source Icon Pill */}
              <div
                style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '10px',
                  backgroundColor: badgeColors.bg,
                  color: badgeColors.color,
                  border: `1px solid ${badgeColors.border}`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                  marginTop: '2px',
                }}
              >
                <Icon size={18} />
              </div>

              {/* Event Body */}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', flexWrap: 'wrap', gap: '0.5rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span
                      style={{
                        fontSize: '0.75rem',
                        fontWeight: 700,
                        textTransform: 'uppercase',
                        padding: '0.15rem 0.5rem',
                        borderRadius: '6px',
                        backgroundColor: badgeColors.bg,
                        color: badgeColors.color,
                      }}
                    >
                      {event.sourceLabel}
                    </span>
                    {(event.source.toLowerCase().includes('ring') || event.source.toLowerCase().includes('bee')) && (
                      <span
                        style={{
                          fontSize: '0.7rem',
                          fontWeight: 700,
                          padding: '0.1rem 0.4rem',
                          borderRadius: '4px',
                          backgroundColor: '#fef3c7',
                          color: '#92400e',
                          border: '1px solid #fde68a',
                        }}
                      >
                        SIMULATED
                      </span>
                    )}
                    {event.metric && (
                      <strong style={{ fontSize: '0.925rem' }}>
                        {humanize(event.metric)}
                      </strong>
                    )}
                  </div>

                  <time
                    dateTime={event.observedAt}
                    style={{ fontSize: '0.8rem', color: 'var(--text-muted, #64748b)', whiteSpace: 'nowrap' }}
                  >
                    {formatDate(event.observedAt, timeZone)}
                  </time>
                </div>

                <div style={{ marginTop: '0.35rem', fontSize: '0.9rem' }}>
                  <span>Observation: {event.valueText}</span>
                </div>

                {event.summary && (
                  <p
                    style={{
                      margin: '0.35rem 0 0',
                      fontSize: '0.85rem',
                      color: 'var(--text-secondary, #475569)',
                      fontStyle: 'italic',
                      backgroundColor: 'rgba(0,0,0,0.02)',
                      padding: '0.35rem 0.6rem',
                      borderRadius: '6px',
                    }}
                  >
                    “{event.summary}”
                  </p>
                )}

                {event.expectationClaim && (
                  <div style={{ marginTop: '0.4rem', fontSize: '0.775rem', color: 'var(--text-muted, #64748b)' }}>
                    Matching claim: “{event.expectationClaim}”
                  </div>
                )}
              </div>

              {/* Confidence Badge */}
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted, #64748b)', whiteSpace: 'nowrap', alignSelf: 'center' }}>
                {Math.round(event.confidence * 100)}% conf
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
