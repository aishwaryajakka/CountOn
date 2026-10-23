'use client';
import { useState, type FormEvent } from 'react';
import Link from 'next/link';
import { getSupabase } from '@/lib/supabase';
import { authMessage, callbackUrl } from '@/lib/auth/config';
import { Logo } from '@/components/ui';

export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  async function send(event: FormEvent) {
    event.preventDefault(); if (busy) return; setBusy(true); setMessage(null);
    try {
      const { error } = await getSupabase().auth.resetPasswordForEmail(email.trim(), { redirectTo: callbackUrl() });
      setMessage(error ? authMessage(error, 'Recovery is unavailable. Try again later.') : 'If this account supports email recovery, a reset link has been sent. Open it in this browser.');
    } catch { setMessage('Recovery is unavailable. Try again later.'); }
    finally { setBusy(false); }
  }
  return <main className="login-page"><section className="card"><Logo /><h1>Reset your password</h1><p>We’ll send a secure Supabase recovery link.</p><form onSubmit={send}><label htmlFor="recovery-email">Email address</label><input id="recovery-email" type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} required disabled={busy} /><button className="button primary" disabled={busy}>{busy ? 'Sending…' : 'Send reset link'}</button></form>{message && <p role="status">{message}</p>}<Link href="/login">Back to sign in</Link></section></main>;
}
