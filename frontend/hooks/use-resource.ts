'use client';
import { useCallback, useEffect, useState } from 'react';

export function useResource<T>(load: (signal: AbortSignal) => Promise<T>) {
  const [state, setState] = useState<{ data: T | null; error: Error | null; loading: boolean }>({ data: null, error: null, loading: true });
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    // Results are committed only for the current request, including on navigation.
    const pending = Promise.resolve().then(() => { if (!controller.signal.aborted) setState({ data: null, error: null, loading: true }); return load(controller.signal); });
    pending.then(data => { if (!controller.signal.aborted) setState({ data, error: null, loading: false }); }).catch(error => {
      if (!controller.signal.aborted) setState({ data: null, error: error instanceof Error ? error : new Error('Please try again.'), loading: false });
    });
    return () => controller.abort();
  }, [load, revision]);
  const reload = useCallback(() => setRevision(value => value + 1), []);
  return { ...state, reload };
}
