import { NextRequest, NextResponse } from 'next/server';
import { authOrigin, safeAuthNext } from '@/lib/auth/config';
import { serverAuth, transferCookies } from '@/lib/auth/server';

export const dynamic = 'force-dynamic';
export async function GET(request: NextRequest) {
  let origin: string;
  try { origin = authOrigin(request.nextUrl.origin); } catch { return new NextResponse('Authentication configuration is unavailable.', { status: 503, headers: { 'Cache-Control': 'no-store' } }); }
  const response = NextResponse.next();
  const fail = () => transferCookies(NextResponse.next(), NextResponse.redirect(`${origin}/login?auth_error=callback`));
  const params = request.nextUrl.searchParams;
  const code = params.get('code');
  // Supabase owns upstream state/PKCE. Reject flattened tokens and duplicate or
  // unexpected parameters; no user_id/provider identity from URL is trusted.
  if (!code || code.length > 2048 || [...params.keys()].some(key => !['code', 'next', 'sb_flow_id', 'mode'].includes(key) || params.getAll(key).length !== 1)) return fail();
  try {
    const auth = serverAuth(request, response).auth;
    const linking = params.get('mode') === 'link';
    if (params.has('mode') && !linking) return fail();
    const previous = linking ? await auth.getUser() : null;
    if (linking && (previous?.error || !previous?.data.user)) return fail();
    const flowId = params.get('sb_flow_id');
    const { data, error } = await auth.exchangeCodeForSession(code, flowId ? { flowId } : undefined);
    if (error || !data.session?.access_token || !data.user || !/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(data.user.id ?? '')) return fail();
    const verified = await auth.getUser();
    if (verified.error || verified.data.user?.id !== data.user.id || verified.data.user?.is_anonymous || (linking && verified.data.user?.id !== previous?.data.user?.id)) return fail();
    // Recovery intent comes from SDK PKCE storage, never next=reset-password.
    const destination = 'redirectType' in data && data.redirectType === 'recovery' ? '/reset-password' : safeAuthNext(params.get('next'));
    return transferCookies(response, NextResponse.redirect(origin + destination));
  } catch { return fail(); }
}
