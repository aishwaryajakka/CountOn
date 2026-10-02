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
  id: string; user_id: string; expectation_id: string; evaluation_id: string;
  type: string; channel: string; status: 'pending' | 'read' | 'sent' | 'failed' | 'dismissed';
  message: string; metadata: JsonObject; sent_at: string | null; created_at: string;
}
export interface Integration {
  id: string; user_id: string; provider: 'google' | 'microsoft' | 'ring' | 'bee' | 'utility' | 'delivery';
  connection_type: 'email' | 'calendar' | 'camera' | 'wearable' | 'utility' | 'delivery';
  external_account_id: string | null; display_name: string | null;
  status: 'pending' | 'connected' | 'disconnected' | 'error'; scopes: string[];
  metadata: { mock: boolean; demo: boolean; demo_tag: string | null; account_kind: string | null };
  last_synced_at: string | null; created_at: string; updated_at: string; credential_state: 'not_configured';
}
export interface WatchedExpectation { expectation: Expectation; latest: Evaluation | null }
