import type { AuditEvent, Evidence, Evaluation, Expectation, Notification, WatchedExpectation } from './types';

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
export function creationSourceLabel(expectation: Expectation): string | null {
  switch (expectation.compiler_metadata.creation_source) {
    case 'alexa_skill': return 'Created via Alexa';
    case 'alexa_web': return 'Created via Alexa web';
    case 'web': return 'Created via Web';
    case 'mcp': return 'Created via MCP';
    default: return null;
  }
}
export function auditSourceLabel(event: AuditEvent): string {
  if (event.source_provenance === 'SIMULATED_RING' || event.evidence?.source === 'ring_simulator') return 'Ring — SIMULATED';
  if (event.source_provenance === 'SIMULATED_BEE' || event.evidence?.source === 'bee_simulator') return 'Bee — SIMULATED';
  if (event.source_provider === 'ALEXA') return 'Alexa Custom Skill';
  if (event.source_provider === 'ALEXA_WEB') return 'Alexa web';
  return event.source_provider ? `${humanize(event.source_provider.toLowerCase())}${event.source_provenance ? ` · ${humanize(event.source_provenance.toLowerCase())}` : ''}` : 'CountOn';
}
export function auditActionLabel(event: AuditEvent): string {
  switch (event.event_type) {
    case 'EXPECTATION_CONFIRMED':
      return event.source_provider === 'ALEXA' ? 'Alexa created expectation' : event.source_provider === 'ALEXA_WEB' ? 'Alexa web created expectation' : 'Expectation confirmed';
    case 'EXPECTATION_CREATED': return 'Expectation created';
    case 'EVIDENCE_INGESTED': return `Evidence received from ${event.source_provider ? humanize(event.source_provider.toLowerCase()) : 'a declared source'}`;
    case 'EVALUATION_COMPLETED': return event.result_status ? `CountOn evaluated ${event.result_status}` : 'Evaluation recorded';
    case 'EXPLANATION_GENERATED': return event.action_metadata.bedrock_used === true && event.action_metadata.grounded === true ? 'Bedrock generated grounded explanation' : event.action_metadata.fallback_used === true ? 'CountOn recorded fallback explanation' : 'Explanation recorded';
    case 'NOTIFICATION_CREATED': return 'Notification created';
    default: return humanize(event.action_taken.replaceAll('.', '_'));
  }
}
const sources: Record<string, string> = { utility_bill: 'Utility bill', utility_usage: 'Energy usage', tariff: 'Electricity rate', delivery: 'Delivery tracking', ring_simulator: 'Ring · SIMULATED', bee_simulator: 'Bee · SIMULATED', ring: 'Ring', bee: 'Bee wearable', gmail: 'Gmail', google_calendar: 'Google Calendar', outlook_calendar: 'Outlook Calendar', confirmation_email: 'Confirmation email' };
export const humanize = (value: string) => sources[value] ?? value.replaceAll('_', ' ').replace(/^./, char => char.toUpperCase());
export function evidenceSourceLabel(item: Pick<Evidence, 'source' | 'raw_data'>): string {
  const label = ({ gmail_email: 'Gmail', outlook_email: 'Outlook', microsoft_calendar: 'Microsoft Calendar' } as Record<string, string>)[item.source] ?? humanize(item.source);
  return item.raw_data.simulated === true && !item.source.endsWith('_simulator') ? `${label} · SIMULATED` : label;
}
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
  if (typeof item.value.summary === 'string') return item.value.summary;
  if (typeof item.value.event === 'string') return humanize(item.value.event);
  if (item.value.detected !== undefined) return item.value.detected ? 'Package detected' : 'No package detected';
  return 'Observation recorded';
}
export const comparisonLabels = { less_than: 'Less than', less_than_or_equal: 'At most', greater_than: 'More than', greater_than_or_equal: 'At least', equal: 'Equal to', not_equal: 'Different from' };
export function expectedText(expectation: Expectation, unit?: string | null, evaluation?: Evaluation | null): string {
  // A saved result describes its own criteria, even after the expectation is edited.
  if (evaluation && ('target' in evaluation.expected || 'comparison' in evaluation.expected || expectation.type === 'numeric_comparison')) {
    const { target, comparison } = evaluation.expected;
    if (typeof target === 'number' && Number.isFinite(target) && typeof comparison === 'string' && Object.hasOwn(comparisonLabels, comparison)) {
      return `${comparisonLabels[comparison as keyof typeof comparisonLabels]} ${number(target, unit)}`;
    }
    return 'Criteria not recorded for this evaluation';
  }
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
  const reason = evaluation.reasoning.reason;
  if (evaluation.result === 'MISMATCH' && reason === 'reply_absent_after_covered_deadline') return 'No matching reply was found during verified mailbox coverage through your deadline.';
  if (evaluation.result === 'MISMATCH' && reason === 'event_observed_after_deadline') return 'The recorded event occurred after your deadline.';
  if (evaluation.result === 'MISMATCH') return 'The latest observation for the expected metric did not meet your criteria, including the configured tolerance.';
  if (evaluation.result === 'MATCH') return 'The latest observation for the expected metric met your criteria, including the configured tolerance.';
  if (reason === 'unsupported_expectation_type' || reason === 'temporal_evaluation_not_implemented' || reason === 'not_implemented') return 'This evaluation path could not establish the event. Automatic temporal tracking requires explicit criteria and trustworthy source evidence.';
  if (reason === 'no_relevant_evidence') return 'There is no usable evidence for the exact metric this expectation is watching.';
  if (reason === 'incomplete_mailbox_coverage') return 'CountOn does not have continuous mailbox coverage for this deadline yet. It cannot safely claim a reply was absent.';
  if (reason === 'ambiguous_sources') return 'More than one source is bound. Choose one source so CountOn can evaluate the right account.';
  if (reason === 'source_unavailable' || reason === 'source_not_bound') return 'The selected source is unavailable. Reconnect or choose a source; the current outcome is unknown.';
  if (reason === 'stale_source' || reason === 'stale_evidence') return 'The source or evidence is too old to establish the current outcome. CountOn is waiting for a fresh observation.';
  if (reason === 'conflicting_evidence') return 'The relevant observations conflict. CountOn will keep the outcome unknown until the evidence is clear.';
  return 'The available evidence does not support a determination yet.';
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
