import { consentReturnPath } from '@/lib/oauth-consent';

export const AMAZON_PROVIDER = 'custom:amazon' as const;
export const AMAZON_SCOPE = 'profile:user_id';
export function supabaseConfig() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY;
  if (!url || !key) throw new Error('Add the public Supabase URL and publishable key to frontend/.env.local, then restart the frontend.');
  let privileged = key.startsWith('sb_secret_');
  try { privileged ||= JSON.parse(atob(key.split('.')[1].replaceAll('-', '+').replaceAll('_', '/'))).role === 'service_role'; } catch { /* Publishable keys are not JWTs. */ }
  if (privileged) throw new Error('Use a Supabase publishable key, never a privileged key.');
  return { url, key };
}
export function authOrigin(fallback: string): string {
  const configured = process.env.NEXT_PUBLIC_APP_URL;
  const url = new URL(configured ?? fallback);
  if (url.username || url.password || url.search || url.hash || url.pathname !== '/' ||
      (url.protocol !== 'https:' && !(process.env.NODE_ENV !== 'production' && url.protocol === 'http:' && ['localhost', '127.0.0.1'].includes(url.hostname))) ||
      (process.env.NODE_ENV === 'production' && !configured)) throw new Error('Configure the exact HTTPS NEXT_PUBLIC_APP_URL.');
  return url.origin;
}
export function safeAuthNext(value: string | null): string {
  if (value?.startsWith('/oauth/consent')) return consentReturnPath(value);
  return value && /^(\/dashboard|\/settings|\/alexa|\/expectations(?:\/[0-9a-f-]{36})?)$/.test(value) ? value : '/dashboard';
}
export function callbackUrl(next = '/dashboard'): string {
  const origin = authOrigin(window.location.origin);
  if (origin !== window.location.origin) throw new Error('Open CountOn at its configured application address.');
  return `${origin}/auth/callback?next=${encodeURIComponent(safeAuthNext(next))}`;
}
export function authMessage(error: { code?: string; status?: number } | null, fallback: string): string {
  if (error?.status === 429 || error?.code?.includes('rate_limit')) return 'Too many attempts. Please wait a moment and try again.';
  if (error?.code === 'email_not_confirmed') return 'Confirm your email before signing in. You can request another confirmation below.';
  if (error?.code === 'weak_password') return 'Use a stronger password that meets this project’s password requirements.';
  if (error?.code === 'same_password') return 'Choose a password different from your current password.';
  if (error?.code === 'invalid_credentials') return 'The email or password is incorrect.';
  if (error?.code === 'identity_already_exists') return 'That Amazon identity already belongs to another account. Sign in to that account; accounts are not merged.';
  return fallback; // Never echo provider errors, URLs, credentials or enumeration details.
}

export function amazonAuthorizationUrl(value: string, projectUrl: string, linking: boolean): string {
  const url = new URL(value); const project = new URL(projectUrl);
  if ([...url.searchParams.keys()].some(key => url.searchParams.getAll(key).length !== 1) || url.username || url.password || url.hash || url.searchParams.has('access_token') || url.searchParams.has('refresh_token')) throw new Error('Invalid authorization redirect.');
  if (!linking && url.origin === project.origin && url.pathname === '/auth/v1/authorize' && url.searchParams.get('provider') === AMAZON_PROVIDER) return url.href;
  // linkIdentity performs an authenticated Supabase request and returns the
  // actual provider URL, unlike signInWithOAuth's Supabase authorize URL.
  if (linking && url.origin === 'https://www.amazon.com' && url.pathname === '/ap/oa' &&
      url.searchParams.get('response_type') === 'code' && url.searchParams.get('scope') === AMAZON_SCOPE &&
      url.searchParams.get('redirect_uri') === project.origin + '/auth/v1/callback' &&
      url.searchParams.get('code_challenge_method') === 'S256' &&
      /^[A-Za-z0-9_-]{43}$/.test(url.searchParams.get('code_challenge') ?? '') &&
      !!url.searchParams.get('state') && !!url.searchParams.get('client_id')) return url.href;
  throw new Error('Invalid authorization redirect.');
}
