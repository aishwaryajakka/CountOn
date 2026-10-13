'use client';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowLeft, ArrowUp, Check, MessageCircle, Radio, Volume2 } from 'lucide-react';
import { useAuth, useIdentity } from '@/components/auth-provider';
import { Logo } from '@/components/ui';
import { requestMcp, McpClientError } from '@/lib/mcp/client';
import { toolNames } from '@/lib/mcp/contracts';
import { requestAgent, AgentClientError } from '@/lib/agent/client';
import type { AgentResponse } from '@/lib/agent/contracts';

type TraceEvent = AgentResponse['traces'][number];
type Message = { id: number; role: 'user' | 'assistant'; text: string; rows?: AgentResponse['rows']; traces?: TraceEvent[]; saved?: string; error?: boolean; provenance?: AgentResponse['provenance'] };
const starters = ['What am I counting on?', 'Tell me about my electricity bill', "I'm counting on my grocery bill staying under $120 this week"];
const label = (value: string) => value.replace(/_/g, ' ');
function Trace({ event }: { event: TraceEvent }) {
  return <details className="alexa-trace"><summary>{event.layer} → {event.label}</summary><p className="caption">Approved CountOn capability. MCP actions use Streamable HTTP.</p></details>;
}
function Provenance({ value, traces }: { value: NonNullable<AgentResponse['provenance']>; traces?: TraceEvent[] }) {
  return <details className="alexa-trace"><summary>Why CountOn said this</summary><dl>
    <div><dt>Expectation</dt><dd>{value.expectation_label ?? 'No expectation selected'}</dd></div>
    <div><dt>Evaluation</dt><dd>{value.evaluator_result ?? 'No recorded evaluation used'}</dd></div>
    <div><dt>Sources used</dt><dd>{value.sources_used.length ? value.sources_used.join(', ') : 'None'}</dd></div>
    <div><dt>Evidence used</dt><dd>{value.evidence_count} {value.evidence_count === 1 ? 'signal' : 'signals'}</dd></div>
    <div><dt>AI</dt><dd>{value.bedrock_used ? 'Amazon Bedrock' : 'No AI output used'}</dd></div>
    {value.fallback_used && <div><dt>Fallback</dt><dd>Safe fallback used</dd></div>}
  </dl>{traces?.map((event, index) => <p className="caption" key={index}>{event.layer} → {event.label}</p>)}</details>;
}
function AlexaConversation() {
  const { session } = useAuth(); const { firstName } = useIdentity();
  const [connection, setConnection] = useState<'checking' | 'connected' | 'unavailable'>('checking');
  const [messages, setMessages] = useState<Message[]>([]); const [input, setInput] = useState('');
  const sessionReference = useRef<string | null>(null);
  const [busy, setBusy] = useState(false); const [expired, setExpired] = useState(false);
  const [voice, setVoice] = useState(false); const [canSpeak] = useState(() => typeof window !== 'undefined' && 'speechSynthesis' in window);
  const nextId = useRef(0); const bottom = useRef<HTMLDivElement>(null); const inFlight = useRef(false);
  const token = session?.access_token;
  useEffect(() => () => { if ('speechSynthesis' in window) window.speechSynthesis.cancel(); }, []);
  useEffect(() => {
    let active = true;
    requestMcp(token, { action: 'list_tools' }).then(response => {
      if (active) setConnection(response.meta.initialized && response.meta.toolsDiscovered && 'tools' in response && toolNames.every(name => response.tools.some(tool => tool.name === name)) ? 'connected' : 'unavailable');
    }).catch(error => { if (active) { setConnection('unavailable'); if (error instanceof McpClientError && ['AUTH_EXPIRED', 'AUTH_REQUIRED'].includes(error.code)) setExpired(true); } });
    return () => { active = false; };
  }, [token]);
  useEffect(() => { bottom.current?.scrollIntoView?.({ behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'nearest' }); }, [messages, busy]);
  async function send(text: string) {
    if (!text.trim() || inFlight.current || expired) return;
    inFlight.current = true; setBusy(true); setInput('');
    setMessages(previous => [...previous, { id: nextId.current++, role: 'user', text: text.trim() }]);
    let reply: Omit<Message, 'id' | 'role'>;
    try {
      const result = await requestAgent(token, { text: text.trim(), session_reference: sessionReference.current });
      sessionReference.current = result.session_reference;
      if (result.traces.some(event => event.layer === 'MCP')) setConnection('connected');
      if (result.code === 'UNAVAILABLE') setConnection('unavailable');
      reply = {
        text: result.code === 'UNAVAILABLE' && result.status === 'FAILED' ? "CountOn can't reach its tools right now. Check CountOn before retrying a save." : result.answer,
        rows: result.rows,
        saved: result.captured && result.saved_id ? result.saved_id : undefined,
        traces: result.traces,
        provenance: result.provenance,
        error: result.status === 'FAILED' || result.status === 'REJECTED',
      };
    } catch (error) {
      // No retry: a lost response may follow a successful persisted capture.
      sessionReference.current = null;
      const code = error instanceof AgentClientError ? error.code : 'UNAVAILABLE';
      if (code === 'AUTH_REQUIRED' || code === 'AUTH_EXPIRED') setExpired(true);
      if (code === 'UNAVAILABLE') setConnection('unavailable');
      reply = { text: error instanceof AgentClientError ? error.message : "CountOn can't reach its tools right now. Check CountOn before retrying a save.", error: true };
    }
    setMessages(previous => [...previous, { ...reply, role: 'assistant', id: nextId.current++ }]);
    if (voice && canSpeak) {
      try { window.speechSynthesis.cancel(); window.speechSynthesis.speak(new SpeechSynthesisUtterance(reply.text)); }
      catch { setVoice(false); }
    }
    setBusy(false); inFlight.current = false;
  }
  const submit = (event: FormEvent) => { event.preventDefault(); void send(input); };
  return <div className="alexa-page"><header className="alexa-top"><Link href="/dashboard" aria-label="CountOn home"><Logo /></Link><Link className="text-link" href="/dashboard"><ArrowLeft size={16} />Back to CountOn</Link></header>
    <main id="main-content" className="alexa-main"><div className="alexa-heading"><div><span className="eyebrow">A quieter way to check in</span><h1>Alexa+ MCP Demo</h1><p>Your expectations. A conversation. The live CountOn MCP server.</p></div><span role="status" className={`alexa-connection ${connection}`}><Radio size={15} />{connection === 'checking' ? 'Connecting to CountOn MCP' : connection === 'connected' ? 'Connected to CountOn MCP' : 'CountOn MCP unavailable'}</span></div>
      <div className="alexa-chat card"><div className="alexa-chat-heading"><span className="icon-box"><MessageCircle size={21} /></span><div><strong>CountOn</strong><p className="caption">Calm monitoring. Clear signals.</p></div>{canSpeak && <button className={`alexa-voice ${voice ? 'active' : ''}`} aria-pressed={voice} onClick={() => { setVoice(!voice); if (voice) window.speechSynthesis.cancel(); }}><Volume2 size={16} />Read replies {voice ? 'on' : 'off'}</button>}</div>
        <div role="log" aria-label="Conversation with CountOn" aria-live="polite" className="alexa-transcript"><article className="alexa-message assistant"><span className="alexa-speaker">CountOn</span><p>Hi {firstName}. What are you counting on?</p><p className="caption">Ask about something you’re tracking, or describe a new expectation. I’ll use your actual CountOn records.</p></article>
          {messages.map(message => <article key={message.id} className={`alexa-message ${message.role} ${message.error ? 'is-error' : ''}`}><span className="alexa-speaker">{message.role === 'user' ? 'You' : 'CountOn'}</span><p>{message.text}</p>{message.rows && <div className="alexa-records">{message.rows.map(row => <div key={row.id} className="alexa-record"><strong>{row.claim}</strong><span className={`alexa-record-status ${row.status}`}>{label(row.status)}</span><dl><div><dt>Type</dt><dd>{label(row.type)}</dd></div><div><dt>Metric</dt><dd>{row.metric ?? 'Not specified'}</dd></div><div><dt>Created</dt><dd>{new Date(row.created_at).toLocaleDateString()}</dd></div></dl></div>)}</div>}{message.saved && <div className="alexa-saved"><span><Check size={16} />Saved to CountOn</span><Link className="button primary" href={`/expectations/${encodeURIComponent(message.saved)}`}>View in CountOn</Link></div>}{message.provenance ? <Provenance value={message.provenance} traces={message.traces} /> : message.traces?.map((trace, index) => <Trace key={index} event={trace} />)}</article>)}
          {busy && <div role="status" className="alexa-working"><span className="status-dot" />Checking with CountOn…</div>}<div ref={bottom} /></div>
        {expired && <div role="alert" className="alexa-auth-error">Your CountOn session expired. <Link href="/login">Please sign in again.</Link></div>}
        <div className="alexa-compose-area"><div className="alexa-starters" aria-label="Starter prompts">{starters.map(prompt => <button key={prompt} disabled={busy || expired} onClick={() => void send(prompt)}>{prompt}</button>)}</div><form onSubmit={submit} className="alexa-composer"><label htmlFor="alexa-input" className="sr-only">Message CountOn</label><textarea id="alexa-input" rows={2} maxLength={2000} value={input} onChange={event => setInput(event.target.value)} placeholder="Tell CountOn what’s on your mind…" disabled={busy || expired} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(input); } }} /><button className="button primary" type="submit" aria-label="Send message" disabled={busy || expired || !input.trim()}><ArrowUp size={20} /></button></form><p className="caption">AI: Amazon Bedrock. Clarification stays in this conversation; refreshing starts a new conversation.</p></div>
      </div><details className="alexa-how"><summary>How this works</summary><p>Browser → trusted Next.js route → CountOn orchestrator → MCP Streamable HTTP → CountOn services / Bedrock → Supabase</p><p>This demo uses the live CountOn MCP server and the Model Context Protocol over Streamable HTTP.</p><p>Built by CountOn for a hackathon. This is not an official Amazon Alexa+ simulator.</p></details>
    </main><footer className="alexa-footer">Calm monitoring. Clear signals.</footer></div>;
}
export default function AlexaPage() {
  const { loading, session } = useAuth(); const router = useRouter();
  useEffect(() => { if (!loading && !session) router.replace('/login'); }, [loading, session, router]);
  if (loading || !session) return <div className="auth-loading"><Logo /><p role="status">Restoring your CountOn session…</p></div>;
  return <AlexaConversation key={session.user.id} />;
}
