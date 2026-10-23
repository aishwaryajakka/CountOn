import { api } from './api';
import { createUtilityBillEvidence, generateBeeEvent, generateRingEvent } from './simulators';
import type { ExpectationCreate } from './types';

export const demoScenarios = [
  { id: 'electricity', title: 'Electricity Bill Surprise', claim: 'My next electricity bill should be below $150.', source: 'DEMO utility bill · SIMULATED', expected: 'MISMATCH · $180 is above the $150 target', button: 'Run Electricity Demo' },
  { id: 'package', title: 'Package Arrived', claim: 'My package should arrive by Friday.', source: 'DEMO delivery confirmation + Ring · SIMULATED', expected: 'MATCH · positive package delivery evidence', button: 'Run Package Demo' },
  { id: 'bee', title: 'Plumber Commitment', claim: 'My landlord said the plumber will arrive Friday.', source: 'Bee commitment · SIMULATED', expected: 'UNKNOWN · a promise does not confirm arrival', button: 'Run Bee Demo' },
] as const;
export type DemoKind = typeof demoScenarios[number]['id'];

// Explicit demo setup, not a natural-language compiler. Friday means the end of
// the upcoming Friday in this browser's timezone, and is persisted as an instant.
export function demoExpectation(kind: DemoKind, now = new Date()): ExpectationCreate {
  const scenario = demoScenarios.find(item => item.id === kind)!;
  if (kind === 'electricity') return {
    claim: scenario.claim, type: 'numeric_comparison', metric: 'total_cost',
    comparison: 'less_than', target_value: 150, evidence_sources: ['utility_bill'], materiality_threshold: 0,
  };
  const friday = new Date(now);
  friday.setDate(friday.getDate() + (5 - friday.getDay() + 7) % 7);
  friday.setHours(23, 59, 59, 999);
  return {
    claim: scenario.claim, type: 'boolean',
    metric: kind === 'package' ? 'delivered' : 'appointment_confirmed',
    deadline: friday.toISOString(), evidence_sources: kind === 'package' ? ['delivery', 'ring_simulator'] : ['bee_simulator'],
    materiality_threshold: 0,
  };
}

export async function submitDemoEvidence(kind: DemoKind, expectationId: string) {
  if (kind === 'electricity') {
    const evidence = createUtilityBillEvidence(180);
    evidence.raw_data = { simulated: true, category: 'DEMO', provenance: 'USER_SUBMITTED' };
    await api.addEvidence(expectationId, evidence);
    await api.evaluate(expectationId, `simulation:${evidence.external_event_id}`);
  } else if (kind === 'package') {
    // Same normalized positive delivery fact as the existing seeded demo. This
    // is user-approved DEMO input, not a claim of live shipping-provider access.
    await api.addEvidence(expectationId, {
      source: 'delivery', metric: 'delivered', value: { value: true },
      observed_at: new Date().toISOString(), confidence: 1,
      external_event_id: `demo_delivery_${crypto.randomUUID()}`,
      raw_data: { simulated: true, category: 'DEMO', provenance: 'USER_SUBMITTED' },
    });
    // A positive observation, explicitly associated with this new demo package.
    // No-detection is deliberately never used as proof of nondelivery.
    await api.simulateRing(expectationId, generateRingEvent('package_detected', { metric: 'delivered' }));
  } else {
    await api.simulateBee(expectationId, generateBeeEvent({
      type: 'commitment', speaker: 'Landlord', summary: demoScenarios[2].claim,
      metric: 'appointment_confirmed', confirmed: true,
    }));
  }
}

export async function loadDemoSnapshot(id: string) {
  const [expectation, evidence, evaluation, evaluations, notifications, activity] = await Promise.all([
    api.expectation(id), api.evidence(id), api.latest(id), api.evaluations(id),
    api.notifications(), api.auditEvents({ expectationId: id }),
  ]);
  return { expectation, evidence, evaluation, evaluations,
    notifications: notifications.filter(item => item.expectation_id === id), activity };
}
export type DemoSnapshot = Awaited<ReturnType<typeof loadDemoSnapshot>>;
