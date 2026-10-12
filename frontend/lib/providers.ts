import { api } from './api';
import type { Integration } from './types';

export type SyncState = { id: string; connection_id: string; stream: string; status: string; last_success_at: string | null; next_run_at: string; last_error: string | null };
export type SourceRule = { kind: 'bill' | 'reply' | 'commitment' | 'order' | 'calendar'; sender?: string; subject_contains?: string; thread_id?: string; event_id?: string; order_id?: string; expected_start?: string; timezone?: string; recipient?: string; message_id?: string; calendar_uid?: string; occurrence_start?: string };
export type SourceBinding = { id: string; expectation_id: string; sync_id: string; rule: SourceRule };
export type SourceEvent = { id: string; facts: { title?: string; subject?: string; sender?: string; thread_id?: string; start?: string; cancelled?: boolean; unavailable?: boolean }; observed_at: string };
export type PlanQuery = { order_id?: string; calendar_uid?: string; expected_start?: string };
export type PlanChoice = { sync_id: string; external_id: string };
export type SourcePlan = { status: 'ready' | 'clarification' | 'permission_required' | 'unsupported' | 'bounded'; question: string | null; candidates: (PlanChoice & { group_id: string; account_label: string; label: string; rule: SourceRule; suggestion_reason?: string; synced_at?: string | null; sync_status?: string })[]; bedrock_calls: 0 };
const segment = encodeURIComponent;
export const providers = {
  previewPlan: (expectation: string, query: PlanQuery) => api.request<SourcePlan>(`/expectations/${segment(expectation)}/monitoring-plan/preview`, { method: 'POST', body: JSON.stringify(query) }),
  confirmPlan: (expectation: string, query: PlanQuery, sources: PlanChoice[]) => api.request<{ job_id: string; status: string }>(`/expectations/${segment(expectation)}/monitoring-plan/confirm`, { method: 'POST', body: JSON.stringify({ confirmed: true, query, sources }) }),
  capabilities: (signal?: AbortSignal) => api.request<{ google: boolean; microsoft: boolean; automatic_sync: boolean; push: boolean }>('/integrations/providers', { signal }),
  create: (provider: 'google' | 'microsoft', connection_type: 'email' | 'calendar') => api.request<Integration>('/integrations', { method: 'POST', body: JSON.stringify({ provider, connection_type, status: 'pending' }) }),
  authorize: (id: string) => api.request<{ authorization_url: string }>(`/integrations/${segment(id)}/oauth/authorize`, { method: 'POST' }),
  calendars: (id: string) => api.request<{ id: string; name: string }[]>(`/integrations/${segment(id)}/calendars`),
  states: (id: string, signal?: AbortSignal) => api.request<SyncState[]>(`/integrations/${segment(id)}/sync`, { signal }),
  sync: (id: string, calendar_id?: string) => api.request<SyncState>(`/integrations/${segment(id)}/sync`, { method: 'POST', body: JSON.stringify(calendar_id ? { calendar_id } : {}) }),
  run: (id: string) => api.request<SyncState>(`/provider-sync/${segment(id)}/run`, { method: 'POST' }),
  events: (id: string) => api.request<SourceEvent[]>(`/provider-sync/${segment(id)}/events`),
  bind: (expectation: string, sync_id: string, rule: SourceRule) => api.request<SourceBinding>(`/expectations/${segment(expectation)}/sources`, { method: 'POST', body: JSON.stringify({ sync_id, rule }) }),
  bindings: (expectation: string, signal?: AbortSignal) => api.request<SourceBinding[]>(`/expectations/${segment(expectation)}/sources`, { signal }),
  unbind: (expectation: string, id: string) => api.request<void>(`/expectations/${segment(expectation)}/sources/${segment(id)}`, { method: 'DELETE' }),
  disconnect: (id: string) => api.request<{ disconnected: boolean; provider_revoked: boolean; revocation_action: string | null }>(`/integrations/${segment(id)}/disconnect`, { method: 'POST', body: JSON.stringify({ revoke: true, erase_evidence: false }) }),
};
export function consentUrl(value: string): string {
  const url = new URL(value);
  if (url.protocol !== 'https:' || !['accounts.google.com', 'login.microsoftonline.com'].includes(url.hostname) || url.username || url.password) throw new Error('The provider returned an invalid consent address.');
  return url.toString();
}
