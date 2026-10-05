'use client';

import { useEffect, useState, type FormEvent } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  ArrowRight,
  Eye,
  EyeOff,
  Mail,
  ShieldCheck,
} from 'lucide-react';

import { getSupabase } from '@/lib/supabase';
import { useAuth } from '@/components/auth-provider';
import { Logo } from '@/components/ui';

export default function Register() {
  const { session, loading, error: configError } = useAuth();
  const router = useRouter();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  const [visible, setVisible] = useState(false);
  const [visibleConfirm, setVisibleConfirm] = useState(false);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    if (!loading && session) {
      router.replace('/dashboard');
    }
  }, [loading, session, router]);

  async function signUp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    setError(null);
    setSuccess(false);

    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }

    if (password.length < 6) {
      setError('Password must be at least 6 characters.');
      return;
    }

    setBusy(true);

    try {
      const result = await getSupabase().auth.signUp({
        email: email.trim(),
        password,
      });

      if (result.error) {
        setError(result.error.message);
        setBusy(false);
        return;
      }

      /*
       * If email confirmation is enabled in Supabase,
       * session will usually be null here.
       */
      if (!result.data.session) {
        setSuccess(
          'Account created! Please check your email to confirm your account.'
        );
        setBusy(false);
        setPassword('');
        setConfirmPassword('');
        return;
      }

      // If email confirmation is disabled,
      // Supabase gives us a session immediately.
      setPassword('');
      setConfirmPassword('');

      router.replace('/dashboard');
    } catch {
      setError(
        'Registration is unavailable. Check your connection and try again.'
      );
      setBusy(false);
    }
  }

  return (
    <main className="login-page">
      <div className="login-frame">

        {/* LEFT SIDE */}
        <section className="login-story">
          <div className="login-story-top">
            <Logo light />

            <span className="story-pill">
              <span className="status-dot" />
              Quiet by design
            </span>
          </div>

          <div className="story-content">
            <span className="story-kicker">
              <ShieldCheck size={17} />
              Clarity for what matters
            </span>

            <h1>
              Know when reality stops matching what you expected.
            </h1>

            <p>
              CountOn watches what you’re counting on and lets you know
              when something changes.
            </p>

            <div className="story-example">
              <div>
                <span className="signal" />
                Less checking.
                <br />
                More peace of mind.
              </div>

              <p>
                Tell us what you expect. Follow the evidence. See what
                needs your attention.
              </p>
            </div>
          </div>

          <div className="story-footer">
            Calm monitoring.
            <br />
            Clear signals.
            <span>Made for real life.</span>
          </div>
        </section>

        {/* RIGHT SIDE */}
        <section className="login-form-panel">
          <div className="login-form-content">

            <span className="eyebrow">
              CREATE YOUR QUIET CORNER
            </span>

            <h2>Create your account</h2>

            <p>
              Sign up to start using CountOn.
            </p>

            <form onSubmit={signUp}>

              {/* EMAIL */}
              <label htmlFor="email">
                Email address
              </label>

              <div className="input-icon">
                <input
                  id="email"
                  type="email"
                  autoComplete="email"
                  placeholder="you@example.com"
                  value={email}
                  onChange={(event) =>
                    setEmail(event.target.value)
                  }
                  required
                  disabled={busy}
                />

                <Mail size={19} aria-hidden="true" />
              </div>

              {/* PASSWORD */}
              <label htmlFor="password">
                Password
              </label>

              <div className="input-icon">
                <input
                  id="password"
                  type={visible ? 'text' : 'password'}
                  autoComplete="new-password"
                  placeholder="Create a password"
                  value={password}
                  onChange={(event) =>
                    setPassword(event.target.value)
                  }
                  required
                  disabled={busy}
                />

                <button
                  className="icon-button"
                  type="button"
                  aria-label={
                    visible
                      ? 'Hide password'
                      : 'Show password'
                  }
                  onClick={() =>
                    setVisible((value) => !value)
                  }
                >
                  {visible ? (
                    <EyeOff size={19} />
                  ) : (
                    <Eye size={19} />
                  )}
                </button>
              </div>

              {/* CONFIRM PASSWORD */}
              <label htmlFor="confirmPassword">
                Confirm password
              </label>

              <div className="input-icon">
                <input
                  id="confirmPassword"
                  type={visibleConfirm ? 'text' : 'password'}
                  autoComplete="new-password"
                  placeholder="Confirm your password"
                  value={confirmPassword}
                  onChange={(event) =>
                    setConfirmPassword(event.target.value)
                  }
                  required
                  disabled={busy}
                />

                <button
                  className="icon-button"
                  type="button"
                  aria-label={
                    visibleConfirm
                      ? 'Hide password'
                      : 'Show password'
                  }
                  onClick={() =>
                    setVisibleConfirm((value) => !value)
                  }
                >
                  {visibleConfirm ? (
                    <EyeOff size={19} />
                  ) : (
                    <Eye size={19} />
                  )}
                </button>
              </div>

              {/* ERROR */}
              {(error || configError) && (
                <p
                  role="alert"
                  className="inline-error"
                >
                  {error || configError}
                </p>
              )}

              {/* SUCCESS */}
              {success && (
                <p
                  role="status"
                  className="inline-success"
                >
                  {success}
                </p>
              )}

              {/* SUBMIT */}
              <button
                className="button primary full"
                type="submit"
                disabled={
                  busy ||
                  loading ||
                  !!configError?.startsWith('Add the public')
                }
              >
                {busy
                  ? 'Creating your account…'
                  : 'Create account'}
                <ArrowRight size={18} />
              </button>
            </form>

            <div className="login-reassurance">
              <ShieldCheck size={17} />
              <span>
                A personal space for what you’re counting on.
              </span>
            </div>

            {/* LOGIN LINK */}
            <p className="caption login-help">
              Already have an account?{' '}
              <Link href="/login">
                Sign in
              </Link>
            </p>

          </div>

          <div className="login-bottom">
            Real life. Clear answers.
          </div>
        </section>

      </div>
    </main>
  );
}