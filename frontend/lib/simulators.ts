import type { EvidenceCreate, RingSimEvent, BeeSimEvent, Expectation, WatchedExpectation } from './types';

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
  const id = `ring_sim_${crypto.randomUUID()}`;
  const timestamp = options.timestamp ?? new Date().toISOString();
  return {
    simulated: true,
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
      source: 'ring_simulator',
      metric: raw.metric ?? 'package_detected',
      value: { value: true, detected: true, kind: raw.kind, device },
      observed_at,
      confidence,
      external_event_id: raw.event_id,
      raw_data: { ...raw, simulated: true },
    };
  }

  if (raw.kind === 'package_not_detected') {
    return {
      source: 'ring_simulator',
      metric: raw.metric ?? 'package_detected',
      value: { detected: false, kind: raw.kind, device },
      observed_at,
      confidence,
      external_event_id: raw.event_id,
      raw_data: { ...raw, simulated: true },
    };
  }

  if (raw.kind === 'doorbell_ding') {
    return {
      source: 'ring_simulator',
      metric: raw.metric ?? 'doorbell_pressed',
      value: { value: true, event: 'doorbell_ding', kind: raw.kind, device },
      observed_at,
      confidence,
      external_event_id: raw.event_id,
      raw_data: { ...raw, simulated: true },
    };
  }

  // Motion detected
  return {
    source: 'ring_simulator',
    metric: raw.metric ?? 'motion_detected',
    value: { value: true, event: 'motion_detected', kind: raw.kind, device },
    observed_at,
    confidence,
    external_event_id: raw.event_id,
    raw_data: { ...raw, simulated: true },
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
  const id = `bee_sim_${crypto.randomUUID()}`;
  return {
    simulated: true,
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
  }

  return {
    source: 'bee_simulator',
    metric: raw.metric ?? 'conversation_mention',
    value: valDict,
    observed_at,
    confidence: 0.85,
    external_event_id: raw.id,
    raw_data: { ...raw, simulated: true },
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
    external_event_id: `util_bill_${crypto.randomUUID()}`,
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
    external_event_id: `util_usage_${crypto.randomUUID()}`,
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
    external_event_id: `util_tariff_${crypto.randomUUID()}`,
    raw_data: { simulated: true, percentageChange },
  };
}

// Never attach a demo to an arbitrary first row or infer compatibility from prose.
export function simulatorTargets(rows: WatchedExpectation[], kind: 'utility' | 'ring' | 'bee'): Expectation[] {
  return rows.map(row => row.expectation).filter(exp => {
    if (['resolved', 'cancelled'].includes(exp.status)) return false;
    if (kind === 'utility') return exp.type === 'numeric_comparison' && exp.metric === 'total_cost';
    if (kind === 'ring') return ['boolean', 'event', 'temporal'].includes(exp.type) && ['package_detected', 'delivered', 'package_delivery', 'delivery_reported'].includes(exp.metric ?? '');
    return exp.type === 'boolean' && exp.metric === 'appointment_confirmed';
  });
}

export function simulatorTarget(rows: WatchedExpectation[], kind: 'utility' | 'ring' | 'bee', selectedId?: string): Expectation {
  const targets = simulatorTargets(rows, kind);
  const selected = selectedId ? targets.find(exp => exp.id === selectedId) : targets.length === 1 ? targets[0] : undefined;
  if (!selected) throw new Error(targets.length ? 'Select the exact compatible expectation in Interactive Demos.' : 'No compatible active expectation. Create one before simulating evidence.');
  return selected;
}
