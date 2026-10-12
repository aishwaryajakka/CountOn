'use client';
import { useState } from 'react';
import { useResource } from '@/hooks/use-resource';
import { monitoring, type Preferences } from '@/lib/monitoring';
import { ErrorState, Loading } from './ui';
const load = (signal: AbortSignal) => monitoring.preferences(signal);
export function NotificationPreferences() {
  const state = useResource(load);
  const [draft, setDraft] = useState<Preferences | null>(null); const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  const prefs = draft ?? state.data;
  return <section className="card"><h2>Notification preferences</h2>{state.loading ? <Loading /> : state.error ? <ErrorState error={state.error} retry={state.reload} /> : prefs && <form onSubmit={async e => {
    e.preventDefault(); setBusy(true); setError(null);
    try { await monitoring.savePreferences(prefs); setDraft(null); state.reload(); }
    catch (err) { setError(err instanceof Error ? err.message : 'Preferences could not be saved.'); }
    finally { setBusy(false); }
  }}>{([['mismatch_enabled', 'Mismatch alerts'], ['deadline_enabled', 'Upcoming deadline reminders'], ['connection_enabled', 'Connection health warnings'], ['email_enabled', 'Email me (opt-in)'], ['quiet_enabled', 'Quiet hours for email']] as const).map(([key, label]) => <label key={key}><input type="checkbox" checked={prefs[key]} onChange={e => setDraft({ ...prefs, [key]: e.target.checked })} />{label}</label>)}
  <p className="caption">Email requires deployment configuration and goes only to your confirmed Supabase account email. In-app alerts remain available during quiet hours.</p>
  <label>Timezone<input value={prefs.timezone} onChange={e => setDraft({ ...prefs, timezone: e.target.value })} placeholder="America/Chicago" /></label>
  <label>Quiet hours start (0–23)<input type="number" min={0} max={23} value={prefs.quiet_start_hour} onChange={e => setDraft({ ...prefs, quiet_start_hour: Number(e.target.value) })} /></label>
  <label>Quiet hours end (0–23)<input type="number" min={0} max={23} value={prefs.quiet_end_hour} onChange={e => setDraft({ ...prefs, quiet_end_hour: Number(e.target.value) })} /></label>
  <button className="button secondary" disabled={busy}>Save preferences</button></form>}{error && <p role="alert" className="inline-error">{error}</p>}</section>;
}
