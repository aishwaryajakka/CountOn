import { createServerClient } from '@supabase/ssr';
import { NextRequest, NextResponse } from 'next/server';
import { supabaseConfig } from './config';

/** Request-scoped client; never share an SSR client or trust getSession for auth. */
export function serverAuth(request: NextRequest, response: NextResponse) {
  const { url, key } = supabaseConfig();
  return createServerClient(url, key, {
    global: { fetch: (input, init) => fetch(input, { ...init, cache: 'no-store', signal: init?.signal ? AbortSignal.any([init.signal, AbortSignal.timeout(10_000)]) : AbortSignal.timeout(10_000) }) },
    cookies: {
      getAll: () => request.cookies.getAll(),
      setAll: cookies => { for (const { name, value, options } of cookies) { request.cookies.set(name, value); response.cookies.set(name, value, { ...options, sameSite: 'lax', secure: process.env.NODE_ENV === 'production' }); } },
    },
  });
}
export function transferCookies(from: NextResponse, to: NextResponse) {
  for (const cookie of from.cookies.getAll()) to.cookies.set(cookie);
  to.headers.set('Cache-Control', 'private, no-store');
  to.headers.set('Referrer-Policy', 'no-referrer');
  return to;
}
