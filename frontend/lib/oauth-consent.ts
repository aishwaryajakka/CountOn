/** Only identifiers come from the URL. Supabase owns PKCE, codes and tokens. */
export function authorizationId(value: string | null): string {
  if (!value || !/^[A-Za-z0-9_-]{16,128}$/.test(value)) throw new Error('Invalid authorization request.');
  return value;
}
export function consentReturnPath(value: string | null): string {
  try {
    const url = new URL(value ?? '', 'https://counton.invalid');
    if (url.origin !== 'https://counton.invalid' || url.pathname !== '/oauth/consent' || url.hash) throw new Error();
    if ([...url.searchParams.keys()].some(key => key !== 'authorization_id') || url.searchParams.getAll('authorization_id').length !== 1) throw new Error();
    return '/oauth/consent?authorization_id=' + encodeURIComponent(authorizationId(url.searchParams.get('authorization_id')));
  } catch { return '/dashboard'; }
}
export function safeAlexaRedirect(value: string, registered: string[]): string {
  const url = new URL(value);
  if (url.protocol !== 'https:' || url.username || url.password || url.hash) throw new Error('Invalid authorization redirect.');
  const base = url.origin + url.pathname;
  if (!registered.includes(base) || url.searchParams.has('access_token') || url.searchParams.has('refresh_token')) throw new Error('Invalid authorization redirect.');
  if ([...url.searchParams.keys()].some(key => !['code','state','error','error_description'].includes(key))) throw new Error('Invalid authorization redirect.');
  if ([...url.searchParams.keys()].some(key => url.searchParams.getAll(key).length !== 1)) throw new Error('Invalid authorization redirect.');
  return url.href;
}
