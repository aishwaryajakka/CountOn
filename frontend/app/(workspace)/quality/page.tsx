'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import {
  CheckCircle,
  Clock,
  DollarSign,
  AlertTriangle,
  Play,
  RotateCcw,
  Sparkles,
  Check,
  X,
  ShieldCheck,
  Cpu,
  BarChart2,
} from 'lucide-react';
import { PageHeader, Loading, ErrorState } from '@/components/ui';

interface HumanReviewItem {
  id: string;
  input_text: string;
  model_output: Record<string, any>;
  expected_output?: Record<string, any>;
  status: 'pending' | 'verified' | 'flagged' | 'rejected';
  reviewer_notes?: string;
  reviewer_verdict?: string;
  latency_ms?: number;
  created_at: string;
  reviewed_at?: string;
}

interface BenchmarkReport {
  total_requests: number;
  successful_requests: number;
  failed_requests: number;
  latency: {
    avg_ms: number;
    p50_ms: number;
    p95_ms: number;
    min_ms: number;
    max_ms: number;
  };
  tokens: {
    total_input: number;
    total_output: number;
    total: number;
  };
  cost: {
    total_usd: number;
    avg_per_request_usd: number;
  };
  samples: Array<{
    query: string;
    latency_ms: number;
    input_tokens: number;
    output_tokens: number;
    cost_usd: number;
    success: boolean;
  }>;
}

interface RecommendationItem {
  id: string;
  title: string;
  claim: string;
  category: string;
  type: string;
  metric?: string;
  comparison?: string;
  baseline?: number;
  confidence: number;
  status: 'pending_approval' | 'approved' | 'rejected' | 'dismissed';
  rationale: string;
  source_references: Array<{
    provider: string;
    source_id?: string;
    snippet?: string;
  }>;
  created_at: string;
}

