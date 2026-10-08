import { describe, expect, it, vi } from 'vitest';
import { contextSignals, displayTitle, evidenceValue, expectedText, formatDate, getExpectationPresentationStatus, humanize, latestMetricEvidence, notificationTitle, number, summary } from '@/lib/presentation';
import { manualExpectation } from '@/lib/manual-expectation';
import { evidence, evaluation, expectation, notification } from './fixtures';
describe('real contract presentation', () => {
  it('does not infer personal account ownership or rewrite unrelated meeting claims', () => {
    expect(humanize('gmail')).toBe('Gmail');
    expect(displayTitle({ ...expectation, claim: 'My 5 meetings will finish early' })).toBe('My 5 meetings will finish early');
    expect(displayTitle({ ...expectation, claim: 'I should have no meetings after 5 PM tomorrow.' })).toBe('No meetings after 5 PM');
  });
  it('uses the profile calendar across year and daylight saving boundaries', () => {
    vi.useFakeTimers();
    try {
      vi.setSystemTime(new Date('2027-01-01T01:00:00Z'));
      expect(formatDate('2026-12-31T23:00:00Z', 'America/Los_Angeles')).toContain('Today');
      expect(formatDate('2026-12-30T23:00:00Z', 'America/Los_Angeles')).toContain('Yesterday');
      vi.setSystemTime(new Date('2026-03-09T07:30:00Z'));
      expect(formatDate('2026-03-08T08:30:00Z', 'America/Los_Angeles')).toContain('Yesterday');
    } finally { vi.useRealTimers(); }
  });
  it.each([['MATCH', 'match'], ['MISMATCH', 'attention'], ['UNKNOWN', 'waiting']] as const)('maps %s separately from backend values', (result, label) => {
    expect(getExpectationPresentationStatus(expectation, { ...evaluation, result })).toBe(label);
    expect(expectation.status).toBe('contradicted');
  });
  it('keeps terminal status ahead of a historical evaluation', () => {
    expect(getExpectationPresentationStatus({ ...expectation, status: 'cancelled' }, evaluation)).toBe('cancelled');
    expect(getExpectationPresentationStatus({ ...expectation, status: 'monitoring' }, null)).toBe('monitoring');
  });
  it('counts actual results including unknown on a monitoring expectation', () => {
    expect(summary([{ expectation, latest: evaluation }, { expectation: { ...expectation, status: 'monitoring' }, latest: { ...evaluation, result: 'UNKNOWN' } }])).toMatchObject({ attention: 1, waiting: 1, match: 0 });
  });
  it('honors an explicit zero target and generic units', () => {
    expect(expectedText({ ...expectation, target_value: 0 }, 'kWh')).toBe('Less than 0 kWh');
    expect(number(22, 'percent')).toBe('22%');
    expect(number(22, 'KWH')).toBe('22 KWH');
    expect(evidenceValue(evidence[0])).toBe('$162.00');
  });
  it('uses observed_at for late-arriving evidence', () => {
    const late = { ...evidence[0], id: 'late-old', observed_at: '2026-10-01T12:00:00Z', created_at: '2026-10-03T12:00:00Z', value: { amount: 130 } };
    expect(latestMetricEvidence([...evidence, late], 'total_cost')?.id).toBe('bill-evidence');
    expect(contextSignals(evidence)).toEqual([{ label: 'Energy usage', value: -18 }]);
  });
  it('uses evaluation facts for a readable alert without inferring a cause', () => {
    expect(notificationTitle(notification, { expectation, latest: evaluation })).toBe('Your electricity bill was higher than expected');
    expect(notificationTitle(notification, { expectation, latest: { ...evaluation, id: 'different-evaluation' } })).toBe('Electricity bill needs your attention');
  });
});
describe('manual creation adapter', () => {
  const input = { claim: ' My value should fall ', type: 'numeric_comparison' as const, metric: 'value', comparison: 'less_than' as const, target: '0', sources: 'meter, meter, receipt', threshold: '5' };
  it('creates only supported backend fields without inventing a baseline', () => {
    expect(manualExpectation(input)).toEqual({ claim: 'My value should fall', type: 'numeric_comparison', metric: 'value', comparison: 'less_than', target_value: 0, evidence_sources: ['meter', 'receipt'], materiality_threshold: .05 });
  });
  it('rejects an empty numeric target', () => expect(() => manualExpectation({ ...input, target: '' })).toThrow('numerical target'));
  it('rejects invalid tolerances', () => expect(() => manualExpectation({ ...input, threshold: '101' })).toThrow('Tolerance'));
});
