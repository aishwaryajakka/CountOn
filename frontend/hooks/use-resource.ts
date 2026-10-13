'use client';
import { useCallback, useEffect, useRef, useState } from 'react';

export function useResource<T>(load: (signal: AbortSignal) => Promise<T>, pollMs?: number) {
  const [state, setState] = useState<{ data: T | null; error: Error | null; loading: boolean }>({ data: null, error: null, loading: true });
  const [revision, setRevision] = useState(0);
  const background = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    const quiet = background.current;
    background.current = false;
    // Results are committed only for the current request, including on navigation.
    const pending = Promise.resolve().then(() => { if (!controller.signal.aborted) setState(previous => quiet && previous.data !== null ? { ...previous, error: null } : { data: null, error: null, loading: true }); return load(controller.signal); });
    pending.then(data => { if (!controller.signal.aborted) setState({ data, error: null, loading: false }); }).catch(error => {
      if (!controller.signal.aborted) setState({ data: null, error: error instanceof Error ? error : new Error('Please try again.'), loading: false });
    });
    return () => controller.abort();
  }, [load, revision]);
  const reload = useCallback(() => { background.current = false; setRevision(value => value + 1); }, []);
  useEffect(() => {
    if (!pollMs) return;
    const refresh = () => { if (document.visibilityState === 'visible') { background.current = true; setRevision(value => value + 1); } };
    const timer = window.setInterval(refresh, pollMs);
    window.addEventListener('focus', refresh);
    return () => { window.clearInterval(timer); window.removeEventListener('focus', refresh); };
  }, [pollMs, reload]);
  return { ...state, reload };
}
