import { NextRequest, NextResponse } from 'next/server';
import { serverAuth, transferCookies } from '@/lib/auth/server';
import { authOrigin, safeAuthNext } from '@/lib/auth/config';

export async function proxy(request: NextRequest) {
  const response = NextResponse.next({ request });
  response.headers.set('Cache-Control', 'private, no-store');
  try {
    const { data, error } = await serverAuth(request, response).auth.getUser();
    if (!error && data.user && !data.user.is_anonymous && data.user.aud === 'authenticated') return transferCookies(response, NextResponse.next({ request }));
  } catch { /* Fail closed, never log cookies or Auth exceptions. */ }
  let url: URL;
  try { url = new URL('/login', authOrigin(request.nextUrl.origin)); } catch { return new NextResponse('Authentication configuration is unavailable.', { status: 503, headers: { 'Cache-Control': 'no-store' } }); }
  const next = safeAuthNext(request.nextUrl.pathname + request.nextUrl.search);
  url.pathname = '/login'; url.search = ''; url.searchParams.set('next', next);
  return transferCookies(response, NextResponse.redirect(url));
}
export const config = { matcher: ['/dashboard/:path*', '/quality/:path*', '/expectations/:path*', '/integrations/:path*', '/activity/:path*', '/notifications/:path*', '/settings/:path*', '/alexa/:path*', '/oauth/consent/:path*'] };
