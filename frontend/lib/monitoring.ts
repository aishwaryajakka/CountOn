import { api } from './api';
import type { Expectation } from './types';
export interface Schedule {
  id: string; expectation_id: string; status: string; next_run_at: string; last_run_at: string | null;
  interval_seconds: number; recurring: boolean; max_evidence_age_seconds: number; attempt_count: number;
  max_attempts: number; last_error: string | null; connection_id: string | null;
  window_start_at: string | null; provider_config: Record<string, unknown>;
}
export interface Preferences {
  email_enabled: boolean; mismatch_enabled: boolean; deadline_enabled: boolean; connection_enabled: boolean;
  quiet_enabled: boolean; quiet_start_hour: number; quiet_end_hour: number; timezone: string;
}
export const monitoring = {
  get: (id: string, signal?: AbortSignal) => api.request<Schedule>(`/expectations/${encodeURIComponent(id)}/monitoring`, { signal }),
  configure: (id: string, current: Schedule, status: 'pending' | 'paused') => api.request<Schedule>(`/expectations/${encodeURIComponent(id)}/monitoring`, { method: 'PUT', body: JSON.stringify({
    next_run_at: new Date().toISOString(), interval_seconds: current.interval_seconds, recurring: current.recurring,
    max_evidence_age_seconds: current.max_evidence_age_seconds, max_attempts: current.max_attempts,
    window_start_at: current.window_start_at, status, connection_id: current.connection_id,
    outlook_rule: current.connection_id ? current.provider_config : null,
  }) }),
  update: (id: string, changes: Partial<Expectation>) => api.request<Expectation>(`/expectations/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(changes) }),
  preferences: (signal?: AbortSignal) => api.request<Preferences>('/notification-preferences', { signal }),
  savePreferences: (prefs: Preferences) => api.request<Preferences>('/notification-preferences', { method: 'PUT', body: JSON.stringify(prefs) }),
};
