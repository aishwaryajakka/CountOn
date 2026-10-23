import { api } from './api';
import type { BeeCliStatus, BeeImportCandidate } from './types';

export const beeCli = {
  status: (signal?: AbortSignal) => api.request<BeeCliStatus>('/integrations/bee-cli/status', { signal }),
  pairing: () => api.request<{ pairing_code: string; expires_at: string }>('/integrations/bee-cli/pairings', { method: 'POST' }),
  candidates: (signal?: AbortSignal) => api.request<BeeImportCandidate[]>('/integrations/bee-cli/candidates', { signal }),
  import: (expectationId: string, candidateIds: string[]) => api.request<{ imported: number; duplicate: number; evaluation_ids: string[]; binding_id: string }>('/integrations/bee-cli/imports', { method: 'POST', body: JSON.stringify({ expectation_id: expectationId, candidate_ids: candidateIds, consent: true, confirm_source_binding: true }) }),
  disconnect: () => api.request<{ disconnected: boolean; local_action: string }>('/integrations/bee-cli/disconnect', { method: 'POST', body: JSON.stringify({ revoke: true }) }),
};
