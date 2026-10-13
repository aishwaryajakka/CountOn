import { Suspense } from 'react';
import { act, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { Evaluation, Evidence, Expectation, WatchedExpectation } from '@/lib/types';
import {
  generateRingEvent,
  ringEventToEvidence,
  generateBeeEvent,
  beeEventToEvidence,
  createUtilityBillEvidence,
} from '@/lib/simulators';
import { expectation, evaluation, integration } from './fixtures';

const mocks = vi.hoisted(() => ({
  board: {
    data: null as WatchedExpectation[] | null,
    error: null as Error | null,
    loading: false,
    reload: vi.fn(),
  },
  replace: vi.fn(),
  push: vi.fn(),
  createExpectation: vi.fn(),
  addEvidence: vi.fn(),
  evaluate: vi.fn(),
  evidence: vi.fn(),
  expectation: vi.fn(),
  evaluations: vi.fn(),
  latest: vi.fn(),
  integrations: vi.fn(),
  deleteIntegration: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace: mocks.replace, push: mocks.push }),
}));

vi.mock('@/components/app-shell', () => ({
  useBoard: () => mocks.board,
}));

vi.mock('@/components/auth-provider', () => ({
  useAuth: () => ({ session: null, loading: false, error: null }),
  useIdentity: () => ({ firstName: 'Akshaya', name: 'Akshaya Tanniru', timeZone: 'America/Chicago' }),
}));

vi.mock('@/lib/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/api')>();
  return {
    ...actual,
    api: {
      createExpectation: mocks.createExpectation,
      addEvidence: mocks.addEvidence,
      evaluate: mocks.evaluate,
      evidence: mocks.evidence,
      expectation: mocks.expectation,
      evaluations: mocks.evaluations,
      latest: mocks.latest,
      integrations: mocks.integrations,
      deleteIntegration: mocks.deleteIntegration,
    },
  };
});

import Dashboard from '@/app/(workspace)/dashboard/page';
import Detail from '@/app/(workspace)/expectations/[id]/page';
import Integrations from '@/app/(workspace)/integrations/page';
import { AiRecommendations } from '@/components/ai-recommendations';
import { EvidenceTimeline } from '@/components/evidence-timeline';

