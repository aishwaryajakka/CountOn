import type { EvidenceCreate, RingSimEvent, BeeSimEvent } from './types';

// ==========================================
// RING EVENT SIMULATOR & ADAPTER
// ==========================================

export function generateRingEvent(
  kind: RingSimEvent['kind'],
  options: {
    device?: string;
    confidence?: number;
    metric?: string;
    timestamp?: string;
  } = {}
): RingSimEvent {
  const id = `ring_sim_${Math.random().toString(36).substring(2, 9)}`;
  const timestamp = options.timestamp ?? new Date().toISOString();
  return {
    event_id: id,
    kind,
    device: options.device ?? 'front_door',
    timestamp,
    confidence: options.confidence ?? (kind === 'package_detected' ? 0.95 : 0.9),
    metric: options.metric,
  };
}

export function ringEventToEvidence(raw: RingSimEvent): EvidenceCreate {
  const device = raw.device ?? 'front_door';
  const confidence = raw.confidence ?? 0.9;
  const observed_at = raw.timestamp ?? new Date().toISOString();

  if (raw.kind === 'package_detected') {
    return {
      source: 'ring',
      metric: raw.metric ?? 'package_detected',
      value: { value: true, detected: true, kind: raw.kind, device },
      observed_at,
      confidence,
      external_event_id: raw.event_id,
      raw_data: raw as unknown as Record<string, unknown>,
    };
  }

  if (raw.kind === 'package_not_detected') {
    return {
      source: 'ring',
      metric: raw.metric ?? 'package_detected',
      value: { value: false, detected: false, kind: raw.kind, device },
      observed_at,
      confidence,
      external_event_id: raw.event_id,
      raw_data: raw as unknown as Record<string, unknown>,
    };
  }

  if (raw.kind === 'doorbell_ding') {
    return {
      source: 'ring',
      metric: raw.metric ?? 'doorbell_pressed',
      value: { value: true, event: 'doorbell_ding', kind: raw.kind, device },
      observed_at,
      confidence,
      external_event_id: raw.event_id,
      raw_data: raw as unknown as Record<string, unknown>,
    };
  }

  // Motion detected
  return {
    source: 'ring',
    metric: raw.metric ?? 'motion_detected',
    value: { value: true, event: 'motion_detected', kind: raw.kind, device },
    observed_at,
    confidence,
    external_event_id: raw.event_id,
    raw_data: raw as unknown as Record<string, unknown>,
  };
}

// ==========================================
// BEE WEARABLE CONTEXT SIMULATOR & ADAPTER
// ==========================================

export function generateBeeEvent(options: {
  type?: BeeSimEvent['type'];
  speaker?: string;
  summary: string;
  metric?: string;
  confirmed?: boolean;
  start_time?: string;
}): BeeSimEvent {
  const id = `bee_sim_${Math.random().toString(36).substring(2, 9)}`;
  return {
    id,
    type: options.type ?? 'conversation',
    speaker: options.speaker ?? 'Landlord',
    summary: options.summary,
    start_time: options.start_time ?? new Date().toISOString(),
    metric: options.metric,
    confirmed: options.confirmed,
  };
}

export function beeEventToEvidence(raw: BeeSimEvent): EvidenceCreate {
  const observed_at = raw.start_time ?? new Date().toISOString();
  const valDict: Record<string, unknown> = {
    speaker: raw.speaker,
    summary: raw.summary,
    type: raw.type,
  };

  if (raw.confirmed !== undefined) {
    valDict.value = raw.confirmed;
  } else {
    // Basic heuristic if not explicitly set
    const lower = raw.summary.toLowerCase();
    if (lower.includes('cancel') || lower.includes('cannot make it') || lower.includes('reschedule') || lower.includes('emergency')) {
      valDict.value = false;
    } else if (lower.includes('confirm') || lower.includes('will come') || lower.includes('arriving')) {
      valDict.value = true;
    }
  }

  return {
    source: 'bee',
    metric: raw.metric ?? 'conversation_mention',
    value: valDict,
    observed_at,
    confidence: 0.85,
    external_event_id: raw.id,
    raw_data: raw as unknown as Record<string, unknown>,
  };
}

// ==========================================
// UTILITY BILLING SIMULATOR
// ==========================================

export function createUtilityBillEvidence(amount: number): EvidenceCreate {
  return {
    source: 'utility_bill',
    metric: 'total_cost',
    value: { amount },
    unit: 'USD',
    observed_at: new Date().toISOString(),
    confidence: 1.0,
    external_event_id: `util_bill_${Date.now()}`,
    raw_data: { simulated: true, amount },
  };
}

export function createUtilityUsageEvidence(percentageChange: number): EvidenceCreate {
  return {
    source: 'utility_usage',
    metric: 'energy_usage_change',
    value: { percentage: percentageChange },
    unit: 'percent',
    observed_at: new Date().toISOString(),
    confidence: 1.0,
    external_event_id: `util_usage_${Date.now()}`,
    raw_data: { simulated: true, percentageChange },
  };
}

export function createTariffRateEvidence(percentageChange: number): EvidenceCreate {
  return {
    source: 'tariff',
    metric: 'rate_change',
    value: { percentage: percentageChange },
    unit: 'percent',
    observed_at: new Date().toISOString(),
    confidence: 1.0,
    external_event_id: `util_tariff_${Date.now()}`,
    raw_data: { simulated: true, percentageChange },
  };
}
