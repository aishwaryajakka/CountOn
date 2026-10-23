'use client';

import { useState } from 'react';
import Link from 'next/link';
import {
  ArrowLeft,
  Camera,
  Lightbulb,
  Mic,
  Send,
  Sparkles,
  Zap,
} from 'lucide-react';
import { useBoard } from '@/components/app-shell';
import { PageHeader, Badge, IconBox } from '@/components/ui';
import { api } from '@/lib/api';
import type { Evaluation } from '@/lib/types';
import {
  generateRingEvent,
  ringEventToEvidence,
  generateBeeEvent,
  beeEventToEvidence,
  createUtilityBillEvidence,
  simulatorTargets,
  simulatorTarget,
} from '@/lib/simulators';

export default function DemosPage() {
  const board = useBoard();
  const rows = board.data ?? [];

  // Active tab
  const [activeTab, setActiveTab] = useState<'utility' | 'ring' | 'bee'>('utility');

  // Status feedback
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [targetId, setTargetId] = useState('');
  const [evaluations, setEvaluations] = useState<Partial<Record<'utility' | 'ring' | 'bee', Evaluation>>>({});
  const targets = simulatorTargets(rows, activeTab);
  const selectedTarget = targets.find(exp => exp.id === targetId) ?? (targets.length === 1 ? targets[0] : undefined);

  // ----------------------------------------------------
  // DEMO 1: ELECTRICITY BILL SIMULATOR STATE
  // ----------------------------------------------------
  const [billAmount, setBillAmount] = useState<number>(162.0);
  const baselineBill = 142.1;
  const billResult = evaluations.utility?.result;

  // ----------------------------------------------------
  // DEMO 2: RING EVENT SIMULATOR STATE
  // ----------------------------------------------------
  const [ringKind, setRingKind] = useState<'package_detected' | 'package_not_detected' | 'doorbell_ding' | 'motion_detected'>('package_detected');
  const [ringDevice, setRingDevice] = useState<string>('front_door');
  const [ringConfidence, setRingConfidence] = useState<number>(0.95);

  const currentRingRaw = generateRingEvent(ringKind, {
    ...(ringKind.startsWith('package_') ? { metric: selectedTarget?.metric ?? undefined } : {}),
    device: ringDevice,
    confidence: ringConfidence,
  });
  const currentRingEvidence = ringEventToEvidence(currentRingRaw);
  const ringResult = evaluations.ring?.result;

  // ----------------------------------------------------
  // DEMO 3: BEE CONTEXT SIMULATOR STATE
  // ----------------------------------------------------
  const [beeSpeaker, setBeeSpeaker] = useState<string>('Landlord');
  const [beeSummary, setBeeSummary] = useState<string>(
    'The plumber had an emergency and cannot make it Friday. We need to reschedule.'
  );
  const [beeConfirmed, setBeeConfirmed] = useState<boolean>(false);

  const currentBeeRaw = generateBeeEvent({
    speaker: beeSpeaker,
    summary: beeSummary,
    confirmed: beeConfirmed,
    metric: 'appointment_confirmed',
  });
  const currentBeeEvidence = beeEventToEvidence(currentBeeRaw);
  const beeResult = evaluations.bee?.result;

  // ----------------------------------------------------
  // BACKEND SUBMISSION HANDLER
  // ----------------------------------------------------
  async function submitDemoToBackend(type: 'utility' | 'ring' | 'bee') {
    setBusy(true);
    setStatusMessage(null);

    try {
      const target = simulatorTarget(rows, type, targetId);
      let evaluation: Evaluation;
      if (type === 'utility') {
        const evidence = createUtilityBillEvidence(billAmount);
        await api.addEvidence(target.id, evidence);
        evaluation = await api.evaluate(target.id, `simulation:${evidence.external_event_id}`);
      } else if (type === 'ring') {
        evaluation = (await api.simulateRing(target.id, { ...currentRingRaw, ...(ringKind.startsWith('package_') ? { metric: target.metric ?? undefined } : {}) })).evaluation;
      } else {
        evaluation = (await api.simulateBee(target.id, { ...currentBeeRaw, metric: target.metric ?? undefined })).evaluation;
      }
      setEvaluations(previous => ({ ...previous, [type]: evaluation }));
      setStatusMessage(`SIMULATED ${type} evidence recorded · Backend evaluation: ${evaluation.result}`);

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
        description="SIMULATED evidence sent to your authenticated backend. Ring remains simulated; optional Bee CLI imports are managed under Connected Accounts."
      />

      {statusMessage && (
        <div
          className="soft-card"
          style={{
            margin: '0 0 1.5rem',
            padding: '0.875rem 1.25rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.6rem',
            backgroundColor: '#eff6ff',
            border: '1px solid #bfdbfe',
            color: '#1e40af',
          }}
        >
          <Sparkles size={18} />
          <span>{statusMessage}</span>
        </div>
      )}

      {/* Tabs */}
      <div className="filters" aria-label="Demo scenarios" style={{ marginBottom: '1.5rem' }}>
        <button
          className={`filter ${activeTab === 'utility' ? 'selected' : ''}`}
          onClick={() => { setActiveTab('utility'); setTargetId(''); }}
          aria-pressed={activeTab === 'utility'}
        >
          <Zap size={16} />
          Electricity Bill Demo
        </button>

        <button
          className={`filter ${activeTab === 'ring' ? 'selected' : ''}`}
          onClick={() => { setActiveTab('ring'); setTargetId(''); }}
          aria-pressed={activeTab === 'ring'}
        >
          <Camera size={16} />
          Ring Delivery Simulator
        </button>

        <button
          className={`filter ${activeTab === 'bee' ? 'selected' : ''}`}
          onClick={() => { setActiveTab('bee'); setTargetId(''); }}
          aria-pressed={activeTab === 'bee'}
        >
          <Mic size={16} />
          Bee Wearable Simulator
        </button>
      </div>

      <label>Expectation receiving SIMULATED evidence<select value={targetId || (targets.length === 1 ? targets[0].id : '')} onChange={event => setTargetId(event.target.value)}><option value="">Select a compatible expectation</option>{targets.map(exp => <option key={exp.id} value={exp.id}>{exp.claim}</option>)}</select></label>
      <p className="caption">Badges show the last saved backend evaluation for each simulator. Only the backend decides the outcome. No package detection does not prove missed delivery. Simulations persist as tagged evidence.</p>

      {/* ========================================================
          DEMO 1: ELECTRICITY BILL INTERACTIVE DEMO
          ======================================================== */}
      {activeTab === 'utility' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          <section className="card" style={{ padding: '1.75rem' }}>
            <div className="section-heading">
              <div>
                <span className="overline">Scenario Overview</span>
                <h2 style={{ margin: '0.25rem 0' }}>“My next electric bill should be lower.”</h2>
                <p className="caption">
                  Target baseline: Less than $142.10 (with 5% materiality tolerance).
                </p>
              </div>
              {billResult ? <Badge status={billResult === 'MISMATCH' ? 'attention' : billResult === 'MATCH' ? 'match' : 'waiting'} /> : <span>Not evaluated yet</span>}
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
                htmlFor="bill-input"
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
                  Preset: $162.00
                </button>
                <button
                  type="button"
                  className={`button ${billAmount === 130 ? 'primary' : 'secondary'}`}
                  onClick={() => setBillAmount(130.0)}
                  style={{ fontSize: '0.85rem' }}
                >
                  Preset: $130.00
                </button>
              </div>
            </div>

            {/* Comparison Cards */}
            <div className="comparison-grid" style={{ marginBottom: '1.25rem' }}>
              <div className="comparison expected">
                <span className="overline">Expected Threshold</span>
                <strong>Less than $142.10</strong>
                <p>Sample preview baseline; use the selected expectation’s actual conditions.</p>
              </div>

              <div className={`comparison observed ${billResult === 'MISMATCH' ? 'attention' : billResult === 'MATCH' ? 'match' : ''}`}>
                <div className="section-heading">
                  <span className="overline">Simulated Input Amount</span>
                  {billResult ? <Badge status={billResult === 'MISMATCH' ? 'attention' : billResult === 'MATCH' ? 'match' : 'waiting'} /> : <span>Not evaluated yet</span>}
                </div>
                <strong>${billAmount.toFixed(2)}</strong>
                <p>
                  Difference: {billAmount > baselineBill ? '+' : ''}
                  ${(billAmount - baselineBill).toFixed(2)}
                </p>
              </div>
            </div>

            <div className="soft-card"><IconBox icon={Lightbulb} tone="blue" /><p>This is an input preview, using a sample baseline of $142.10. The selected expectation’s saved conditions determine the backend evaluation. No usage or tariff explanation is inferred.</p>{billResult && <p>Last backend evaluation: {billResult}</p>}</div>

            <button
              className="button primary"
              onClick={() => submitDemoToBackend('utility')}
              disabled={busy || !targets.length || (targets.length > 1 && !targetId)}
            >
              <Send size={16} />
              {busy ? 'Sending...' : 'Send Bill to CountOn Backend & Evaluate'}
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
            <div className="section-heading">
              <div>
                <span className="overline">Device Simulator</span>
                <h2 style={{ margin: '0.25rem 0' }}>Ring Doorbell & Camera Simulator</h2>
                <p className="caption">
                  No physical Ring camera required. Generates raw camera events and converts them into CountOn evidence.
                </p>
              </div>
              {ringResult ? <Badge status={ringResult === 'MATCH' ? 'match' : ringResult === 'MISMATCH' ? 'attention' : 'waiting'} /> : <span>Not evaluated yet</span>}
            </div>

            {/* Presets */}
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1.25rem' }}>
              <button
                type="button"
                className={`button ${ringKind === 'package_detected' ? 'primary' : 'secondary'}`}
                onClick={() => setRingKind('package_detected')}
              >
                Package Detected
              </button>
              <button
                type="button"
                className={`button ${ringKind === 'package_not_detected' ? 'primary' : 'secondary'}`}
                onClick={() => setRingKind('package_not_detected')}
              >
                No Package Detected
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
              disabled={busy || !targets.length || (targets.length > 1 && !targetId)}
            >
              <Send size={16} />
              {busy ? 'Sending...' : 'Send Ring Evidence to Backend & Evaluate'}
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
            <div className="section-heading">
              <div>
                <span className="overline">Wearable Context Simulator</span>
                <h2 style={{ margin: '0.25rem 0' }}>Bee Smart Wearable Simulator</h2>
                <p className="caption">
                  Simulate voice conversations and commitments without an iPhone or Bee CLI.
                </p>
              </div>
              {beeResult ? <Badge status={beeResult === 'MATCH' ? 'match' : beeResult === 'MISMATCH' ? 'attention' : 'waiting'} /> : <span>Not evaluated yet</span>}
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
                Plumber Confirmed
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
                Plumber Rescheduled
              </button>
              <button
                type="button"
                className="button secondary"
                onClick={() => {
                  setBeeSpeaker('Sarah');
                  setBeeSummary('Sarah confirmed she will send the updated design document tomorrow morning.');
                  setBeeConfirmed(true);
                }}
              >
                Design Document Promise
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
                    <option value="yes">Confirmed (True)</option>
                    <option value="no">Contradicted / Cancelled (False)</option>
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

            <p className="caption">This is a simulated conversation with an explicitly selected confirmation flag. It is not a live wearable observation or an explanation of causation.</p>

            <button
              className="button primary"
              onClick={() => submitDemoToBackend('bee')}
              disabled={busy || !targets.length || (targets.length > 1 && !targetId)}
            >
              <Send size={16} />
              {busy ? 'Sending...' : 'Send Bee Context to Backend & Evaluate'}
            </button>
          </section>
        </div>
      )}
    </>
  );
}
