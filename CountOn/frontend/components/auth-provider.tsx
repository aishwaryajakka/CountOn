'use client';
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import type { Session } from '@supabase/supabase-js';
import { getSupabase } from '@/lib/supabase';

type AuthState = { session: Session | null; loading: boolean; error: string | null };
const AuthContext = createContext<AuthState>({ session: null, loading: true, error: null });
export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>({ session: null, loading: true, error: null });
  useEffect(() => {
    let mounted = true;
    let authEventReceived = false;
    let unsubscribe: (() => void) | undefined;
    try {
      const auth = getSupabase().auth;
      // Keep the callback synchronous: calling Auth methods inside it can deadlock.
      const { data } = auth.onAuthStateChange((_event, session) => {
        authEventReceived = true;
        if (mounted) setState({ session, loading: false, error: null });
      });
      unsubscribe = () => data.subscription.unsubscribe();
      auth.getSession().then(({ data, error }) => {
        if (mounted && !authEventReceived) setState({ session: data.session, loading: false, error: error ? 'Your session could not be restored. Please sign in again.' : null });
      }).catch(() => { if (mounted && !authEventReceived) setState({ session: null, loading: false, error: 'Your session could not be restored. Please sign in again.' }); });
    } catch (error) {
      queueMicrotask(() => { if (mounted) setState({ session: null, loading: false, error: error instanceof Error ? error.message : 'Authentication is unavailable.' }); });
    }
    return () => { mounted = false; unsubscribe?.(); };
  }, []);
  return <AuthContext.Provider value={state}>{children}</AuthContext.Provider>;
}
export const useAuth = () => useContext(AuthContext);
export function useIdentity() {
  const { session } = useAuth();
  const user = session?.user;
  const metadata = user?.user_metadata;
  const name = typeof metadata?.display_name === 'string' ? metadata.display_name : typeof metadata?.full_name === 'string' ? metadata.full_name : user?.email?.split('@')[0] ?? 'Your account';
  let timeZone = typeof metadata?.timezone === 'string' ? metadata.timezone : undefined;
  try { new Intl.DateTimeFormat(undefined, { timeZone }); } catch { timeZone = undefined; }
  return { name, email: user?.email, timeZone, firstName: name.split(' ')[0] };
}