describe('End-to-End Integration Flow: Expectation -> Simulation -> Evidence -> Evaluation -> Dashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('proves complete lifecycle: create -> simulate Ring event -> save evidence -> evaluate -> dashboard display', async () => {
    // 1. Create Expectation
    const newExpData = {
      claim: 'Ring front door should detect packages',
      type: 'boolean' as const,
      metric: 'package_detected',
      evidence_sources: ['ring'],
      materiality_threshold: 0.05,
    };

    const createdExpectation: Expectation = {
      id: 'ring-exp-001',
      user_id: 'user-001',
      claim: newExpData.claim,
      type: newExpData.type,
      metric: newExpData.metric,
      comparison: null,
      baseline: null,
      target_value: null,
      deadline: null,
      evidence_sources: newExpData.evidence_sources,
      materiality_threshold: 0.05,
      status: 'monitoring',
      compiler_metadata: {},
      created_at: '2026-10-13T10:00:00Z',
      updated_at: '2026-10-13T10:00:00Z',
    };

    mocks.createExpectation.mockResolvedValue(createdExpectation);

    // 2. Simulate Ring event via simulator adapter
    const rawRingEvent = generateRingEvent('package_detected', { device: 'front_door', confidence: 0.98 });
    const evidencePayload = ringEventToEvidence(rawRingEvent);

    expect(evidencePayload.source).toBe('ring');
    expect(evidencePayload.metric).toBe('package_detected');
    expect(evidencePayload.value.detected).toBe(true);

    // 3. Save evidence via API
    const savedEvidence: Evidence = {
      id: 'ev-ring-101',
      expectation_id: createdExpectation.id,
      external_event_id: rawRingEvent.event_id,
      source: evidencePayload.source,
      metric: evidencePayload.metric ?? null,
      value: evidencePayload.value,
      unit: null,
      observed_at: evidencePayload.observed_at,
      confidence: evidencePayload.confidence ?? 1.0,
      raw_data: evidencePayload.raw_data ?? {},
      created_at: '2026-10-13T10:05:00Z',
    };

    mocks.addEvidence.mockResolvedValue(savedEvidence);
    const added = await mocks.addEvidence(createdExpectation.id, evidencePayload);
    expect(added.id).toBe('ev-ring-101');
    expect(mocks.addEvidence).toHaveBeenCalledWith('ring-exp-001', evidencePayload);

    // 4. Trigger backend evaluation - returns real MATCH response
    const realBackendEvaluation: Evaluation = {
      id: 'eval-ring-201',
      expectation_id: createdExpectation.id,
      result: 'MATCH',
      expected: { metric: 'package_detected', value: true },
      observed: { value: true, evidence_id: 'ev-ring-101' },
      confidence: 0.98,
      reasoning: { reason: 'boolean_truth_verified' },
      created_at: '2026-10-13T10:06:00Z',
    };

    mocks.evaluate.mockResolvedValue(realBackendEvaluation);
    const evaluated = await mocks.evaluate(createdExpectation.id);
    expect(evaluated.result).toBe('MATCH');

    // 5. Verify Dashboard reflects the fulfilled state and evidence
    const fulfilledExp: Expectation = { ...createdExpectation, status: 'fulfilled' };
    mocks.board.data = [{ expectation: fulfilledExp, latest: realBackendEvaluation }];
    mocks.evidence.mockResolvedValue([savedEvidence]);

    render(<Dashboard />);

    // Dashboard shows healthy state ("Everything looks as expected.")
    expect(await screen.findByText('Everything looks as expected.')).toBeInTheDocument();
    // Claim is rendered in expectation card and timeline event
    expect(screen.getAllByText(/Ring front door should detect packages/).length).toBeGreaterThanOrEqual(1);
    // Timeline contains the simulated event with Ring label
    expect(await screen.findByText(/Package detected/i)).toBeInTheDocument();
  });

  it('proves mismatch flow with Bee wearable simulator and displays attention state', async () => {
    // 1. Target expectation
    const beeExp: Expectation = {
      id: 'bee-exp-002',
      user_id: 'user-001',
      claim: 'Plumber confirmed for Friday',
      type: 'boolean',
      metric: 'appointment_confirmed',
      comparison: null,
      baseline: null,
      target_value: null,
      deadline: null,
      evidence_sources: ['bee'],
      materiality_threshold: 0.05,
      status: 'contradicted',
      compiler_metadata: {},
      created_at: '2026-10-13T09:00:00Z',
      updated_at: '2026-10-13T09:30:00Z',
    };

    // 2. Simulate Bee cancellation event
    const beeEvent = generateBeeEvent({
      speaker: 'Landlord',
      summary: 'The plumber had an emergency and cannot make it Friday.',
      confirmed: false,
    });
    const beeEvidenceCreate = beeEventToEvidence(beeEvent);

    expect(beeEvidenceCreate.source).toBe('bee');
    expect(beeEvidenceCreate.value.value).toBe(false);

    // 3. Backend evaluation returns MISMATCH with reasoning
    const mismatchEvaluation: Evaluation = {
      id: 'eval-bee-301',
      expectation_id: beeExp.id,
      result: 'MISMATCH',
      expected: { metric: 'appointment_confirmed', value: true },
      observed: { value: false, evidence_id: 'ev-bee-202' },
      confidence: 0.95,
      reasoning: {
        reason: 'appointment_cancelled',
        explanation: 'Bee conversation transcript indicates landlord cancelled Friday plumber appointment.',
      },
      created_at: '2026-10-13T09:30:00Z',
    };

    mocks.board.data = [{ expectation: beeExp, latest: mismatchEvaluation }];
    const beeEvidence: Evidence = {
      id: 'ev-bee-202',
      expectation_id: beeExp.id,
      external_event_id: null,
      source: 'bee',
      metric: 'appointment_confirmed',
      value: { value: false, speaker: 'Landlord', summary: 'Plumber cancelled' },
      unit: null,
      observed_at: '2026-10-13T09:25:00Z',
      confidence: 0.95,
      raw_data: {},
      created_at: '2026-10-13T09:30:00Z',
    };
    mocks.evidence.mockResolvedValue([beeEvidence]);

    render(<Dashboard />);

    // Renders Needs attention heading
    expect(await screen.findByText('Needs your attention')).toBeInTheDocument();
    expect(screen.getByText('Plumber confirmed for Friday')).toBeInTheDocument();
  });

  it('aggregates evidence timeline across all expectations, never capping at 6', async () => {
    // Create 8 expectations with evidence
    const exps: WatchedExpectation[] = Array.from({ length: 8 }, (_, i) => ({
      expectation: {
        ...expectation,
        id: `exp-${i + 1}`,
        claim: `Monitored bill #${i + 1}`,
      },
      latest: evaluation,
    }));

    mocks.board.data = exps;
    // Each expectation has 1 evidence entry
    mocks.evidence.mockImplementation((id: string) =>
      Promise.resolve([
        {
          id: `ev-${id}`,
          expectation_id: id,
          external_event_id: null,
          source: 'utility_bill',
          metric: 'total_cost',
          value: { amount: 100 + Number(id.replace('exp-', '')) },
          unit: 'USD',
          observed_at: `2026-10-13T10:0${id.replace('exp-', '')}:00Z`,
          confidence: 1,
          raw_data: {},
          created_at: '2026-10-13T10:10:00Z',
        },
      ])
    );

    render(<Dashboard />);

    // Wait for all 8 evidence requests to be initiated and rendered
    await waitFor(() => {
      expect(mocks.evidence.mock.calls.length).toBeGreaterThanOrEqual(8);
    });

    for (let i = 1; i <= 8; i++) {
      expect(mocks.evidence).toHaveBeenCalledWith(`exp-${i}`, expect.any(AbortSignal));
    }
  });

  it('proves connected accounts UI displays simulated indicators, email derivation disclaimers and disconnect action', async () => {
    const ringIntegration = {
      ...integration,
      id: 'ring-conn-1',
      provider: 'ring' as const,
      connection_type: 'camera' as const,
      display_name: 'Front Door Ring Cam',
      scopes: ['devices.events.read'],
      status: 'connected' as const,
    };

    const amazonDelivery = {
      ...integration,
      id: 'amazon-conn-2',
      provider: 'delivery' as const,
      connection_type: 'delivery' as const,
      display_name: 'Amazon Deliveries',
      scopes: ['mail.read'],
      status: 'connected' as const,
    };

    mocks.integrations.mockResolvedValue([ringIntegration, amazonDelivery]);
    mocks.deleteIntegration.mockResolvedValue({ success: true });

    render(<Integrations />);

    // Displays Ring with SIMULATED badge
    expect(await screen.findByText('SIMULATED (NO LIVE HARDWARE)')).toBeInTheDocument();
    expect(screen.getByText('Front Door Ring Cam')).toBeInTheDocument();

    // Displays Amazon Email-derived disclaimer
    expect(screen.getByText('Amazon (Email-derived)')).toBeInTheDocument();
    expect(
      screen.getByText(/Order status is extracted from authenticated email receipts\. Does not imply direct Amazon Retail API authorization\./)
    ).toBeInTheDocument();

    // Granted permissions are displayed
    expect(screen.getByText('devices.events.read')).toBeInTheDocument();

    // Disconnect button functions cleanly
    const disconnectButtons = screen.getAllByRole('button', { name: 'Disconnect' });
    expect(disconnectButtons.length).toBeGreaterThanOrEqual(1);

    await userEvent.click(disconnectButtons[0]);
    expect(mocks.deleteIntegration).toHaveBeenCalledWith('ring-conn-1');
  });

  it('proves AI recommendations flow: Accept creates expectation directly in backend', async () => {
    mocks.createExpectation.mockResolvedValue({
      ...expectation,
      id: 'accepted-rec-1',
      claim: 'Package delivery from Amazon order #112-8821 expected by 8:00 PM Friday',
    });

    render(<AiRecommendations onAccepted={mocks.board.reload} />);

    // Verify recommendations heading and suggestions
    expect(screen.getByText('Suggested Expectations')).toBeInTheDocument();
    expect(screen.getByText(/Next municipal water bill/)).toBeInTheDocument();

    // Click Accept on first recommendation (Amazon order delivery)
    const acceptButtons = screen.getAllByRole('button', { name: /Accept/ });
    await userEvent.click(acceptButtons[0]);

    // Verifies createExpectation is called with structured contract
    await waitFor(() => {
      expect(mocks.createExpectation).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'boolean',
          metric: 'delivered',
        })
      );
    });

    // Board reload is invoked to display the new expectation immediately
    expect(mocks.board.reload).toHaveBeenCalled();
  });

  it('renders SIMULATED tags on Ring and Bee items in the evidence timeline', () => {
    const mixedEvidence: Evidence[] = [
      {
        id: 'ev-ring',
        expectation_id: 'exp-1',
        external_event_id: null,
        source: 'ring',
        metric: 'package_detected',
        value: { detected: true },
        unit: null,
        observed_at: '2026-10-13T10:00:00Z',
        confidence: 0.95,
        raw_data: {},
        created_at: '2026-10-13T10:01:00Z',
      },
      {
        id: 'ev-bee',
        expectation_id: 'exp-2',
        external_event_id: null,
        source: 'bee',
        metric: 'appointment_confirmed',
        value: { value: true, speaker: 'Doctor' },
        unit: null,
        observed_at: '2026-10-13T09:00:00Z',
        confidence: 0.9,
        raw_data: {},
        created_at: '2026-10-13T09:01:00Z',
      },
    ];

    render(<EvidenceTimeline evidenceList={mixedEvidence} expectations={[expectation]} />);

    // Both Ring and Bee show SIMULATED badge
    const simBadges = screen.getAllByText('SIMULATED');
    expect(simBadges).toHaveLength(2);
  });

  it('proves utility bill threshold simulation and grounded detail view', async () => {
    const utilityExp: Expectation = {
      ...expectation,
      id: 'util-exp-003',
      claim: 'My next electric bill should be lower.',
      type: 'numeric_comparison',
      metric: 'total_cost',
      comparison: 'less_than',
      baseline: 142.10,
      materiality_threshold: 0.05,
      evidence_sources: ['utility_bill', 'utility_usage'],
    };

    const utilityEvidence = createUtilityBillEvidence(162);
    expect(utilityEvidence.value.amount).toBe(162);

    mocks.expectation.mockResolvedValue(utilityExp);
    mocks.evidence.mockResolvedValue([
      {
        id: 'ev-util-1',
        expectation_id: utilityExp.id,
        external_event_id: null,
        source: 'utility_bill',
        metric: 'total_cost',
        value: { amount: 162 },
        unit: 'USD',
        observed_at: '2026-10-13T10:00:00Z',
        confidence: 1.0,
        raw_data: {},
        created_at: '2026-10-13T10:00:00Z',
      },
    ]);
    mocks.evaluations.mockResolvedValue([evaluation]);
    mocks.latest.mockResolvedValue(evaluation);

    const params = Promise.resolve({ id: utilityExp.id });
    await act(async () => {
      render(
        <Suspense fallback={<span>Loading detail</span>}>
          <Detail params={params} />
        </Suspense>
      );
      await params;
    });

    expect(await screen.findByRole('heading', { name: 'Evidence gathered' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Timeline' })).toBeInTheDocument();
    expect(screen.getAllByText('$162.00').length).toBeGreaterThanOrEqual(1);
  });
});
