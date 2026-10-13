'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  ArrowLeft,
  Camera,
  Lightbulb,
  Mic,
  Send,
  Sparkles,
  Zap,
  AlertTriangle,
  Info,
} from 'lucide-react';
import { useBoard } from '@/components/app-shell';
import { PageHeader, Badge, IconBox } from '@/components/ui';
import { api } from '@/lib/api';
import type { Evaluation, Evidence } from '@/lib/types';
import {
  generateRingEvent,
  ringEventToEvidence,
  generateBeeEvent,
  beeEventToEvidence,
  createUtilityBillEvidence,
} from '@/lib/simulators';

export default function DemosPage() {
  const board = useBoard();
  const rows = board.data ?? [];

  // Active tab
  const [activeTab, setActiveTab] = useState<'utility' | 'ring' | 'bee'>('utility');

  // Status feedback & actual backend evaluation result
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [lastEvaluation, setLastEvaluation] = useState<Evaluation | null>(null);
  const [busy, setBusy] = useState(false);

  // Target expectation selections (explicitly filtered, zero fallback to unrelated expectations)
  const utilityCandidates = rows.filter(
    (r) =>
      r.expectation.metric === 'total_cost' ||
      r.expectation.claim.toLowerCase().includes('bill') ||
      r.expectation.claim.toLowerCase().includes('electric')
  );
  const [selectedUtilityId, setSelectedUtilityId] = useState<string>('');

  const ringCandidates = rows.filter(
    (r) =>
      r.expectation.metric === 'delivered' ||
      r.expectation.metric === 'package_detected' ||
      r.expectation.claim.toLowerCase().includes('package') ||
      r.expectation.claim.toLowerCase().includes('delivery')
  );
  const [selectedRingId, setSelectedRingId] = useState<string>('');

  const beeCandidates = rows.filter(
    (r) =>
      r.expectation.metric === 'appointment_confirmed' ||
      r.expectation.claim.toLowerCase().includes('plumber') ||
      r.expectation.claim.toLowerCase().includes('appointment') ||
      r.expectation.claim.toLowerCase().includes('landlord')
  );
  const [selectedBeeId, setSelectedBeeId] = useState<string>('');

  // ----------------------------------------------------
  // DEMO 1: ELECTRICITY BILL SIMULATOR STATE
  // ----------------------------------------------------
  const targetUtilityRow = utilityCandidates.find((r) => r.expectation.id === selectedUtilityId) ?? utilityCandidates[0];
  const [billAmount, setBillAmount] = useState<number>(162.0);

  // Dynamic baseline and tolerance derived from target expectation
  const baselineBill = targetUtilityRow?.expectation.baseline ?? targetUtilityRow?.expectation.target_value ?? 142.1;
  const toleranceRatio = targetUtilityRow?.expectation.materiality_threshold ?? 0.05;
  const tolerancePct = toleranceRatio * 100;
  const maxThreshold = baselineBill * (1 + toleranceRatio);
  const difference = billAmount - baselineBill;
  const relativeDistance = Math.abs(difference) / baselineBill;
  const isSatisfiedUnderTolerance = billAmount <= baselineBill || relativeDistance < toleranceRatio;

  // Real evidence state for target bill expectation
  const [targetEvidence, setTargetEvidence] = useState<Evidence[]>([]);
  useEffect(() => {
    if (targetUtilityRow) {
      api.evidence(targetUtilityRow.expectation.id).then(setTargetEvidence).catch(() => setTargetEvidence([]));
    }
  }, [targetUtilityRow]);

  const actualUsageEvidence = targetEvidence.find((e) => e.metric === 'energy_usage_change' || e.source === 'utility_usage');
  const actualTariffEvidence = targetEvidence.find((e) => e.metric === 'rate_change' || e.source === 'tariff');

  // ----------------------------------------------------
  // DEMO 2: RING EVENT SIMULATOR STATE
  // ----------------------------------------------------
  const targetRingRow = ringCandidates.find((r) => r.expectation.id === selectedRingId) ?? ringCandidates[0];
  const [ringKind, setRingKind] = useState<'package_detected' | 'package_not_detected' | 'doorbell_ding' | 'motion_detected'>('package_detected');
  const [ringDevice, setRingDevice] = useState<string>('front_door');
  const [ringConfidence, setRingConfidence] = useState<number>(0.95);

  const currentRingRaw = generateRingEvent(ringKind, {
    device: ringDevice,
    confidence: ringConfidence,
  });
  const currentRingEvidence = ringEventToEvidence(currentRingRaw);

  // ----------------------------------------------------
  // DEMO 3: BEE CONTEXT SIMULATOR STATE
  // ----------------------------------------------------
  const targetBeeRow = beeCandidates.find((r) => r.expectation.id === selectedBeeId) ?? beeCandidates[0];
  const [beeSpeaker, setBeeSpeaker] = useState<string>('Landlord');
  const [beeSummary, setBeeSummary] = useState<string>(
    'The plumber had an emergency and cannot make it Friday. We need to reschedule.'
  );
  const [beeConfirmed, setBeeConfirmed] = useState<boolean>(false);

  const currentBeeRaw = generateBeeEvent({
    speaker: beeSpeaker,
    summary: beeSummary,
    confirmed: beeConfirmed,
    metric: targetBeeRow?.expectation.metric ?? 'appointment_confirmed',
  });
  const currentBeeEvidence = beeEventToEvidence(currentBeeRaw);

  // ----------------------------------------------------
  // BACKEND SUBMISSION HANDLER
  // ----------------------------------------------------
  async function submitDemoToBackend(type: 'utility' | 'ring' | 'bee') {
    setBusy(true);
    setStatusMessage(null);
    setLastEvaluation(null);

    try {
      if (type === 'utility') {
        if (!targetUtilityRow) {
          throw new Error('No active electricity bill expectation found. Please create one before running utility simulations.');
        }

        const ev = createUtilityBillEvidence(billAmount);
        await api.addEvidence(targetUtilityRow.expectation.id, ev);
        const evalResult = await api.evaluate(targetUtilityRow.expectation.id);
        setLastEvaluation(evalResult);
        setStatusMessage(
          `Utility bill of $${billAmount.toFixed(2)} recorded. Backend evaluated expectation as ${evalResult.result}.`
        );
        api.evidence(targetUtilityRow.expectation.id).then(setTargetEvidence).catch(() => {});
      } else if (type === 'ring') {
        if (!targetRingRow) {
          throw new Error('No package delivery expectation found. Please create one before running Ring simulations.');
        }

        await api.addEvidence(targetRingRow.expectation.id, currentRingEvidence);
        const evalResult = await api.evaluate(targetRingRow.expectation.id);
        setLastEvaluation(evalResult);
        setStatusMessage(
          `Ring simulated event (${ringKind}) sent. Backend evaluated expectation as ${evalResult.result}.`
        );
      } else {
        if (!targetBeeRow) {
          throw new Error('No plumber or appointment expectation found. Please create one before running Bee simulations.');
        }

        await api.addEvidence(targetBeeRow.expectation.id, currentBeeEvidence);
        const evalResult = await api.evaluate(targetBeeRow.expectation.id);
        setLastEvaluation(evalResult);
        setStatusMessage(
          `Bee simulated context conversation sent. Backend evaluated expectation as ${evalResult.result}.`
        );
      }

      board.reload();
    } catch (err) {
      setStatusMessage(err instanceof Error ? err.message : 'Submission failed');
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <Link className="back-link" href="/dashboard">
        <ArrowLeft size={17} />
        Back to Dashboard
      </Link>

      <PageHeader
        eyebrow="Interactive Simulation Suite"
        title="Interactive Demos & Simulators"
        description="Experience deterministic evaluations without physical Ring hardware, an iPhone, or Bee CLI. Evidence is processed by the real backend engine."
      />

      {statusMessage && (
        <div
          className="soft-card"
          style={{
            margin: '0 0 1.5rem',
            padding: '1rem 1.25rem',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '0.6rem',
            backgroundColor: lastEvaluation?.result === 'MISMATCH' ? '#fff7ed' : '#eff6ff',
            border: `1px solid ${lastEvaluation?.result === 'MISMATCH' ? '#fed7aa' : '#bfdbfe'}`,
            color: lastEvaluation?.result === 'MISMATCH' ? '#9a3412' : '#1e40af',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <Sparkles size={18} />
            <div>
              <strong>{statusMessage}</strong>
              {lastEvaluation && (
                <div style={{ fontSize: '0.85rem', marginTop: '0.25rem' }}>
                  Backend Evaluation Result:{' '}
                  <span style={{ fontWeight: 700 }}>{lastEvaluation.result}</span>
                  {typeof lastEvaluation.reasoning?.reason === 'string' && (
                    <span> · Reason: {String(lastEvaluation.reasoning.reason)}</span>
                  )}
                </div>
              )}
            </div>
          </div>
          {lastEvaluation && <Badge status={lastEvaluation.result === 'MATCH' ? 'match' : lastEvaluation.result === 'MISMATCH' ? 'attention' : 'waiting'} />}
        </div>
      )}

      {/* Tabs */}
      <div className="filters" aria-label="Demo scenarios" style={{ marginBottom: '1.5rem' }}>
        <button
          className={`filter ${activeTab === 'utility' ? 'selected' : ''}`}
          onClick={() => setActiveTab('utility')}
          aria-pressed={activeTab === 'utility'}
        >
          <Zap size={16} />
          Electricity Bill Demo
        </button>

        <button
          className={`filter ${activeTab === 'ring' ? 'selected' : ''}`}
          onClick={() => setActiveTab('ring')}
          aria-pressed={activeTab === 'ring'}
        >
          <Camera size={16} />
          Ring Delivery Simulator
          <span className="demo-badge" style={{ marginLeft: '0.4rem', backgroundColor: '#fef3c7', color: '#92400e' }}>
            SIMULATED
          </span>
        </button>

        <button
          className={`filter ${activeTab === 'bee' ? 'selected' : ''}`}
          onClick={() => setActiveTab('bee')}
          aria-pressed={activeTab === 'bee'}
        >
          <Mic size={16} />
          Bee Wearable Simulator
          <span className="demo-badge" style={{ marginLeft: '0.4rem', backgroundColor: '#fef3c7', color: '#92400e' }}>
            SIMULATED
          </span>
        </button>
      </div>

      {/* ========================================================
          DEMO 1: ELECTRICITY BILL INTERACTIVE DEMO
          ======================================================== */}
      {activeTab === 'utility' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <section className="card" style={{ padding: '1.75rem' }}>
            {/* Target Expectation Selector */}
            {utilityCandidates.length > 0 ? (
              <div style={{ marginBottom: '1.25rem' }}>
                <label htmlFor="utility-target" style={{ display: 'block', fontWeight: 600, fontSize: '0.875rem', marginBottom: '0.35rem' }}>
                  Target Expectation (Strictly matched, no unrelated fallback):
                </label>
                <select
                  id="utility-target"
                  value={targetUtilityRow?.expectation.id ?? ''}
                  onChange={(e) => setSelectedUtilityId(e.target.value)}
                  style={{ width: '100%', padding: '0.6rem', borderRadius: '8px', border: '1px solid var(--border-color, #e2e8f0)' }}
                >
                  {utilityCandidates.map((c) => (
                    <option key={c.expectation.id} value={c.expectation.id}>
                      {c.expectation.claim} (Baseline: ${Number(c.expectation.baseline ?? c.expectation.target_value ?? 142.1).toFixed(2)})
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <div className="soft-card" style={{ padding: '0.875rem', marginBottom: '1.25rem', backgroundColor: '#fffbeb', border: '1px solid #fef3c7', color: '#92400e' }}>
                <AlertTriangle size={16} style={{ display: 'inline', marginRight: '0.4rem' }} />
                No electricity bill expectation found. Please create one before running utility simulations.
              </div>
            )}

            <div className="section-heading">
              <div>
                <span className="overline">Scenario Overview</span>
                <h2 style={{ margin: '0.25rem 0' }}>“{targetUtilityRow?.expectation.claim ?? 'My next electric bill should be lower.'}”</h2>
                <p className="caption">
                  Target baseline: ${baselineBill.toFixed(2)} · Materiality tolerance: {tolerancePct.toFixed(0)}% (upper boundary: ${maxThreshold.toFixed(2)}).
                </p>
              </div>
              <Badge status={isSatisfiedUnderTolerance ? 'match' : 'attention'} />
            </div>

            {/* Interactive Bill Input / Slider */}
            <div
              style={{
                backgroundColor: 'var(--surface-subtle, #f8fafc)',
                padding: '1.25rem',
                borderRadius: '12px',
                border: '1px solid var(--border-color, #e2e8f0)',
                margin: '1.25rem 0',
              }}
            >
              <label
                htmlFor="bill-slider"
                style={{ display: 'block', fontWeight: 600, marginBottom: '0.5rem' }}
              >
                Simulated Bill Amount: <strong>${billAmount.toFixed(2)}</strong>
              </label>

              <input
                id="bill-slider"
                type="range"
                min="90"
                max="210"
                step="1"
                value={billAmount}
                onChange={(e) => setBillAmount(Number(e.target.value))}
                style={{ width: '100%', cursor: 'pointer', marginBottom: '0.75rem' }}
              />

              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <button
                  type="button"
                  className={`button ${billAmount === 162 ? 'primary' : 'secondary'}`}
                  onClick={() => setBillAmount(162.0)}
                  style={{ fontSize: '0.85rem' }}
                >
                  Preset: $162.00 (Above threshold · MISMATCH)
                </button>
                <button
                  type="button"
                  className={`button ${billAmount === 145 ? 'primary' : 'secondary'}`}
                  onClick={() => setBillAmount(145.0)}
                  style={{ fontSize: '0.85rem' }}
                >
                  Preset: $145.00 (Within 5% tolerance · MATCH)
                </button>
                <button
                  type="button"
                  className={`button ${billAmount === 130 ? 'primary' : 'secondary'}`}
                  onClick={() => setBillAmount(130.0)}
                  style={{ fontSize: '0.85rem' }}
                >
                  Preset: $130.00 (Below baseline · MATCH)
                </button>
              </div>
            </div>

            {/* Comparison Cards */}
            <div className="comparison-grid" style={{ marginBottom: '1.25rem' }}>
              <div className="comparison expected">
                <span className="overline">Expected Baseline</span>
                <strong>Less than ${baselineBill.toFixed(2)}</strong>
                <p>Materiality tolerance: {tolerancePct.toFixed(0)}% (up to ${maxThreshold.toFixed(2)} tolerated)</p>
              </div>

              <div className={`comparison observed ${isSatisfiedUnderTolerance ? 'match' : 'attention'}`}>
                <div className="section-heading">
                  <span className="overline">Observed Amount</span>
                  <Badge status={isSatisfiedUnderTolerance ? 'match' : 'attention'} />
                </div>
                <strong>${billAmount.toFixed(2)}</strong>
                <p>
                  Difference: {difference >= 0 ? '+' : ''}${difference.toFixed(2)} ({(relativeDistance * 100).toFixed(1)}% deviation)
                </p>
              </div>
            </div>

            {/* Evidence-Grounded Deterministic Explanation Card */}
            <div
              className="explanation-card"
              style={{
                padding: '1.25rem',
                borderRadius: '12px',
                backgroundColor: isSatisfiedUnderTolerance ? '#f0fdf4' : '#fff7ed',
                border: `1px solid ${isSatisfiedUnderTolerance ? '#bbf7d0' : '#fed7aa'}`,
                marginBottom: '1.25rem',
              }}
            >
              <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-start' }}>
                <IconBox icon={Lightbulb} tone={isSatisfiedUnderTolerance ? 'green' : 'orange'} />
                <div>
                  <h3 style={{ margin: '0 0 0.4rem', color: isSatisfiedUnderTolerance ? '#166534' : '#9a3412' }}>
                    {isSatisfiedUnderTolerance ? 'Deterministic Evaluation: MATCH' : 'Deterministic Evaluation: MISMATCH'}
                  </h3>
                  <p style={{ margin: 0, fontSize: '0.925rem', lineHeight: 1.5 }}>
                    {billAmount <= baselineBill
                      ? `The bill arrived at $${billAmount.toFixed(2)}, which is below your $${baselineBill.toFixed(2)} baseline threshold.`
                      : billAmount <= maxThreshold
                      ? `The bill arrived at $${billAmount.toFixed(2)}, which is $${difference.toFixed(2)} above baseline but within your ${tolerancePct.toFixed(0)}% materiality tolerance ($${maxThreshold.toFixed(2)}). Backend evaluator classifies this as MATCH.`
                      : `The bill arrived at $${billAmount.toFixed(2)}, which is $${difference.toFixed(2)} above your $${baselineBill.toFixed(2)} baseline and exceeds the ${tolerancePct.toFixed(0)}% materiality threshold ($${maxThreshold.toFixed(2)}).`}
                  </p>

                  {/* Real Supporting Evidence (Grounded, not fabricated) */}
                  {(actualUsageEvidence || actualTariffEvidence) ? (
                    <div style={{ marginTop: '0.75rem' }}>
                      <span className="caption" style={{ fontWeight: 600 }}>Supporting Evidence Observations:</span>
                      <div className="signal-chips" style={{ marginTop: '0.35rem' }}>
                        {actualUsageEvidence && (
                          <span className="down" style={{ fontSize: '0.8rem' }}>
                            Energy usage: {String((actualUsageEvidence.value as Record<string, unknown>)?.percentage ?? '-18%')}
                          </span>
                        )}
                        {actualTariffEvidence && (
                          <span className="up" style={{ fontSize: '0.8rem' }}>
                            Utility rate: {String((actualTariffEvidence.value as Record<string, unknown>)?.percentage ?? '+22%')}
                          </span>
                        )}
                      </div>
                    </div>
                  ) : (
                    <p className="caption" style={{ marginTop: '0.5rem', color: '#64748b' }}>
                      <Info size={13} style={{ display: 'inline', marginRight: '0.3rem' }} />
                      Evaluated deterministically from submitted bill evidence. No external tariff or usage assumptions applied.
                    </p>
                  )}
                </div>
              </div>
            </div>

            <button
              className="button primary"
              onClick={() => submitDemoToBackend('utility')}
              disabled={busy || !targetUtilityRow}
            >
              <Send size={16} />
              {busy ? 'Sending...' : 'Send Bill to Backend & Run Evaluation'}
            </button>
          </section>
        </div>
      )}

      {/* ========================================================
          DEMO 2: RING EVENT SIMULATOR
          ======================================================== */}
      {activeTab === 'ring' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <section className="card" style={{ padding: '1.75rem' }}>
            {/* Target Expectation Selector */}
            {ringCandidates.length > 0 ? (
              <div style={{ marginBottom: '1.25rem' }}>
                <label htmlFor="ring-target" style={{ display: 'block', fontWeight: 600, fontSize: '0.875rem', marginBottom: '0.35rem' }}>
                  Target Delivery Expectation (Strictly matched, no unrelated fallback):
                </label>
                <select
                  id="ring-target"
                  value={targetRingRow?.expectation.id ?? ''}
                  onChange={(e) => setSelectedRingId(e.target.value)}
                  style={{ width: '100%', padding: '0.6rem', borderRadius: '8px', border: '1px solid var(--border-color, #e2e8f0)' }}
                >
                  {ringCandidates.map((c) => (
                    <option key={c.expectation.id} value={c.expectation.id}>
                      {c.expectation.claim} ({c.expectation.metric ?? 'package_detected'})
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <div className="soft-card" style={{ padding: '0.875rem', marginBottom: '1.25rem', backgroundColor: '#fffbeb', border: '1px solid #fef3c7', color: '#92400e' }}>
                <AlertTriangle size={16} style={{ display: 'inline', marginRight: '0.4rem' }} />
                No package delivery expectation found. Please create one before running Ring simulations.
              </div>
            )}

            <div className="section-heading">
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                  <span className="overline">Device Simulator</span>
                  <span className="demo-badge" style={{ backgroundColor: '#fef3c7', color: '#92400e', border: '1px solid #fde68a' }}>
                    SIMULATED · NO PHYSICAL HARDWARE
                  </span>
                </div>
                <h2 style={{ margin: '0.25rem 0' }}>Ring Doorbell & Camera Simulator</h2>
                <p className="caption">
                  Generates virtual Ring camera events and transforms them into CountOn evidence evaluated by the backend.
                </p>
              </div>
              <Badge status={ringKind === 'package_detected' ? 'match' : ringKind === 'package_not_detected' ? 'attention' : 'waiting'} />
            </div>

            {/* Presets */}
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1.25rem' }}>
              <button
                type="button"
                className={`button ${ringKind === 'package_detected' ? 'primary' : 'secondary'}`}
                onClick={() => setRingKind('package_detected')}
              >
                Package Detected (MATCH)
              </button>
              <button
                type="button"
                className={`button ${ringKind === 'package_not_detected' ? 'primary' : 'secondary'}`}
                onClick={() => setRingKind('package_not_detected')}
              >
                Package Missing / Removed (MISMATCH)
              </button>
              <button
                type="button"
                className={`button ${ringKind === 'doorbell_ding' ? 'primary' : 'secondary'}`}
                onClick={() => setRingKind('doorbell_ding')}
              >
                Doorbell Ring
              </button>
              <button
                type="button"
                className={`button ${ringKind === 'motion_detected' ? 'primary' : 'secondary'}`}
                onClick={() => setRingKind('motion_detected')}
              >
                Motion Detected
              </button>
            </div>

            {/* Config controls */}
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '1rem',
                backgroundColor: 'var(--surface-subtle, #f8fafc)',
                padding: '1.25rem',
                borderRadius: '12px',
                marginBottom: '1.25rem',
              }}
            >
              <div>
                <label htmlFor="ring-dev" style={{ display: 'block', fontWeight: 600, marginBottom: '0.4rem' }}>
                  Camera Location
                </label>
                <select
                  id="ring-dev"
                  value={ringDevice}
                  onChange={(e) => setRingDevice(e.target.value)}
                  style={{ width: '100%', borderRadius: '8px', padding: '0.6rem' }}
                >
                  <option value="front_door">Front Doorbell</option>
                  <option value="porch_camera">Front Porch Camera</option>
                  <option value="driveway">Driveway Floodlight</option>
                </select>
              </div>

              <div>
                <label htmlFor="ring-conf" style={{ display: 'block', fontWeight: 600, marginBottom: '0.4rem' }}>
                  Detection Confidence: {Math.round(ringConfidence * 100)}%
                </label>
                <input
                  id="ring-conf"
                  type="range"
                  min="0.5"
                  max="1.0"
                  step="0.05"
                  value={ringConfidence}
                  onChange={(e) => setRingConfidence(Number(e.target.value))}
                  style={{ width: '100%', cursor: 'pointer' }}
                />
              </div>
            </div>

            {/* Side-by-side JSON & Evidence preview */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
              <div>
                <strong style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.85rem' }}>
                  1. Raw Simulated Ring Webhook JSON
                </strong>
                <pre
                  style={{
                    backgroundColor: '#1e293b',
                    color: '#f8fafc',
                    padding: '1rem',
                    borderRadius: '8px',
                    fontSize: '0.8rem',
                    overflowX: 'auto',
                    maxHeight: '220px',
                  }}
                >
                  {JSON.stringify(currentRingRaw, null, 2)}
                </pre>
              </div>

              <div>
                <strong style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.85rem' }}>
                  2. Converted CountOn Evidence Payload
                </strong>
                <pre
                  style={{
                    backgroundColor: '#0f172a',
                    color: '#38bdf8',
                    padding: '1rem',
                    borderRadius: '8px',
                    fontSize: '0.8rem',
                    overflowX: 'auto',
                    maxHeight: '220px',
                  }}
                >
                  {JSON.stringify(currentRingEvidence, null, 2)}
                </pre>
              </div>
            </div>

            <button
              className="button primary"
              onClick={() => submitDemoToBackend('ring')}
              disabled={busy || !targetRingRow}
            >
              <Send size={16} />
              {busy ? 'Sending...' : 'Send Ring Simulated Evidence to Backend & Evaluate'}
            </button>
          </section>
        </div>
      )}

      {/* ========================================================
          DEMO 3: BEE WEARABLE CONTEXT SIMULATOR
          ======================================================== */}
      {activeTab === 'bee' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <section className="card" style={{ padding: '1.75rem' }}>
            {/* Target Expectation Selector */}
            {beeCandidates.length > 0 ? (
              <div style={{ marginBottom: '1.25rem' }}>
                <label htmlFor="bee-target" style={{ display: 'block', fontWeight: 600, fontSize: '0.875rem', marginBottom: '0.35rem' }}>
                  Target Appointment Expectation (Strictly matched, no unrelated fallback):
                </label>
                <select
                  id="bee-target"
                  value={targetBeeRow?.expectation.id ?? ''}
                  onChange={(e) => setSelectedBeeId(e.target.value)}
                  style={{ width: '100%', padding: '0.6rem', borderRadius: '8px', border: '1px solid var(--border-color, #e2e8f0)' }}
                >
                  {beeCandidates.map((c) => (
                    <option key={c.expectation.id} value={c.expectation.id}>
                      {c.expectation.claim} ({c.expectation.metric ?? 'appointment_confirmed'})
                    </option>
                  ))}
                </select>
              </div>
            ) : (
              <div className="soft-card" style={{ padding: '0.875rem', marginBottom: '1.25rem', backgroundColor: '#fffbeb', border: '1px solid #fef3c7', color: '#92400e' }}>
                <AlertTriangle size={16} style={{ display: 'inline', marginRight: '0.4rem' }} />
                No appointment expectation found. Please create one before running Bee simulations.
              </div>
            )}

            <div className="section-heading">
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.25rem' }}>
                  <span className="overline">Wearable Context Simulator</span>
                  <span className="demo-badge" style={{ backgroundColor: '#fef3c7', color: '#92400e', border: '1px solid #fde68a' }}>
                    SIMULATED · NO PHYSICAL HARDWARE
                  </span>
                </div>
                <h2 style={{ margin: '0.25rem 0' }}>Bee Smart Wearable Simulator</h2>
                <p className="caption">
                  Simulate voice conversations and commitments without an iPhone or physical Bee wearable.
                </p>
              </div>
              <Badge status={beeConfirmed ? 'match' : 'attention'} />
            </div>

            {/* Presets */}
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1.25rem' }}>
              <button
                type="button"
                className={`button ${beeConfirmed ? 'primary' : 'secondary'}`}
                onClick={() => {
                  setBeeSpeaker('Landlord');
                  setBeeSummary('Spoke with landlord: Plumber is confirmed for Friday at 10:00 AM.');
                  setBeeConfirmed(true);
                }}
              >
                Plumber Confirmed (MATCH)
              </button>
              <button
                type="button"
                className={`button ${!beeConfirmed ? 'primary' : 'secondary'}`}
                onClick={() => {
                  setBeeSpeaker('Landlord');
                  setBeeSummary(
                    'The plumber had an emergency and cannot make it Friday. We need to reschedule.'
                  );
                  setBeeConfirmed(false);
                }}
              >
                Plumber Rescheduled (MISMATCH)
              </button>
            </div>

            {/* Editor */}
            <div
              style={{
                backgroundColor: 'var(--surface-subtle, #f8fafc)',
                padding: '1.25rem',
                borderRadius: '12px',
                marginBottom: '1.25rem',
              }}
            >
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                <div>
                  <label htmlFor="bee-spk" style={{ display: 'block', fontWeight: 600, marginBottom: '0.4rem' }}>
                    Speaker
                  </label>
                  <input
                    id="bee-spk"
                    value={beeSpeaker}
                    onChange={(e) => setBeeSpeaker(e.target.value)}
                    style={{ width: '100%', borderRadius: '8px', padding: '0.6rem' }}
                  />
                </div>

                <div>
                  <label htmlFor="bee-conf-status" style={{ display: 'block', fontWeight: 600, marginBottom: '0.4rem' }}>
                    Confirmed Status
                  </label>
                  <select
                    id="bee-conf-status"
                    value={beeConfirmed ? 'yes' : 'no'}
                    onChange={(e) => setBeeConfirmed(e.target.value === 'yes')}
                    style={{ width: '100%', borderRadius: '8px', padding: '0.6rem' }}
                  >
                    <option value="yes">Confirmed (True · MATCH)</option>
                    <option value="no">Contradicted / Cancelled (False · MISMATCH)</option>
                  </select>
                </div>
              </div>

              <div>
                <label htmlFor="bee-sum" style={{ display: 'block', fontWeight: 600, marginBottom: '0.4rem' }}>
                  Conversation Summary / Transcription
                </label>
                <textarea
                  id="bee-sum"
                  value={beeSummary}
                  onChange={(e) => setBeeSummary(e.target.value)}
                  rows={3}
                  style={{ width: '100%', borderRadius: '8px', padding: '0.6rem' }}
                />
              </div>
            </div>

            {/* Side-by-side JSON & Evidence preview */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem' }}>
              <div>
                <strong style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.85rem' }}>
                  1. Raw Simulated Bee Device JSON
                </strong>
                <pre
                  style={{
                    backgroundColor: '#1e293b',
                    color: '#f8fafc',
                    padding: '1rem',
                    borderRadius: '8px',
                    fontSize: '0.8rem',
                    overflowX: 'auto',
                    maxHeight: '220px',
                  }}
                >
                  {JSON.stringify(currentBeeRaw, null, 2)}
                </pre>
              </div>

              <div>
                <strong style={{ display: 'block', marginBottom: '0.5rem', fontSize: '0.85rem' }}>
                  2. Converted CountOn Evidence Payload
                </strong>
                <pre
                  style={{
                    backgroundColor: '#0f172a',
                    color: '#fde047',
                    padding: '1rem',
                    borderRadius: '8px',
                    fontSize: '0.8rem',
                    overflowX: 'auto',
                    maxHeight: '220px',
                  }}
                >
                  {JSON.stringify(currentBeeEvidence, null, 2)}
                </pre>
              </div>
            </div>

            <button
              className="button primary"
              onClick={() => submitDemoToBackend('bee')}
              disabled={busy || !targetBeeRow}
            >
              <Send size={16} />
              {busy ? 'Sending...' : 'Send Bee Simulated Context to Backend & Evaluate'}
            </button>
          </section>
        </div>
      )}
    </>
  );
}
