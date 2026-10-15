import { createBrowserClient } from '@supabase/ssr';
import type { SupabaseClient } from '@supabase/supabase-js';
import { supabaseConfig } from './auth/config';

let client: SupabaseClient | undefined;
export function getSupabase(): SupabaseClient {
  const { url, key } = supabaseConfig();
  // Official cookie-backed PKCE storage. URL codes are exchanged only by our
  // server callback, never by a second browser handler or an implicit token flow.
  client ??= createBrowserClient(url, key, { auth: { detectSessionInUrl: false }, cookieOptions: { sameSite: 'lax', secure: process.env.NODE_ENV === 'production' } });
  return client;
}
