'use client';
import { useCallback, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { getSupabase } from '@/lib/supabase';
import { useResource } from '@/hooks/use-resource';
import { AMAZON_PROVIDER, authMessage, callbackUrl } from '@/lib/auth/config';
import { AmazonSignIn } from './amazon-sign-in';
import { ErrorState, Loading } from './ui';

export function AccountSecurity() {
  const load = useCallback(async () => {
    const { data, error } = await getSupabase().auth.getUser();
    if (error || !data.user) throw new Error('Please sign in again to manage login methods.');
    return data.user;
  }, []);
  const state = useResource(load);
  const [email, setEmail] = useState(''); const [busy, setBusy] = useState(false); const [message, setMessage] = useState<string | null>(null);
  const identity = state.data?.identities?.find(item => item.provider === AMAZON_PROVIDER);
  const canUnlink = !!identity && (state.data?.identities?.length ?? 0) > 1 && !!state.data?.email_confirmed_at;
  async function addEmail(event: FormEvent) {
    event.preventDefault(); if (busy) return; setBusy(true); setMessage(null);
    try {
      const current = await load();
      if (current.id !== state.data?.id) throw new Error('Account changed.');
      const { error } = await getSupabase().auth.updateUser({ email: email.trim() }, { emailRedirectTo: callbackUrl('/settings') });
      setMessage(error ? authMessage(error, 'This email could not be added. Use your existing account and link Amazon there; accounts are not merged.') : 'Check your email to verify this recovery address. Your CountOn account ID is unchanged.');
    } catch { setMessage('Sign in again before changing recovery details.'); }
    finally { setBusy(false); }
  }
  async function unlink() {
    if (busy || !canUnlink || !window.confirm('Unlink Amazon? Ensure you can sign in with your verified email/password first.')) return;
    setBusy(true); setMessage(null);
    try {
      const current = await load();
      const owned = current.identities?.find(item => item.provider === AMAZON_PROVIDER);
      if (current.id !== state.data?.id || !owned || (current.identities?.length ?? 0) < 2 || !current.email_confirmed_at) throw new Error('Recovery method unavailable.');
      const { error } = await getSupabase().auth.unlinkIdentity(owned);
      if (error) setMessage(authMessage(error, 'Amazon could not be unlinked. Keep your existing sign-in method.'));
      else { setMessage('Amazon unlinked. Your CountOn data is unchanged.'); state.reload(); }
    } catch { setMessage('Sign in again and verify a recovery method before unlinking.'); }
    finally { setBusy(false); }
  }
  return <section className="card"><h2>Sign-in and recovery</h2>{state.loading ? <Loading /> : state.error ? <ErrorState error={state.error} retry={state.reload} /> : <>
    <p>Email: {state.data?.email ?? 'No recovery email yet'}</p><p>{state.data?.email_confirmed_at ? 'Email verified' : 'Add and verify an email before relying on password recovery.'}</p>
    {identity ? <><p>Amazon linked to this CountOn account.</p><button className="button secondary" disabled={busy || !canUnlink} onClick={unlink}>Unlink Amazon</button>{!canUnlink && <p className="caption">Keep Amazon until another verified sign-in identity is available.</p>}</> : <AmazonSignIn link />}
    <form onSubmit={addEmail}><label htmlFor="account-email">Recovery email address</label><input id="account-email" type="email" autoComplete="email" value={email} onChange={event => setEmail(event.target.value)} required disabled={busy} /><button className="button secondary" disabled={busy}>Send verification</button></form>
    <p><Link href="/reset-password">Set or change password</Link> · <Link href="/forgot-password">Email recovery</Link></p><p className="caption">If you already have another CountOn account, sign in there and explicitly link Amazon. No expectation data is transferred between accounts.</p>
  </>}{message && <p role="status">{message}</p>}</section>;
}
