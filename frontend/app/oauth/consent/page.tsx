'use client';
import { Suspense, useEffect, useState, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import type { OAuthAuthorizationDetails } from '@supabase/supabase-js';
import { getSupabase } from '@/lib/supabase';
import { useAuth } from '@/components/auth-provider';
import { authorizationId, safeAlexaRedirect } from '@/lib/oauth-consent';
import { Logo } from '@/components/ui';

function Consent() {
  const query = useSearchParams(); const router = useRouter();
  const { session, loading } = useAuth();
  const [details, setDetails] = useState<OAuthAuthorizationDetails | null>(null);
  const [error, setError] = useState<string | null>(null); const [busy, setBusy] = useState(false);
  const id = query.get('authorization_id');
  const clientId = process.env.NEXT_PUBLIC_ALEXA_OAUTH_CLIENT_ID;
  const redirects = useMemo(() => (process.env.NEXT_PUBLIC_ALEXA_REDIRECT_URIS ?? '').split(',').map(value => value.trim()).filter(Boolean), []);
  // OAuth IDs/codes must not escape as Referer headers to external pages.
  useEffect(() => {
    const meta = document.createElement('meta'); meta.name = 'referrer'; meta.content = 'no-referrer';
    document.head.appendChild(meta); return () => meta.remove();
  }, []);
  useEffect(() => {
    if (loading) return;
    let cancelled = false;
    async function load() {
      try {
        const checked = authorizationId(id);
        if (!clientId || !redirects.length) throw new Error();
        if (!session) { router.replace('/login?next=' + encodeURIComponent('/oauth/consent?authorization_id=' + checked)); return; }
        const auth = getSupabase().auth;
        const verified = await auth.getUser();
        if (verified.error || verified.data.user?.id !== session.user.id) throw new Error();
        const result = await auth.oauth.getAuthorizationDetails(checked);
        if (result.error || !result.data || cancelled) { if (!cancelled) throw new Error(); return; }
        if ('redirect_url' in result.data) { window.location.assign(safeAlexaRedirect(result.data.redirect_url, redirects)); return; }
        const data = result.data;
        if (data.client.id !== clientId || data.user.id !== session.user.id || data.authorization_id !== checked
          || !redirects.includes(data.redirect_uri) || data.scope.split(' ').some(scope => !['openid','email','profile'].includes(scope))) throw new Error();
        setDetails(data);
      } catch { if (!cancelled) setError('This linking request is unavailable or invalid. Start account linking again in Alexa.'); }
    }
    void load(); return () => { cancelled = true; };
    // Registered configuration is compiled into this page; session changes revoke loaded consent.
  }, [id, session, loading, router, clientId, redirects]);
  async function decide(approve: boolean) {
    if (!details || busy || !session) return;
    setBusy(true); setError(null);
    try {
      const auth = getSupabase().auth;
      const current = await auth.getUser();
      if (current.error || current.data.user?.id !== details.user.id) throw new Error();
      const result = approve ? await auth.oauth.approveAuthorization(details.authorization_id, { skipBrowserRedirect: true })
        : await auth.oauth.denyAuthorization(details.authorization_id, { skipBrowserRedirect: true });
      if (result.error || !result.data) throw new Error();
      window.location.assign(safeAlexaRedirect(result.data.redirect_url, redirects));
    } catch { setError('We could not complete account linking. Start again in Alexa.'); setBusy(false); }
  }
  return <main className="login-page"><section className="card" style={{ maxWidth: 520, margin: '4rem auto', padding: '2rem' }}><Logo /><h1>Link CountOn to Alexa</h1>
    {error ? <p role="alert">{error}</p> : (!details || details.user.id !== session?.user.id) ? <p>Checking your secure linking request…</p> : <>
      <p>Alexa can list and read your CountOn expectations, help you compile new ones, and explain recorded mismatches.</p>
      <p>New expectations require your confirmation. CountOn evaluates evidence with deterministic code.</p>
      <p className="caption">Signed in as {details.user.email}. Requested identity scopes: {details.scope}.</p>
      <button className="button primary" disabled={busy} onClick={() => void decide(true)}>Allow Alexa</button>{' '}
      <button className="button secondary" disabled={busy} onClick={() => void decide(false)}>Deny</button>
    </>}
  </section></main>;
}
export default function ConsentPage() { return <Suspense fallback={<p>Loading account linking…</p>}><Consent /></Suspense>; }
