import type { Comparison, ExpectationCreate, ExpectationType } from './types';

// TODO: replace this explicit manual adapter with the future Bedrock compiler.
// It never infers structured fields or invents a baseline from free text.
export function manualExpectation(input: { claim: string; type: ExpectationType; metric: string; comparison: Comparison; target: string; sources: string; threshold: string }): ExpectationCreate {
  if (!input.claim.trim()) throw new Error('Tell us what you’re counting on.');
  if (!input.metric.trim()) throw new Error('Add the metric you want to watch.');
  const threshold = Number(input.threshold);
  if (!input.threshold.trim() || !Number.isFinite(threshold) || threshold < 0 || threshold > 100) throw new Error('Tolerance must be between 0 and 100 percent.');
  const payload: ExpectationCreate = { claim: input.claim.trim(), type: input.type, metric: input.metric.trim(), evidence_sources: [...new Set(input.sources.split(',').map(source => source.trim()).filter(Boolean))], materiality_threshold: threshold / 100 };
  if (input.type === 'numeric_comparison') {
    const target = Number(input.target);
    if (!input.target.trim() || !Number.isFinite(target)) throw new Error('Add a valid numerical target.');
    payload.target_value = target; payload.comparison = input.comparison;
  }
  return payload;
}
