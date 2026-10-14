'use client';
import { useState } from 'react';
import { getSupabase } from '@/lib/supabase';
import { AMAZON_PROVIDER, AMAZON_SCOPE, authMessage, callbackUrl, safeAuthNext, amazonAuthorizationUrl } from '@/lib/auth/config';

export function AmazonSignIn({ link = false, onLinked }: { link?: boolean; onLinked?: () => void }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const enabled = process.env.NEXT_PUBLIC_AMAZON_AUTH_ENABLED === 'true';
  async function start() {
    setBusy(true); setError(null);
    try {
      const auth = getSupabase().auth;
      if (link) { const verified = await auth.getUser(); if (verified.error || !verified.data.user) throw new Error('Sign in again before linking Amazon.'); }
      const next = link ? '/settings' : safeAuthNext(new URLSearchParams(window.location.search).get('next'));
      const options = { redirectTo: callbackUrl(next) + (link ? '&mode=link' : ''), scopes: AMAZON_SCOPE, skipBrowserRedirect: true };
      const result = link ? await auth.linkIdentity({ provider: AMAZON_PROVIDER, options }) : await auth.signInWithOAuth({ provider: AMAZON_PROVIDER, options });
      if (result.error || !result.data.url) throw new Error(authMessage(result.error, 'Amazon sign-in is unavailable. Please try again.'));
      const url = amazonAuthorizationUrl(result.data.url, process.env.NEXT_PUBLIC_SUPABASE_URL ?? '', link);
      onLinked?.();
      window.location.assign(url);
    } catch { setError('Amazon sign-in is unavailable. Please sign in again or try later.'); setBusy(false); }
  }
  return <div><button type="button" className="button secondary full" disabled={busy || !enabled} onClick={start}>{busy ? 'Opening Amazon…' : link ? 'Link Amazon to this account' : 'Continue with Amazon'}</button>{!enabled && <p className="caption">Amazon sign-in is not configured yet.</p>}{link && <p className="caption">Linking requires signing in to Amazon. Accounts are never merged using an email match.</p>}{error && <p role="alert">{error}</p>}</div>;
}
