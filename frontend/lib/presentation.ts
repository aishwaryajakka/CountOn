import type { Evidence, Evaluation, Expectation, Notification, WatchedExpectation } from './types';

export type PresentationStatus = 'match' | 'attention' | 'waiting' | 'monitoring' | 'resolved' | 'cancelled';
export const statusLabels: Record<PresentationStatus, string> = { match: 'Matched', attention: 'Needs attention', waiting: 'Waiting for evidence', monitoring: 'Monitoring', resolved: 'Resolved', cancelled: 'Cancelled' };
export const evaluationLabels = { MATCH: statusLabels.match, MISMATCH: statusLabels.attention, UNKNOWN: statusLabels.waiting };
export function getExpectationPresentationStatus(expectation: Expectation, latest?: Evaluation | null): PresentationStatus {
  if (expectation.status === 'cancelled' || expectation.status === 'resolved') return expectation.status;
  if (latest) return latest.result === 'MATCH' ? 'match' : latest.result === 'MISMATCH' ? 'attention' : 'waiting';
  return expectation.status === 'fulfilled' ? 'match' : expectation.status === 'contradicted' ? 'attention' : expectation.status === 'unknown' ? 'waiting' : 'monitoring';
}
export function summary(rows: WatchedExpectation[]) {
  const counts = { match: 0, attention: 0, waiting: 0, monitoring: 0, resolved: 0, cancelled: 0 };
  rows.forEach(row => counts[getExpectationPresentationStatus(row.expectation, row.latest)]++);
  return counts;
}
export function displayTitle(expectation: Expectation): string {
  const claim = expectation.claim.toLowerCase();
  if (claim.includes('electric') && claim.includes('bill')) return 'Electricity bill';
  if (claim.includes('package')) return 'Package delivery';
  if (claim.includes('plumber')) return 'Plumber appointment';
  if (claim.includes('dentist')) return 'Dentist appointment';
  if (/\bno meetings? after 5\s*(?:pm|p\.m\.)\b/.test(claim)) return 'No meetings after 5 PM';
  return expectation.claim.length > 65 ? `${expectation.claim.slice(0, 62)}…` : expectation.claim;
}
const sources: Record<string, string> = { utility_bill: 'Utility bill', utility_usage: 'Energy usage', tariff: 'Electricity rate', delivery: 'Delivery tracking', ring: 'Ring', gmail: 'Gmail', google_calendar: 'Google Calendar', outlook_calendar: 'Outlook Calendar', confirmation_email: 'Confirmation email' };
export const humanize = (value: string) => sources[value] ?? value.replaceAll('_', ' ').replace(/^./, char => char.toUpperCase());
const currencies = new Set(Intl.supportedValuesOf('currency'));
export function number(value: number, unit?: string | null) {
  if (unit && currencies.has(unit)) {
    try { return new Intl.NumberFormat(undefined, { style: 'currency', currency: unit }).format(value); } catch { /* Non-currency three-letter units use plain formatting. */ }
  }
  const formatted = new Intl.NumberFormat(undefined, { maximumFractionDigits: 3 }).format(value);
  return unit === 'percent' || unit === '%' ? `${formatted}%` : `${formatted}${unit ? ` ${unit}` : ''}`;
}
export function formatDate(value: string, timeZone?: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Date unavailable';
  const localDay = (day: Date) => new Intl.DateTimeFormat('en-CA', { timeZone, year: 'numeric', month: '2-digit', day: '2-digit' }).format(day);
  const today = localDay(new Date());
  const yesterday = new Date(`${today}T12:00:00Z`); yesterday.setUTCDate(yesterday.getUTCDate() - 1);
  const previousDay = yesterday.toISOString().slice(0, 10);
  const day = localDay(date);
  const prefix = day === today ? 'Today' : day === previousDay ? 'Yesterday' : new Intl.DateTimeFormat(undefined, { timeZone, month: 'short', day: 'numeric', year: day.slice(0, 4) !== today.slice(0, 4) ? 'numeric' : undefined }).format(date);
  return `${prefix} · ${new Intl.DateTimeFormat(undefined, { timeZone, hour: 'numeric', minute: '2-digit' }).format(date)}`;
}
export function evidenceValue(item: Evidence, timeZone?: string): string {
  const value = item.value.amount ?? item.value.value ?? item.value.percentage ?? item.value.date ?? item.value.start;
  if (typeof value === 'number') return number(value, item.unit);
  if (typeof value === 'boolean') return value ? 'Confirmed' : 'Not confirmed';
  if (typeof value === 'string') {
    if (/^\d{4}-\d{2}-\d{2}T/.test(value)) return formatDate(value, timeZone);
    if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(new Date(`${value}T12:00:00`));
    return value;
  }
  return 'Observation recorded';
}
export const comparisonLabels = { less_than: 'Less than', less_than_or_equal: 'At most', greater_than: 'More than', greater_than_or_equal: 'At least', equal: 'Equal to', not_equal: 'Different from' };
export function expectedText(expectation: Expectation, unit?: string | null): string {
  const target = expectation.target_value ?? expectation.baseline;
  if (expectation.type === 'numeric_comparison' && target != null && expectation.comparison) return `${comparisonLabels[expectation.comparison]} ${number(target, unit)}`;
  if (expectation.type === 'boolean') return 'Confirmation of this expectation';
  return 'Evidence matching your expectation';
}
export function observedText(evaluation?: Evaluation | null, unit?: string | null): string {
  const value = evaluation?.observed.value;
  return typeof value === 'number' ? number(value, unit) : typeof value === 'boolean' ? value ? 'Confirmed' : 'Not confirmed' : 'Not yet determined';
}
export function reasoningText(evaluation: Evaluation | null) {
  if (!evaluation) return 'No evaluation has been recorded yet. Evidence will appear here when it is received.';
  if (evaluation.result === 'MISMATCH') return 'The latest observation for the expected metric did not meet your criteria, including the configured tolerance.';
  if (evaluation.result === 'MATCH') return 'The latest observation for the expected metric met your criteria, including the configured tolerance.';
  const reason = evaluation.reasoning.reason;
  if (reason === 'unsupported_expectation_type' || reason === 'temporal_evaluation_not_implemented' || reason === 'not_implemented') return 'This expectation needs a time-based interpretation. Temporal and event evaluation are not available yet.';
  if (reason === 'no_relevant_evidence') return 'There is no usable evidence for the exact metric this expectation is watching.';
  return 'The available evidence does not support a determination yet. Time-based and event interpretations remain unsupported.';
}
export function latestMetricEvidence(items: Evidence[], metric: string | null): Evidence | undefined {
  return items.filter(item => item.metric === metric).sort((a, b) => Date.parse(b.observed_at) - Date.parse(a.observed_at) || Date.parse(b.created_at) - Date.parse(a.created_at) || b.id.localeCompare(a.id))[0];
}
export function contextSignals(items: Evidence[]) {
  return ['energy_usage_change', 'rate_change'].flatMap(metric => {
    const item = latestMetricEvidence(items, metric);
    const value = item?.value.percentage;
    return typeof value === 'number' ? [{ label: metric === 'rate_change' ? 'Electricity rate' : 'Energy usage', value }] : [];
  });
}
export function notificationTitle(item: Notification, row?: WatchedExpectation) {
  if (!row) return item.message;
  const { expectation, latest } = row;
  const actual = latest?.observed.value;
  const target = latest?.expected.target;
  if (displayTitle(expectation) === 'Electricity bill' && expectation.metric === 'total_cost'
      && latest?.id === item.evaluation_id && latest.result === 'MISMATCH'
      && (latest.expected.comparison === 'less_than' || latest.expected.comparison === 'less_than_or_equal')
      && typeof actual === 'number' && typeof target === 'number' && actual > target) {
    return 'Your electricity bill was higher than expected';
  }
  return `${displayTitle(expectation)} needs your attention`;
}
