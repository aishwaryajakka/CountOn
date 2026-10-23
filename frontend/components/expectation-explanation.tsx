'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useAuth, useIdentity } from '@/components/auth-provider';
import { AgentClientError, requestAgent } from '@/lib/agent/client';
import { formatDate } from '@/lib/presentation';
import type { AuditEvent } from '@/lib/types';

export function ExpectationExplanation({ expectationId, record, loaded, recorded }: {
  expectationId: string; record: AuditEvent | null; loaded: boolean; recorded: () => void;
}) {
  const { session } = useAuth();
  const { timeZone } = useIdentity();
  const [answer, setAnswer] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function explain() {
    setBusy(true); setError(null);
    try {
      // Same authenticated server orchestration as /alexa. The browser sends an
      // owned-record reference and language, never a tool, verdict or evidence.
      const result = await requestAgent(session?.access_token, {
        text: 'Why did it fail?', session_reference: null, expectation_id: expectationId,
      });
      if (result.status !== 'SUCCESS' || result.action !== 'EXPLAIN_MISMATCH') {
        setError(result.answer);
        return;
      }
      setAnswer(result.answer);
      recorded();
    } catch (cause) {
      setError(cause instanceof AgentClientError ? cause.message : 'CountOn could not explain this just now. Please try again.');
    } finally { setBusy(false); }
  }
  return <>
    {record ? <>
      <p>{record.action_metadata.bedrock_used === true ? 'Bedrock explanation recorded' : record.action_metadata.fallback_used === true ? 'CountOn fallback explanation recorded' : 'Explanation recorded'}{record.action_metadata.grounded === true ? ' · grounded in recorded evidence' : ''}.</p>
      <time dateTime={record.occurred_at}>{formatDate(record.occurred_at, timeZone)}</time>
      <p className="caption">{Array.isArray(record.action_metadata.evidence_ids) ? record.action_metadata.evidence_ids.length : 0} evidence references recorded. Exact previous wording is not retained by the history API.</p>
    </> : loaded ? <p>No explanation is recorded for this evaluation yet.</p> : null}
    {answer && <p role="status">{answer}</p>}
    <button className="button secondary" disabled={busy} onClick={() => void explain()}>{busy ? 'Asking CountOn…' : 'Get grounded explanation'}</button>
    <Link className="text-link" href={`/alexa?expectationId=${expectationId}&starter=${encodeURIComponent('Why did it fail?')}`}>Open Alexa conversation</Link>
    {error && <p role="alert">{error}</p>}
  </>;
}
