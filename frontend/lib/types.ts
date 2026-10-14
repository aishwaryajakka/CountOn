export type JsonObject = Record<string, unknown>;
export type ExpectationStatus = 'monitoring' | 'fulfilled' | 'contradicted' | 'unknown' | 'resolved' | 'cancelled';
export type ExpectationType = 'numeric_comparison' | 'boolean' | 'temporal' | 'event';
export type Comparison = 'less_than' | 'less_than_or_equal' | 'greater_than' | 'greater_than_or_equal' | 'equal' | 'not_equal';
export type Result = 'MATCH' | 'MISMATCH' | 'UNKNOWN';

export interface Expectation {
  id: string; user_id: string; claim: string; type: ExpectationType; metric: string | null;
  comparison: Comparison | null; baseline: number | null; target_value: number | null;
  deadline: string | null; evidence_sources: string[]; materiality_threshold: number;
  status: ExpectationStatus; compiler_metadata: JsonObject; created_at: string; updated_at: string;
}

export interface ExpectationCreate {
  claim: string; type: ExpectationType; metric?: string; comparison?: Comparison;
  baseline?: number; target_value?: number; deadline?: string; evidence_sources: string[]; materiality_threshold: number;
}

export interface ExpectationUpdate {
  claim?: string;
  metric?: string;
  comparison?: Comparison;
  baseline?: number;
  target_value?: number;
  deadline?: string;
  evidence_sources?: string[];
  materiality_threshold?: number;
  status?: ExpectationStatus;
}

export interface EvidenceCreate {
  source: string;
  metric?: string;
  value: JsonObject;
  unit?: string | null;
  observed_at: string;
  confidence?: number;
  external_event_id?: string | null;
  raw_data?: JsonObject;
}

export interface Evidence {
  id: string; expectation_id: string; external_event_id: string | null; source: string;
  metric: string | null; value: JsonObject; unit: string | null; observed_at: string;
  confidence: number; raw_data: JsonObject; created_at: string;
}

export interface Evaluation {
  id: string; expectation_id: string; result: Result; expected: JsonObject;
  observed: JsonObject; confidence: number; reasoning: JsonObject; created_at: string;
}

export interface Notification {
  id: string; user_id: string; expectation_id: string; evaluation_id: string | null;
  type: string; channel: string; status: 'pending' | 'read' | 'sent' | 'failed' | 'dismissed';
  message: string; metadata: JsonObject; sent_at: string | null; created_at: string;
}

export interface IntegrationCreate {
  provider: 'google' | 'microsoft' | 'ring' | 'bee' | 'utility' | 'delivery';
  connection_type: 'email' | 'calendar' | 'camera' | 'wearable' | 'utility' | 'delivery';
  external_account_id?: string | null;
  display_name?: string | null;
  status?: 'pending' | 'connected' | 'disconnected' | 'error';
  scopes?: string[];
  metadata?: { mock?: boolean; demo?: boolean; demo_tag?: string | null; account_kind?: 'personal' | 'work' | 'family' | null };
}

export interface IntegrationUpdate {
  display_name?: string | null;
  external_account_id?: string | null;
  status?: 'pending' | 'connected' | 'disconnected' | 'error';
  scopes?: string[];
  metadata?: { mock?: boolean; demo?: boolean; demo_tag?: string | null; account_kind?: 'personal' | 'work' | 'family' | null };
}

export interface Integration {
  id: string; user_id: string; provider: 'google' | 'microsoft' | 'ring' | 'bee' | 'utility' | 'delivery';
  connection_type: 'email' | 'calendar' | 'camera' | 'wearable' | 'utility' | 'delivery';
  external_account_id: string | null; display_name: string | null;
  status: 'pending' | 'connected' | 'disconnected' | 'error'; scopes: string[];
  metadata: { mock: boolean; demo: boolean; demo_tag: string | null; account_kind: string | null };
  last_synced_at: string | null; connected_at: string | null; revoked_at: string | null;
  failure_status: string | null; created_at: string; updated_at: string; credential_state: 'not_configured' | 'configured';
}

export interface AuditEvent {
  audit_event_id: string; counton_user_id: string; expectation_id: string | null;
  event_type: string; occurred_at: string; source_provider: string | null;
  source_type: string | null; source_provenance: string | null; source_reference: string | null;
  evidence_id: string | null; evaluation_id: string | null; result_status: Result | null;
  action_taken: string; actor_type: 'USER' | 'SYSTEM' | 'PROVIDER';
  action_metadata: JsonObject; request_id: string | null;
  expectation: { id: string; claim: string; status: string } | null;
  evidence: { id: string; source: string; metric: string | null; value: JsonObject; unit: string | null; observed_at: string } | null;
}

export interface WatchedExpectation { expectation: Expectation; latest: Evaluation | null }

export interface RingSimEvent {
  simulated: true;
  event_id: string;
  kind: 'package_detected' | 'package_not_detected' | 'doorbell_ding' | 'motion_detected';
  device: string;
  timestamp: string;
  confidence: number;
  metric?: string;
}

export interface BeeSimEvent {
  simulated: true;
  id: string;
  type: 'conversation' | 'note' | 'commitment';
  speaker: string;
  summary: string;
  start_time: string;
  metric?: string;
  confirmed?: boolean;
}

export interface BeeCliStatus {
  simulator_available: true;
  state: 'not_paired' | 'paired' | 'import_enabled' | 'disconnected' | 'error';
  connection_id: string | null;
  cli_version: string | null;
  last_sync_at: string | null;
  last_error: string | null;
  pending_candidates: number;
}

export interface BeeImportCandidate {
  id: string; connection_id: string; external_id: string;
  category: 'fact' | 'todo' | 'conversation' | 'journal'; summary: string;
  observed_at: string; confidence: number; status: 'pending' | 'imported' | 'rejected';
}
