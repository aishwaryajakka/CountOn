'use client';
import { useEffect, useRef, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ArrowLeft, ArrowUp, Check, MessageCircle, Radio, Volume2 } from 'lucide-react';
import { useAuth, useIdentity } from '@/components/auth-provider';
import { Logo } from '@/components/ui';
import { requestMcp, McpClientError } from '@/lib/mcp/client';
import { conversationSchema, explanationSchema, errorMessages, type McpErrorCode } from '@/lib/mcp/contracts';
import type { McpAction, McpMeta, McpResponse } from '@/lib/mcp/contracts';
import { matchExpectations, routeAlexaPrompt, type McpExpectation } from '@/lib/alexa-router';

type Message = { id: number; role: 'user' | 'assistant'; text: string; rows?: McpExpectation[]; traces?: McpMeta[]; saved?: string; error?: boolean; aiTrace?: string };
const starters = ['What am I counting on?', 'Tell me about my electricity bill', "I'm counting on my grocery bill staying under $120 this week"];
const label = (value: string) => value.replace(/_/g, ' ');
function structured(response: McpResponse) {
  if (!('result' in response)) throw new McpClientError('MCP_PROTOCOL_ERROR');
  return response.result.structuredContent;
}
function Trace({ meta }: { meta: McpMeta }) {
  return <details className="alexa-trace"><summary>MCP → {meta.tool ?? 'tools/list'}</summary><dl><div><dt>Transport</dt><dd>Streamable HTTP</dd></div><div><dt>Initialize</dt><dd>{meta.initialized ? 'success' : 'not completed'}</dd></div><div><dt>Tools discovered</dt><dd>{meta.toolsDiscovered ? 'yes' : 'no'}</dd></div>{meta.tool && <div><dt>Tool</dt><dd>{meta.tool}</dd></div>}<div><dt>Duration</dt><dd>{meta.durationMs} ms</dd></div></dl></details>;
}
function AlexaConversation() {
  const { session } = useAuth(); const { firstName } = useIdentity();
  const [connection, setConnection] = useState<'checking' | 'connected' | 'unavailable'>('checking');
  const [messages, setMessages] = useState<Message[]>([]); const [input, setInput] = useState('');
  const [clarification, setClarification] = useState<string | null>(null);
  const [focused, setFocused] = useState<McpExpectation | null>(null);
  const [selection, setSelection] = useState<{ kind: 'detail' | 'explain'; ids: string[] } | null>(null);
  const [busy, setBusy] = useState(false); const [expired, setExpired] = useState(false);
  const [voice, setVoice] = useState(false); const [canSpeak] = useState(() => typeof window !== 'undefined' && 'speechSynthesis' in window);
  const nextId = useRef(0); const bottom = useRef<HTMLDivElement>(null); const inFlight = useRef(false);
  const token = session?.access_token;
  useEffect(() => () => { if ('speechSynthesis' in window) window.speechSynthesis.cancel(); }, []);
  useEffect(() => {
    let active = true;
    requestMcp(token, { action: 'list_tools' }).then(response => {
      if (active) setConnection(response.meta.initialized && response.meta.toolsDiscovered && 'tools' in response && ['capture_expectation', 'get_expectation', 'list_expectations'].every(name => response.tools.some(tool => tool.name === name)) ? 'connected' : 'unavailable');
    }).catch(error => { if (active) { setConnection('unavailable'); if (error instanceof McpClientError && ['AUTH_EXPIRED', 'AUTH_REQUIRED'].includes(error.code)) setExpired(true); } });
    return () => { active = false; };
  }, [token]);
  useEffect(() => { bottom.current?.scrollIntoView?.({ behavior: window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth', block: 'nearest' }); }, [messages, busy]);
  async function send(text: string) {
    if (!text.trim() || inFlight.current || expired) return;
    inFlight.current = true; setBusy(true); setInput('');
    setMessages(previous => [...previous, { id: nextId.current++, role: 'user', text: text.trim() }]);
    const traces: McpMeta[] = [];
    let intent = routeAlexaPrompt(text);
    const resolvingSelection = selection && intent.kind === 'clarify';
    if (resolvingSelection) intent = { kind: selection.kind, topic: text.trim() };
    else setSelection(null);
    let aiTrace: string | undefined;
    let captureAttempted = false;
    let reply: Omit<Message, 'id' | 'role'>;
    const call = async (action: McpAction) => { const response = await requestMcp(token, action); traces.push(...(response.meta.steps ?? [response.meta])); setConnection(response.meta.initialized && response.meta.toolsDiscovered ? 'connected' : 'unavailable'); return structured(response); };
    try {
      if (intent.kind === 'capture' || (clarification && intent.kind === 'clarify')) {
        setFocused(null); // An incomplete new expectation is not a persisted referent.
        captureAttempted = true; // Server may save before a network response is lost.
        const response = await call({ action: 'converse', text: text.trim(), state: clarification, turn_id: crypto.randomUUID(), timezone: Intl.DateTimeFormat().resolvedOptions().timeZone, locale: navigator.language.match(/^[a-z]{2}(?:-[A-Z]{2})?$/) ? navigator.language : null });
        const parsed = conversationSchema.safeParse(response);
        if (!parsed.success) throw new McpClientError('MCP_PROTOCOL_ERROR');
        const compiled = parsed.data;
        aiTrace = compiled.bedrock_used ? `Bedrock → ${compiled.status === 'clarification' ? 'clarification' : 'compile'}` : undefined;
        if (compiled.status === 'clarification' && compiled.state) {
          setClarification(compiled.state); reply = { text: compiled.message };
        } else {
          setClarification(null);
          if (compiled.status === 'compiled' && compiled.saved) {
            setFocused(compiled.saved);
            reply = { text: compiled.message, rows: [compiled.saved], saved: compiled.saved.id };
          } else if (compiled.status === 'error') {
            const code = compiled.code && Object.hasOwn(errorMessages, compiled.code) ? compiled.code as McpErrorCode : 'COMPILER_INVALID_OUTPUT';
            reply = { text: errorMessages[code], error: true };
          } else reply = { text: compiled.message };
        }
      } else if (intent.kind === 'clarify') reply = { text: intent.message };
      else if (intent.kind === 'explain' && !intent.topic && !focused) {
        setSelection({ kind: 'explain', ids: [] });
        reply = { text: 'Which expectation do you mean? Tell me part of its claim.' };
      }
      else {
        const result = await call({ action: 'call_tool', tool: 'list_expectations', arguments: { request: { limit: 50, offset: 0 } } });
        const rows = result.expectations as McpExpectation[];
        if (intent.kind === 'list') reply = rows.length ? { text: `Here ${rows.length === 1 ? 'is your expectation' : `are ${rows.length === 50 ? 'the first ' : ''}${rows.length} expectations`}. These are their current recorded statuses.`, rows } : { text: "You're not counting on anything yet." };
        else {
          const candidates = resolvingSelection && selection?.ids.length ? rows.filter(row => selection.ids.includes(row.id)) : rows;
          const matches = intent.kind === 'explain' && !intent.topic
            ? rows.filter(row => row.id === focused?.id)
            : matchExpectations(intent.topic, candidates);
          if (!matches.length) {
            setFocused(null); setSelection(null);
            reply = { text: "I couldn't find an expectation about that." + (rows.length === 50 ? ' I searched the first 50 expectations.' : '') };
          }
          else if (matches.length > 1) {
            setFocused(null);
            setSelection({ kind: intent.kind, ids: matches.map(row => row.id) });
            reply = { text: 'I found more than one expectation about that. Could you use a more specific part of its claim?', rows: matches };
          }
          else {
            setSelection(null); setFocused(matches[0]);
            if (intent.kind === 'explain') {
              const output = await call({ action: 'call_tool', tool: 'explain_expectation_mismatch', arguments: { request: { expectation_id: matches[0].id } } });
              const parsed = explanationSchema.safeParse(output);
              if (!parsed.success) throw new McpClientError('MCP_PROTOCOL_ERROR');
              const explanation = parsed.data;
              aiTrace = explanation.bedrock_used ? 'Amazon Bedrock → grounded explanation' : 'Deterministic evaluation → recorded summary';
              reply = { text: explanation.message };
            } else {
            const row = await call({ action: 'call_tool', tool: 'get_expectation', arguments: { request: { expectation_id: matches[0].id } } });
            reply = { text: 'Here’s what CountOn has recorded. This MCP response contains the expectation’s status, not its evidence or evaluation history.', rows: [row as unknown as McpExpectation] };
            }
          }
        }
      }
    } catch (error) {
      const code = error instanceof McpClientError ? error.code : 'UNKNOWN';
      if (['AUTH_REQUIRED', 'AUTH_EXPIRED'].includes(code)) { setClarification(null); setExpired(true); reply = { text: 'Your CountOn session expired. Please sign in again.', error: true }; }
      else if (code === 'MCP_UNAVAILABLE') { setConnection('unavailable'); reply = { text: 'CountOn is temporarily unavailable.', error: true }; }
      else if (['CLARIFICATION_EXPIRED', 'CLARIFICATION_UNAVAILABLE', 'BEDROCK_DISABLED', 'BEDROCK_UNAVAILABLE', 'BEDROCK_THROTTLED', 'COMPILER_INVALID_OUTPUT', 'NO_EXPECTATION'].includes(code)) { setClarification(null); reply = { text: errorMessages[code as McpErrorCode], error: true }; }
      else if (code === 'TOOL_VALIDATION_ERROR') reply = { text: 'I need a little more information before I can save that.', error: true };
      else reply = { text: captureAttempted ? "I couldn't save that expectation yet. A connection failure can happen after a save, so check CountOn before trying again." : 'I couldn’t complete that request just now. Please try again.', error: true };
    }
    setMessages(previous => [...previous, { ...reply, traces, aiTrace, role: 'assistant', id: nextId.current++ }]);
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
          {messages.map(message => <article key={message.id} className={`alexa-message ${message.role} ${message.error ? 'is-error' : ''}`}><span className="alexa-speaker">{message.role === 'user' ? 'You' : 'CountOn'}</span><p>{message.text}</p>{message.rows && <div className="alexa-records">{message.rows.map(row => <div key={row.id} className="alexa-record"><strong>{row.claim}</strong><span className={`alexa-record-status ${row.status}`}>{label(row.status)}</span><dl><div><dt>Type</dt><dd>{label(row.type)}</dd></div><div><dt>Metric</dt><dd>{row.metric ?? 'Not specified'}</dd></div><div><dt>Created</dt><dd>{new Date(row.created_at).toLocaleDateString()}</dd></div></dl></div>)}</div>}{message.saved && <div className="alexa-saved"><span><Check size={16} />Saved to CountOn</span><Link className="button primary" href={`/expectations/${encodeURIComponent(message.saved)}`}>View in CountOn</Link></div>}{message.aiTrace && <p className="caption">{message.aiTrace}</p>}{message.traces?.map((trace, index) => <Trace key={index} meta={trace} />)}</article>)}
          {busy && <div role="status" className="alexa-working"><span className="status-dot" />Checking with CountOn…</div>}<div ref={bottom} /></div>
        {expired && <div role="alert" className="alexa-auth-error">Your CountOn session expired. <Link href="/login">Please sign in again.</Link></div>}
        <div className="alexa-compose-area"><div className="alexa-starters" aria-label="Starter prompts">{starters.map(prompt => <button key={prompt} disabled={busy || expired} onClick={() => void send(prompt)}>{prompt}</button>)}</div><form onSubmit={submit} className="alexa-composer"><label htmlFor="alexa-input" className="sr-only">Message CountOn</label><textarea id="alexa-input" rows={2} maxLength={2000} value={input} onChange={event => setInput(event.target.value)} placeholder="Tell CountOn what’s on your mind…" disabled={busy || expired} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); void send(input); } }} /><button className="button primary" type="submit" aria-label="Send message" disabled={busy || expired || !input.trim()}><ArrowUp size={20} /></button></form><p className="caption">AI: Amazon Bedrock. Clarification stays in this conversation; refreshing starts a new conversation.</p></div>
      </div><details className="alexa-how"><summary>How this works</summary><p>Browser → Next.js MCP client → Streamable HTTP → CountOn MCP → Bedrock interpretation / CountOn services → Supabase</p><p>This demo uses the live CountOn MCP server and the Model Context Protocol over Streamable HTTP.</p><p>Built by CountOn for a hackathon. This is not an official Amazon Alexa+ simulator.</p></details>
    </main><footer className="alexa-footer">Calm monitoring. Clear signals.</footer></div>;
}
export default function AlexaPage() {
  const { loading, session } = useAuth(); const router = useRouter();
  useEffect(() => { if (!loading && !session) router.replace('/login'); }, [loading, session, router]);
  if (loading || !session) return <div className="auth-loading"><Logo /><p role="status">Restoring your CountOn session…</p></div>;
  return <AlexaConversation key={session.user.id} />;
}
