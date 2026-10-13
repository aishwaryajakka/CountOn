import { describe, expect, it } from 'vitest';
import {
  generateRingEvent,
  ringEventToEvidence,
  generateBeeEvent,
  beeEventToEvidence,
  createUtilityBillEvidence,
  createUtilityUsageEvidence,
  createTariffRateEvidence,
} from '@/lib/simulators';

describe('Ring Event Simulator & Adapter', () => {
  it('generates a package detected event and converts to MATCH-compatible evidence', () => {
    const raw = generateRingEvent('package_detected', { device: 'front_door', confidence: 0.95 });
    expect(raw.kind).toBe('package_detected');
    expect(raw.device).toBe('front_door');

    const ev = ringEventToEvidence(raw);
    expect(ev.source).toBe('ring_simulator');
    expect(ev.metric).toBe('package_detected');
    expect(ev.value.value).toBe(true);
    expect(ev.value.detected).toBe(true);
    expect(ev.confidence).toBe(0.95);
  });

  it('generates a package not detected event and preserves absence without claiming failed delivery', () => {
    const raw = generateRingEvent('package_not_detected');
    const ev = ringEventToEvidence(raw);
    expect(ev.source).toBe('ring_simulator');
    expect(ev.value).not.toHaveProperty('value');
    expect(ev.value.detected).toBe(false);
  });

  it('generates doorbell ring and motion events with appropriate metrics', () => {
    const doorbell = generateRingEvent('doorbell_ding');
    const evDoorbell = ringEventToEvidence(doorbell);
    expect(evDoorbell.metric).toBe('doorbell_pressed');
    expect(evDoorbell.value.event).toBe('doorbell_ding');

    const motion = generateRingEvent('motion_detected');
    const evMotion = ringEventToEvidence(motion);
    expect(evMotion.metric).toBe('motion_detected');
    expect(evMotion.value.event).toBe('motion_detected');
  });
});

describe('Bee Context Simulator & Adapter', () => {
  it('generates wearable conversation confirming plumber arrival', () => {
    const raw = generateBeeEvent({
      speaker: 'Landlord',
      summary: 'Plumber is confirmed for Friday at 10:00 AM.',
      confirmed: true,
      metric: 'appointment_confirmed',
    });
    expect(raw.speaker).toBe('Landlord');

    const ev = beeEventToEvidence(raw);
    expect(ev.source).toBe('bee_simulator');
    expect(ev.metric).toBe('appointment_confirmed');
    expect(ev.value.value).toBe(true);
    expect(ev.value.speaker).toBe('Landlord');
    expect(ev.value.summary).toContain('confirmed');
  });

  it('generates wearable conversation cancelling plumber arrival', () => {
    const raw = generateBeeEvent({
      speaker: 'Landlord',
      summary: 'The plumber had an emergency and cannot make it Friday. We need to reschedule.',
      confirmed: false,
      metric: 'appointment_confirmed',
    });

    const ev = beeEventToEvidence(raw);
    expect(ev.source).toBe('bee_simulator');
    expect(ev.value.value).toBe(false);
  });

  it('keeps conversation text as context without inventing a boolean', () => {
    const raw = generateBeeEvent({
      speaker: 'Doctor',
      summary: 'Doctor appointment cancelled due to doctor illness.',
    });
    const ev = beeEventToEvidence(raw);
    expect(ev.value).not.toHaveProperty('value');
  });
});

describe('Utility Billing Simulators', () => {
  it('generates utility bill evidence with cost and unit', () => {
    const ev = createUtilityBillEvidence(162);
    expect(ev.source).toBe('utility_bill');
    expect(ev.metric).toBe('total_cost');
    expect(ev.value.amount).toBe(162);
    expect(ev.unit).toBe('USD');
  });

  it('generates usage and tariff context evidence', () => {
    const usage = createUtilityUsageEvidence(-18);
    expect(usage.metric).toBe('energy_usage_change');
    expect(usage.value.percentage).toBe(-18);

    const tariff = createTariffRateEvidence(22);
    expect(tariff.metric).toBe('rate_change');
    expect(tariff.value.percentage).toBe(22);
  });
});

it('always marks simulator provenance, including utility evidence', () => {
  expect(generateRingEvent('package_detected').simulated).toBe(true);
  expect(generateBeeEvent({ summary: 'Fixture' }).simulated).toBe(true);
  expect(createUtilityBillEvidence(142).raw_data?.simulated).toBe(true);
});

it('makes distinct event IDs even when two utility observations happen in the same millisecond', () => {
  expect(createUtilityBillEvidence(142).external_event_id).not.toBe(createUtilityBillEvidence(142).external_event_id);
});

it('labels simulator evidence in normal evidence views without claiming a live account', async () => {
  const { evidenceSourceLabel } = await import('@/lib/presentation');
  expect(evidenceSourceLabel({ source: 'ring_simulator', raw_data: { simulated: true } })).toBe('Ring · SIMULATED');
  expect(evidenceSourceLabel({ source: 'utility_bill', raw_data: { simulated: true } })).toBe('Utility bill · SIMULATED');
  expect(evidenceSourceLabel({ source: 'ring', raw_data: {} })).toBe('Ring');
});
