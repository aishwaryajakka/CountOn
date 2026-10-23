import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { RealityDecisionCard } from '@/components/reality-decision-card';
import type { Evaluation, Expectation } from '@/lib/types';
import { expectation, evaluation } from './fixtures';

describe('RealityDecisionCard', () => {
  const numericExp: Expectation = {
    ...expectation,
    id: 'exp-num-1',
    claim: 'Electric bill should stay under $120/mo',
    type: 'numeric_comparison',
    metric: 'amount',
    comparison: 'less_than_or_equal',
    baseline: 120,
    target_value: 120,
    status: 'monitoring',
    evidence_sources: ['utility_portal'],
  };

  const mismatchEval: Evaluation = {
    ...evaluation,
    id: 'eval-mismatch-1',
    expectation_id: 'exp-num-1',
    result: 'MISMATCH',
    expected: { target: 120, comparison: 'less_than_or_equal', metric: 'amount' },
    observed: { value: 142.5, evidence_id: 'ev-1' },
  };

  const matchEval: Evaluation = {
    ...mismatchEval,
    id: 'eval-match-1',
    result: 'MATCH',
    observed: { value: 108.0, evidence_id: 'ev-2' },
  };

  it('renders the complete pipeline for a numeric mismatch', () => {
    render(<RealityDecisionCard expectation={numericExp} evaluation={mismatchEval} />);

    // 1. Pipeline headers
    expect(screen.getByText('CountOn Reality Engine')).toBeInTheDocument();
    expect(screen.getByText(/1\. Expected/i)).toBeInTheDocument();
    expect(screen.getByText(/2\. Observed/i)).toBeInTheDocument();
    expect(screen.getByText(/3\. Deterministic Result/i)).toBeInTheDocument();

    // 2. Evaluator engine identity
    expect(screen.getByText('NumericEvaluator')).toBeInTheDocument();

    // 3. Observed & Target values
    expect(screen.getAllByText(/142\.5/).length).toBeGreaterThan(0);

    // 4. Variance calculation
    expect(screen.getByText(/Variance:/i)).toBeInTheDocument();
    expect(screen.getByText(/\+22\.5/i)).toBeInTheDocument();

    const whyLink = screen.getByRole('link', { name: /Ask CountOn Why/i });
    expect(whyLink).toHaveAttribute('href', expect.stringContaining('/alexa?'));
    expect(whyLink).toHaveAttribute('href', expect.stringContaining('starter='));

    // 6. Security & separation guarantee
    expect(screen.getByText(/Deterministic engine decides · AI never votes on outcome/i)).toBeInTheDocument();
  });

  it('renders MATCH state clearly without panic or misleading AI evaluation claims', () => {
    render(<RealityDecisionCard expectation={numericExp} evaluation={matchEval} />);

    expect(screen.getByText('Quiet Match')).toBeInTheDocument();
    expect(screen.getByText('NumericEvaluator')).toBeInTheDocument();
    expect(screen.getByText('MATCH')).toBeInTheDocument();
  });

  it('renders UNKNOWN waiting state when evaluation is pending or absent', () => {
    render(<RealityDecisionCard expectation={numericExp} evaluation={null} />);

    expect(screen.getByText('Waiting for Evidence')).toBeInTheDocument();
    expect(screen.getByText('UNKNOWN')).toBeInTheDocument();
  });

  it('clearly marks simulated hardware sources as SIMULATED (NO LIVE HARDWARE)', () => {
    const ringExp: Expectation = {
      ...expectation,
      id: 'exp-ring-1',
      claim: 'Package delivered to porch',
      status: 'monitoring',
      evidence_sources: ['ring_simulator'],
    };

    render(<RealityDecisionCard expectation={ringExp} evaluation={null} />);

    expect(screen.getByText(/SIMULATED \(NO LIVE HARDWARE\)/i)).toBeInTheDocument();
  });
});

it('does not turn persisted UNKNOWN into a contradicted formula', () => {
  render(<RealityDecisionCard expectation={expectation} evaluation={{ ...evaluation, result: 'UNKNOWN', observed: {}, reasoning: { reason: 'no_relevant_evidence' } }} />);
  expect(screen.getByText('UNKNOWN')).toBeInTheDocument();
  expect(screen.queryByText(/FALSE|CONTRADICTED/)).not.toBeInTheDocument();
});

it('uses recorded Bee CLI provenance rather than marking all Bee records simulated', () => {
  render(<RealityDecisionCard expectation={{ ...expectation, evidence_sources: ['bee'] }} evaluation={null} evidence={[{
    id: 'live-bee-record', expectation_id: expectation.id, external_event_id: 'bee:approved-record:1', source: 'bee', metric: 'bee_context', value: { context_only: true }, unit: null, observed_at: expectation.created_at, confidence: 0.7, raw_data: { provenance: 'LIVE_BEE_CLI' }, created_at: expectation.created_at,
  }]} />);
  expect(screen.getByText(/LIVE_BEE_CLI/)).toBeInTheDocument();
  expect(screen.queryByText(/SIMULATED_BEE/)).not.toBeInTheDocument();
});

it('keeps historical evaluation criteria after the expectation is edited', () => {
  render(<RealityDecisionCard expectation={{ ...expectation, target_value: 200, comparison: 'greater_than' }} evaluation={evaluation} />);
  expect(screen.getByText('Less than 142.1')).toBeInTheDocument();
  expect(screen.getByText(/\+19\.9/)).toBeInTheDocument();
  expect(screen.queryByText(/More than 200/)).not.toBeInTheDocument();
});

it('does not invent a saved target when a historical evaluation has none', () => {
  render(<RealityDecisionCard expectation={expectation} evaluation={{ ...evaluation, expected: {} }} />);
  expect(screen.getByText('Criteria not recorded for this evaluation')).toBeInTheDocument();
  expect(screen.queryByText(/Variance:/)).not.toBeInTheDocument();
});
