import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useResource } from '@/hooks/use-resource';
afterEach(() => { vi.useRealTimers(); });
it('preserves visible data while a focus refresh is in flight', async () => {
  let resolve: (value: string) => void = () => {};
  const load = vi.fn().mockResolvedValueOnce('original').mockImplementationOnce(() => new Promise<string>(done => { resolve = done; }));
  const { result } = renderHook(() => useResource(load, 30000));
  await waitFor(() => expect(result.current.data).toBe('original'));
  act(() => { window.dispatchEvent(new Event('focus')); });
  await waitFor(() => expect(load).toHaveBeenCalledTimes(2));
  expect(result.current.data).toBe('original'); expect(result.current.loading).toBe(false);
  await act(async () => { resolve('updated'); });
  expect(result.current.data).toBe('updated');
});
it('aborts a background poll on unmount and removes the focus listener', async () => {
  const signals: AbortSignal[] = [];
  const load = vi.fn(async (signal: AbortSignal) => { signals.push(signal); return 'data'; });
  const { result, unmount } = renderHook(() => useResource(load, 30000));
  await waitFor(() => expect(result.current.data).toBe('data'));
  unmount(); act(() => { window.dispatchEvent(new Event('focus')); });
  expect(signals[0].aborted).toBe(true); expect(load).toHaveBeenCalledTimes(1);
});
