'use client';
import { useEffect, useState, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { ArrowRight, Eye, EyeOff, Mail, ShieldCheck } from 'lucide-react';
import { getSupabase } from '@/lib/supabase';
import { useAuth } from '@/components/auth-provider';
import { Logo } from '@/components/ui';

export default function Login() {
  const { session, loading, error: configError } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState(''); const [password, setPassword] = useState('');
  const [visible, setVisible] = useState(false); const [busy, setBusy] = useState(false); const [error, setError] = useState<string | null>(null);
  useEffect(() => { if (!loading && session) router.replace('/dashboard'); }, [loading, session, router]);
  async function signIn(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(null); setBusy(true);
    try {
      const result = await getSupabase().auth.signInWithPassword({ email: email.trim(), password });
      if (result.error) { setError(result.error.message); setBusy(false); return; }
      setPassword(''); router.replace('/dashboard');
    } catch { setError('Sign-in is unavailable. Check your connection and try again.'); setBusy(false); }
  }
  return <main className="login-page"><div className="login-frame"><section className="login-story"><div className="login-story-top"><Logo light /><span className="story-pill"><span className="status-dot" />Quiet by design</span></div><div className="story-content"><span className="story-kicker"><ShieldCheck size={17} />Clarity for what matters</span><h1>Know when reality stops matching what you expected.</h1><p>CountOn watches what you’re counting on and lets you know when something changes.</p><div className="story-example"><div><span className="signal" />Less checking.<br />More peace of mind.</div><p>Tell us what you expect. Follow the evidence. See what needs your attention.</p></div></div><div className="story-footer">Calm monitoring.<br />Clear signals.<span>Made for real life.</span></div></section>
    <section className="login-form-panel"><div className="login-form-content"><span className="eyebrow">WELCOME TO YOUR QUIET CORNER</span><h2>Welcome back</h2><p>Sign in to continue to CountOn.</p><form onSubmit={signIn}><label htmlFor="email">Email address</label><div className="input-icon"><input id="email" type="email" autoComplete="username" placeholder="you@example.com" value={email} onChange={event => setEmail(event.target.value)} required disabled={busy} /><Mail size={19} aria-hidden="true" /></div><label htmlFor="password">Password</label><div className="input-icon"><input id="password" type={visible ? 'text' : 'password'} autoComplete="current-password" placeholder="Enter your password" value={password} onChange={event => setPassword(event.target.value)} required disabled={busy} /><button className="icon-button" type="button" aria-label={visible ? 'Hide password' : 'Show password'} onClick={() => setVisible(value => !value)}>{visible ? <EyeOff size={19} /> : <Eye size={19} />}</button></div>{(error || configError) && <p role="alert" className="inline-error">{error || configError}</p>}<button className="button primary full" type="submit" disabled={busy || loading || !!configError?.startsWith('Add the public')}>{busy ? 'Signing you in…' : 'Sign in to CountOn'}<ArrowRight size={18} /></button></form><div className="login-reassurance"><ShieldCheck size={17} /><span>A personal space for what you’re counting on.</span></div><p className="caption login-help">Need access? Ask your CountOn team for an account.</p></div><div className="login-bottom">Real life. Clear answers.</div></section></div></main>;
}
