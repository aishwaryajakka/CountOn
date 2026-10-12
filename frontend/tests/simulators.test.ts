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
    expect(ev.source).toBe('ring');
    expect(ev.metric).toBe('package_detected');
    expect(ev.value.value).toBe(true);
    expect(ev.value.detected).toBe(true);
    expect(ev.confidence).toBe(0.95);
  });

  it('generates a package not detected event and converts to MISMATCH-compatible evidence', () => {
    const raw = generateRingEvent('package_not_detected');
    const ev = ringEventToEvidence(raw);
    expect(ev.source).toBe('ring');
    expect(ev.value.value).toBe(false);
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
    expect(ev.source).toBe('bee');
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
    expect(ev.source).toBe('bee');
    expect(ev.value.value).toBe(false);
  });

  it('infers cancellation from keywords when confirmation not explicitly provided', () => {
    const raw = generateBeeEvent({
      speaker: 'Doctor',
      summary: 'Doctor appointment cancelled due to doctor illness.',
    });
    const ev = beeEventToEvidence(raw);
    expect(ev.value.value).toBe(false);
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
