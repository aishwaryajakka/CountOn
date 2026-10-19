'use client';

import { Sparkles, ArrowRight } from 'lucide-react';
import type { Evaluation, Expectation } from '@/lib/types';
import Link from 'next/link';

interface AiSuggestionsProps {
  expectation: Expectation;
  evaluation?: Evaluation | null;
  className?: string;
}

export function AiSuggestions({ expectation, className = '' }: AiSuggestionsProps) {
  const metric = (expectation.metric ?? '').toLowerCase();

  let suggestions: string[] = [];
  if (metric.includes('cost') || metric.includes('bill') || metric.includes('tariff')) {
    suggestions = [
      'Review high-consumption appliance usage during peak tariff hours',
      'Check recent rate adjustments or utility provider notices',
      'Consider increasing your target threshold if rate changes are permanent',
      'Keep monitoring through next cycle to establish a new seasonal baseline',
    ];
  } else if (metric.includes('package') || metric.includes('deliver')) {
    suggestions = [
      'Check official tracking portal for revised carrier transit windows',
      'Inspect porch camera motion detection logs and lighting conditions',
      'Extend the expectation deadline if carrier reported an unexpected delay',
    ];
  } else if (metric.includes('appointment') || metric.includes('confirm') || metric.includes('plumber')) {
    suggestions = [
      'Follow up with contractor or landlord to secure an alternate slot',
      'Update the expectation criteria once a new appointment is confirmed',
      'Review recorded conversation transcript in the evidence timeline',
    ];
  } else {
    suggestions = [
      'Review recent incoming signals in the evidence stream',
      'Adjust expectation tolerance or deadline to accommodate slight variations',
      'Keep monitoring until secondary supporting observations arrive',
    ];
  }

  return (
    <div
      className={`card ai-suggestions-card ${className}`}
      style={{
        padding: '1.25rem 1.5rem',
        backgroundColor: '#fafbfc',
        border: '1px solid #e2e8f0',
        borderRadius: '14px',
        marginTop: '1rem',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '0.5rem',
          marginBottom: '0.75rem',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <Sparkles size={16} color="var(--color-brand-primary, #1a5fd7)" />
          <strong style={{ fontSize: '0.95rem', color: 'var(--color-text-primary, #2d3142)' }}>
            What you can do
          </strong>
        </div>
        <span
          style={{
            fontSize: '0.7rem',
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.05em',
            padding: '0.15rem 0.5rem',
            borderRadius: '6px',
            backgroundColor: '#edf3ff',
            color: '#1a5fd7',
          }}
        >
          AI suggestions
        </span>
      </div>

      <p className="caption" style={{ marginBottom: '0.75rem' }}>
        Based on evaluated evidence and typical patterns. These are advisory recommendations, not deterministic decisions.
      </p>

      <ul style={{ listStyle: 'none', padding: 0, margin: '0 0 1rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {suggestions.map((suggestion, idx) => (
          <li
            key={idx}
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: '0.5rem',
              fontSize: '0.85rem',
              color: 'var(--color-text-primary, #2d3142)',
            }}
          >
            <span
              style={{
                width: '18px',
                height: '18px',
                borderRadius: '50%',
                backgroundColor: '#e2e8f0',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
                marginTop: '2px',
                fontSize: '0.7rem',
                fontWeight: 600,
                color: '#475569',
              }}
            >
              {idx + 1}
            </span>
            <span>{suggestion}</span>
          </li>
        ))}
      </ul>

      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
        <Link
          href={`/alexa?starter=${encodeURIComponent(`What should I do about ${expectation.claim}?`)}`}
          className="text-link"
          style={{ fontSize: '0.85rem' }}
        >
          Discuss options in Alexa+ chat <ArrowRight size={14} />
        </Link>
        <span className="caption" style={{ fontStyle: 'italic', fontSize: '0.75rem' }}>
          Powered by Amazon Bedrock intelligence
        </span>
      </div>
    </div>
  );
}