export default function QualityDashboard() {
  const [activeTab, setActiveTab] = useState<'reviews' | 'benchmark' | 'recommendations'>('reviews');

  // Human Review State
  const [reviews, setReviews] = useState<HumanReviewItem[]>([]);
  const [loadingReviews, setLoadingReviews] = useState(true);
  const [reviewNote, setReviewNote] = useState<Record<string, string>>({});
  const [submittingReview, setSubmittingReview] = useState<string | null>(null);

  // Benchmark State
  const [benchmark, setBenchmark] = useState<BenchmarkReport | null>(null);
  const [runningBenchmark, setRunningBenchmark] = useState(false);

  // Recommendations State
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [loadingRecs, setLoadingRecs] = useState(true);
  const [approvingRec, setApprovingRec] = useState<string | null>(null);

  const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || 'http://127.0.0.1:8000';

  const fetchReviews = async () => {
    try {
      setLoadingReviews(true);
      const res = await fetch(`${apiBase}/api/v1/quality/reviews`);
      if (res.ok) {
        setReviews(await res.json());
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingReviews(false);
    }
  };

  const fetchRecommendations = async () => {
    try {
      setLoadingRecs(true);
      const res = await fetch(`${apiBase}/api/v1/quality/recommendations`);
      if (res.ok) {
        setRecommendations(await res.json());
      }
    } catch (e) {
      console.error(e);
    } finally {
      setLoadingRecs(false);
    }
  };

  useEffect(() => {
    fetchReviews();
    fetchRecommendations();
  }, []);

  const handleDecision = async (id: string, status: 'verified' | 'flagged' | 'rejected') => {
    setSubmittingReview(id);
    try {
      const res = await fetch(`${apiBase}/api/v1/quality/reviews/${id}/decide`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          status,
          reviewer_notes: reviewNote[id] || (status === 'verified' ? 'Verified accurate by human reviewer' : 'Flagged for review'),
          reviewer_verdict: status,
        }),
      });
      if (res.ok) {
        await fetchReviews();
      }
    } catch (e) {
      console.error(e);
    } finally {
      setSubmittingReview(null);
    }
  };

  const runBenchmarkSuite = async (mockMode: boolean = false) => {
    setRunningBenchmark(true);
    try {
      const res = await fetch(`${apiBase}/api/v1/quality/benchmark?mock_mode=${mockMode}`, {
        method: 'POST',
      });
      if (res.ok) {
        setBenchmark(await res.json());
      }
    } catch (e) {
      console.error(e);
    } finally {
      setRunningBenchmark(false);
    }
  };

  return (
    <div style={{ maxWidth: '1200px', margin: '0 auto', padding: '1.5rem' }}>
      <PageHeader
        title="AI Verification & Quality Hub"
        description="Review real Bedrock model outputs, benchmark latency and cost, and manage high-confidence expectation recommendations."
      />

      {/* Tabs */}
      <div style={{ display: 'flex', gap: '1rem', borderBottom: '1px solid #e2e8f0', marginBottom: '2rem', marginTop: '1rem' }}>
        <button
          onClick={() => setActiveTab('reviews')}
          style={{
            padding: '0.75rem 1.25rem',
            fontWeight: activeTab === 'reviews' ? 600 : 400,
            color: activeTab === 'reviews' ? '#2563eb' : '#64748b',
            borderBottom: activeTab === 'reviews' ? '2px solid #2563eb' : 'none',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontSize: '0.95rem',
          }}
        >
          🔍 Human Review ({reviews.filter(r => r.status === 'pending').length} pending)
        </button>
        <button
          onClick={() => setActiveTab('benchmark')}
          style={{
            padding: '0.75rem 1.25rem',
            fontWeight: activeTab === 'benchmark' ? 600 : 400,
            color: activeTab === 'benchmark' ? '#2563eb' : '#64748b',
            borderBottom: activeTab === 'benchmark' ? '2px solid #2563eb' : 'none',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontSize: '0.95rem',
          }}
        >
          ⚡ Latency & Cost Suite
        </button>
        <button
          onClick={() => setActiveTab('recommendations')}
          style={{
            padding: '0.75rem 1.25rem',
            fontWeight: activeTab === 'recommendations' ? 600 : 400,
            color: activeTab === 'recommendations' ? '#2563eb' : '#64748b',
            borderBottom: activeTab === 'recommendations' ? '2px solid #2563eb' : 'none',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontSize: '0.95rem',
          }}
        >
          ✨ Recommendations ({recommendations.filter(r => r.status === 'pending_approval').length})
        </button>
      </div>

      {/* Tab 1: Human Review Output against Expected */}
      {activeTab === 'reviews' && (
        <section>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 600 }}>Real Bedrock Output Inspection</h2>
            <button
              onClick={fetchReviews}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: '0.5rem 1rem',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                background: '#fff',
                cursor: 'pointer',
              }}
            >
              <RotateCcw size={16} /> Refresh Items
            </button>
          </div>

          {loadingReviews ? (
            <Loading />
          ) : reviews.length === 0 ? (
            <p style={{ color: '#64748b' }}>No review items available.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
              {reviews.map((item) => (
                <div
                  key={item.id}
                  style={{
                    backgroundColor: '#fff',
                    borderRadius: '8px',
                    border: '1px solid #e2e8f0',
                    padding: '1.25rem',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '1rem' }}>
                    <div>
                      <span
                        style={{
                          fontSize: '0.75rem',
                          textTransform: 'uppercase',
                          fontWeight: 700,
                          letterSpacing: '0.05em',
                          color: '#64748b',
                        }}
                      >
                        User Prompt / Input
                      </span>
                      <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginTop: '0.25rem' }}>
                        &ldquo;{item.input_text}&rdquo;
                      </h3>
                    </div>
                    <span
                      style={{
                        padding: '0.25rem 0.75rem',
                        borderRadius: '9999px',
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        backgroundColor:
                          item.status === 'verified'
                            ? '#dcfce7'
                            : item.status === 'flagged'
                            ? '#fef9c3'
                            : item.status === 'rejected'
                            ? '#fee2e2'
                            : '#f1f5f9',
                        color:
                          item.status === 'verified'
                            ? '#166534'
                            : item.status === 'flagged'
                            ? '#854d0e'
                            : item.status === 'rejected'
                            ? '#991b1b'
                            : '#475569',
                      }}
                    >
                      {item.status.toUpperCase()}
                    </span>
                  </div>

                  <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1rem' }}>
                    <div style={{ backgroundColor: '#f8fafc', padding: '1rem', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                      <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#334155' }}>
                        🤖 Bedrock Model Output ({item.latency_ms ? `${item.latency_ms}ms` : 'latency N/A'})
                      </span>
                      <pre style={{ fontSize: '0.8rem', marginTop: '0.5rem', whiteSpace: 'pre-wrap', color: '#1e293b' }}>
                        {JSON.stringify(item.model_output, null, 2)}
                      </pre>
                    </div>

                    <div style={{ backgroundColor: '#f0fdf4', padding: '1rem', borderRadius: '6px', border: '1px solid #bbf7d0' }}>
                      <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#166534' }}>
                        🎯 Expected Verification Criteria
                      </span>
                      <pre style={{ fontSize: '0.8rem', marginTop: '0.5rem', whiteSpace: 'pre-wrap', color: '#14532d' }}>
                        {JSON.stringify(item.expected_output || { check: 'Model should parse valid numeric metric & baseline' }, null, 2)}
                      </pre>
                    </div>
                  </div>

                  {item.status === 'pending' ? (
                    <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', marginTop: '1rem' }}>
                      <input
                        type="text"
                        placeholder="Reviewer notes (optional)..."
                        value={reviewNote[item.id] || ''}
                        onChange={(e) => setReviewNote({ ...reviewNote, [item.id]: e.target.value })}
                        style={{
                          flex: 1,
                          padding: '0.5rem 0.75rem',
                          borderRadius: '6px',
                          border: '1px solid #cbd5e1',
                          fontSize: '0.85rem',
                        }}
                      />
                      <button
                        onClick={() => handleDecision(item.id, 'verified')}
                        disabled={submittingReview === item.id}
                        style={{
                          backgroundColor: '#16a34a',
                          color: '#fff',
                          border: 'none',
                          borderRadius: '6px',
                          padding: '0.5rem 1rem',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.25rem',
                          fontWeight: 500,
                        }}
                      >
                        <Check size={16} /> Mark Verified
                      </button>
                      <button
                        onClick={() => handleDecision(item.id, 'flagged')}
                        disabled={submittingReview === item.id}
                        style={{
                          backgroundColor: '#ca8a04',
                          color: '#fff',
                          border: 'none',
                          borderRadius: '6px',
                          padding: '0.5rem 1rem',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.25rem',
                          fontWeight: 500,
                        }}
                      >
                        <AlertTriangle size={16} /> Flag
                      </button>
                      <button
                        onClick={() => handleDecision(item.id, 'rejected')}
                        disabled={submittingReview === item.id}
                        style={{
                          backgroundColor: '#dc2626',
                          color: '#fff',
                          border: 'none',
                          borderRadius: '6px',
                          padding: '0.5rem 1rem',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '0.25rem',
                          fontWeight: 500,
                        }}
                      >
                        <X size={16} /> Reject
                      </button>
                    </div>
                  ) : (
                    <div style={{ marginTop: '0.75rem', fontSize: '0.85rem', color: '#64748b' }}>
                      <strong>Reviewer note:</strong> {item.reviewer_notes || 'No notes left'}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* Tab 2: Latency and Cost Benchmarking Suite */}
      {activeTab === 'benchmark' && (
        <section>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
            <div>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 600 }}>Bedrock Latency & Cost Measurement Suite</h2>
              <p style={{ color: '#64748b', fontSize: '0.9rem' }}>
                Measures p50/p95 latency distributions and calculates token expenses using official Claude 3 Bedrock pricing.
              </p>
            </div>
            <div style={{ display: 'flex', gap: '0.75rem' }}>
              <button
                onClick={() => runBenchmarkSuite(true)}
                disabled={runningBenchmark}
                style={{
                  backgroundColor: '#475569',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '6px',
                  padding: '0.6rem 1rem',
                  cursor: 'pointer',
                  fontWeight: 500,
                }}
              >
                Run Mock Suite
              </button>
              <button
                onClick={() => runBenchmarkSuite(false)}
                disabled={runningBenchmark}
                style={{
                  backgroundColor: '#2563eb',
                  color: '#fff',
                  border: 'none',
                  borderRadius: '6px',
                  padding: '0.6rem 1.25rem',
                  cursor: 'pointer',
                  fontWeight: 600,
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                }}
              >
                <Play size={16} /> {runningBenchmark ? 'Executing Benchmark…' : 'Benchmark Live Bedrock'}
              </button>
            </div>
          </div>

          {benchmark && (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
              {/* Stat Cards */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1rem' }}>
                <div style={{ backgroundColor: '#fff', padding: '1.25rem', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                  <span style={{ fontSize: '0.8rem', color: '#64748b' }}>Average Latency</span>
                  <p style={{ fontSize: '1.5rem', fontWeight: 700, marginTop: '0.25rem', color: '#1e293b' }}>
                    {benchmark.latency.avg_ms} ms
                  </p>
                  <span style={{ fontSize: '0.75rem', color: '#10b981' }}>p50: {benchmark.latency.p50_ms}ms · p95: {benchmark.latency.p95_ms}ms</span>
                </div>

                <div style={{ backgroundColor: '#fff', padding: '1.25rem', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                  <span style={{ fontSize: '0.8rem', color: '#64748b' }}>Estimated Total Cost</span>
                  <p style={{ fontSize: '1.5rem', fontWeight: 700, marginTop: '0.25rem', color: '#16a34a' }}>
                    ${benchmark.cost.total_usd.toFixed(5)}
                  </p>
                  <span style={{ fontSize: '0.75rem', color: '#64748b' }}>~${benchmark.cost.avg_per_request_usd.toFixed(5)} / req</span>
                </div>

                <div style={{ backgroundColor: '#fff', padding: '1.25rem', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                  <span style={{ fontSize: '0.8rem', color: '#64748b' }}>Total Token Usage</span>
                  <p style={{ fontSize: '1.5rem', fontWeight: 700, marginTop: '0.25rem', color: '#2563eb' }}>
                    {benchmark.tokens.total.toLocaleString()}
                  </p>
                  <span style={{ fontSize: '0.75rem', color: '#64748b' }}>{benchmark.tokens.total_input} in / {benchmark.tokens.total_output} out</span>
                </div>

                <div style={{ backgroundColor: '#fff', padding: '1.25rem', borderRadius: '8px', border: '1px solid #e2e8f0' }}>
                  <span style={{ fontSize: '0.8rem', color: '#64748b' }}>Success Rate</span>
                  <p style={{ fontSize: '1.5rem', fontWeight: 700, marginTop: '0.25rem', color: '#0ea5e9' }}>
                    {((benchmark.successful_requests / benchmark.total_requests) * 100).toFixed(0)}%
                  </p>
                  <span style={{ fontSize: '0.75rem', color: '#64748b' }}>{benchmark.successful_requests}/{benchmark.total_requests} succeeded</span>
                </div>
              </div>

              {/* Sample Table */}
              <div style={{ backgroundColor: '#fff', borderRadius: '8px', border: '1px solid #e2e8f0', overflow: 'hidden' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '0.9rem' }}>
                  <thead style={{ backgroundColor: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
                    <tr>
                      <th style={{ padding: '0.75rem 1rem' }}>Representative Query</th>
                      <th style={{ padding: '0.75rem 1rem' }}>Latency</th>
                      <th style={{ padding: '0.75rem 1rem' }}>Tokens (In / Out)</th>
                      <th style={{ padding: '0.75rem 1rem' }}>Est. Cost (USD)</th>
                      <th style={{ padding: '0.75rem 1rem' }}>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {benchmark.samples.map((sample, idx) => (
                      <tr key={idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: '0.75rem 1rem', fontWeight: 500 }}>{sample.query}</td>
                        <td style={{ padding: '0.75rem 1rem' }}>{sample.latency_ms} ms</td>
                        <td style={{ padding: '0.75rem 1rem' }}>{sample.input_tokens} / {sample.output_tokens}</td>
                        <td style={{ padding: '0.75rem 1rem', color: '#16a34a' }}>${sample.cost_usd.toFixed(6)}</td>
                        <td style={{ padding: '0.75rem 1rem' }}>
                          <span style={{ color: sample.success ? '#16a34a' : '#dc2626', fontWeight: 600 }}>
                            {sample.success ? 'Success' : 'Failed'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </section>
      )}

      {/* Tab 3: Structured Recommendations & User Approval */}
      {activeTab === 'recommendations' && (
        <section>
          <div style={{ marginBottom: '1.5rem' }}>
            <h2 style={{ fontSize: '1.25rem', fontWeight: 600 }}>Candidate Expectation Recommendations</h2>
            <p style={{ color: '#64748b', fontSize: '0.9rem' }}>
              Extracted from connected accounts (Gmail, Outlook, Amazon). Explicit user approval is required before activating any recommendation.
            </p>
          </div>

          {loadingRecs ? (
            <Loading />
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: '1.25rem' }}>
              {recommendations.map((rec) => (
                <div
                  key={rec.id}
                  style={{
                    backgroundColor: '#fff',
                    borderRadius: '8px',
                    border: '1px solid #e2e8f0',
                    padding: '1.25rem',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
                    display: 'flex',
                    flexDirection: 'column',
                    justifyContent: 'space-between',
                  }}
                >
                  <div>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                      <span
                        style={{
                          backgroundColor: '#eff6ff',
                          color: '#2563eb',
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          padding: '0.2rem 0.6rem',
                          borderRadius: '4px',
                          textTransform: 'uppercase',
                        }}
                      >
                        {rec.category}
                      </span>
                      <span style={{ fontSize: '0.8rem', fontWeight: 600, color: '#059669' }}>
                        {(rec.confidence * 100).toFixed(0)}% Confidence
                      </span>
                    </div>

                    <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                      {rec.title}
                    </h3>
                    <p style={{ fontStyle: 'italic', color: '#334155', marginBottom: '0.75rem', fontSize: '0.95rem' }}>
                      &ldquo;{rec.claim}&rdquo;
                    </p>

                    <div style={{ backgroundColor: '#f8fafc', padding: '0.75rem', borderRadius: '6px', fontSize: '0.85rem', marginBottom: '1rem' }}>
                      <div style={{ fontWeight: 600, color: '#475569', marginBottom: '0.25rem' }}>Provenance / Source Snippet:</div>
                      {rec.source_references[0]?.snippet ? (
                        <p style={{ color: '#64748b', margin: 0 }}>&ldquo;{rec.source_references[0].snippet}&rdquo;</p>
                      ) : (
                        <p style={{ color: '#94a3b8', margin: 0 }}>Source ID: {rec.source_references[0]?.source_id || 'Email/Order parser'}</p>
                      )}
                    </div>
                  </div>

                  <div>
                    {rec.status === 'pending_approval' ? (
                      <div style={{ display: 'flex', gap: '0.75rem', marginTop: '0.5rem' }}>
                        <button
                          style={{
                            flex: 1,
                            backgroundColor: '#2563eb',
                            color: '#fff',
                            border: 'none',
                            borderRadius: '6px',
                            padding: '0.6rem',
                            cursor: 'pointer',
                            fontWeight: 600,
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '0.4rem',
                          }}
                          onClick={async () => {
                            setApprovingRec(rec.id);
                            await fetch(`${apiBase}/api/v1/quality/recommendations/${rec.id}/approval`, {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({ action: 'approved' }),
                            });
                            await fetchRecommendations();
                            setApprovingRec(null);
                          }}
                        >
                          <Check size={16} /> Approve & Monitor
                        </button>
                        <button
                          style={{
                            backgroundColor: '#f1f5f9',
                            color: '#64748b',
                            border: 'none',
                            borderRadius: '6px',
                            padding: '0.6rem 1rem',
                            cursor: 'pointer',
                          }}
                          onClick={async () => {
                            await fetch(`${apiBase}/api/v1/quality/recommendations/${rec.id}/approval`, {
                              method: 'POST',
                              headers: { 'Content-Type': 'application/json' },
                              body: JSON.stringify({ action: 'rejected' }),
                            });
                            await fetchRecommendations();
                          }}
                        >
                          Dismiss
                        </button>
                      </div>
                    ) : (
                      <div
                        style={{
                          padding: '0.5rem',
                          borderRadius: '6px',
                          textAlign: 'center',
                          fontSize: '0.85rem',
                          fontWeight: 600,
                          backgroundColor: rec.status === 'approved' ? '#dcfce7' : '#fee2e2',
                          color: rec.status === 'approved' ? '#166534' : '#991b1b',
                        }}
                      >
                        {rec.status === 'approved' ? 'Active Expectation Created' : 'Dismissed by User'}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
