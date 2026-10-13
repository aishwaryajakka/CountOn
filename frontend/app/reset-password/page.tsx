'use client';
import { useState, type FormEvent } from 'react';
import Link from 'next/link';
import { getSupabase } from '@/lib/supabase';
import { useAuth } from '@/components/auth-provider';
import { authMessage } from '@/lib/auth/config';
import { Loading, Logo } from '@/components/ui';

export default function ResetPassword() {
  const { session, loading } = useAuth();
  const [password, setPassword] = useState(''); const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false); const [message, setMessage] = useState<string | null>(null);
  async function save(event: FormEvent) {
    event.preventDefault(); if (busy) return;
    if (password.length < 12 || password !== confirm) { setMessage('Use at least 12 characters and matching passwords.'); return; }
    setBusy(true); setMessage(null);
    try {
      const auth = getSupabase().auth;
      const verified = await auth.getUser();
      if (verified.error || verified.data.user?.id !== session?.user.id) { setMessage('Your recovery session expired. Request a new link.'); return; }
      const { error } = await auth.updateUser({ password });
      setMessage(error ? authMessage(error, 'Password could not be updated. Request a new link or try again.') : 'Password updated. You can return to CountOn.');
      if (!error) { setPassword(''); setConfirm(''); }
    } catch { setMessage('Password recovery is temporarily unavailable.'); }
    finally { setBusy(false); }
  }
  return <main className="login-page"><section className="card"><Logo /><h1>Choose a new password</h1>{loading ? <Loading /> : !session ? <p>Your recovery session ended. <Link href="/forgot-password">Request a new link</Link>.</p> : <form onSubmit={save}><label htmlFor="new-password">New password</label><input id="new-password" type="password" autoComplete="new-password" value={password} onChange={event => setPassword(event.target.value)} required disabled={busy} /><label htmlFor="confirm-password">Confirm password</label><input id="confirm-password" type="password" autoComplete="new-password" value={confirm} onChange={event => setConfirm(event.target.value)} required disabled={busy} /><button className="button primary" disabled={busy}>{busy ? 'Saving…' : 'Update password'}</button></form>}{message && <p role="status">{message}</p>}<Link href="/dashboard">Return to CountOn</Link></section></main>;
}
