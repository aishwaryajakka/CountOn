import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { ResolutionPanel } from '@/components/resolution-panel';
import type { Evaluation, Expectation } from '@/lib/types';
import { expectation, evaluation } from './fixtures';

describe('ResolutionPanel', () => {
  const numericExp: Expectation = {
    ...expectation,
    id: 'exp-num-2',
    claim: 'Monthly electric charge should be <= $100',
    type: 'numeric_comparison',
    metric: 'amount',
    comparison: 'less_than_or_equal',
    baseline: 100,
    target_value: 100,
    status: 'monitoring',
    evidence_sources: ['utility_statement'],
  };

  const mismatchEval: Evaluation = {
    ...evaluation,
    id: 'eval-mismatch-2',
    expectation_id: 'exp-num-2',
    result: 'MISMATCH',
    expected: { target: 100, comparison: 'less_than_or_equal', metric: 'amount' },
    observed: { value: 128.5, evidence_id: 'bill-evidence' },
  };

  const matchEval: Evaluation = {
    ...mismatchEval,
    id: 'eval-match-2',
    result: 'MATCH',
    observed: { value: 94.0, evidence_id: 'bill-evidence' },
  };

  it('renders mismatch resolution panel with variance and actions', () => {
    const onManage = vi.fn();
    render(<ResolutionPanel expectation={numericExp} evaluation={mismatchEval} onManage={onManage} />);

    expect(screen.getByText(/CountOn detected a mismatch/i)).toBeInTheDocument();
    expect(screen.getByText(/\+28\.5/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Ask CountOn Why/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Mark Resolved/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Update Criteria/i })).toBeInTheDocument();
  });

  it('renders calm UNKNOWN state when evidence has not arrived', () => {
    render(<ResolutionPanel expectation={numericExp} evaluation={null} />);

    expect(screen.getByText(/WAITING FOR EVIDENCE/i)).toBeInTheDocument();
    expect(screen.getByText(/Missing evidence is not failure/i)).toBeInTheDocument();
    expect(screen.getByText(/Expected Condition/i)).toBeInTheDocument();
  });

  it('renders MATCH state affirming that silence is success', () => {
    render(<ResolutionPanel expectation={numericExp} evaluation={matchEval} />);

    expect(screen.getByText(/Confirmed by Evidence/i)).toBeInTheDocument();
    expect(screen.getByText(/Silence is success/i)).toBeInTheDocument();
  });

});

it('uses the evaluation snapshot for mismatch resolution after criteria change', () => {
  render(<ResolutionPanel expectation={{ ...expectation, target_value: 200, comparison: 'greater_than' }} evaluation={evaluation} />);
  expect(screen.getByText('Less than 142.1')).toBeInTheDocument();
  expect(screen.getByText(/\+19\.9/)).toBeInTheDocument();
  expect(screen.queryByText(/More than 200/)).not.toBeInTheDocument();
});
