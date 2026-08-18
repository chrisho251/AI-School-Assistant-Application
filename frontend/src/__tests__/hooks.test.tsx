import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthProvider } from '@/lib/auth';
import { useCountdown } from '@/hooks/useCountdown';
import { useLockdown } from '@/hooks/useLockdown';

import type { ReactNode } from 'react';

describe('useCountdown', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('formats the remaining time as mm:ss and ticks down', () => {
    const { result } = renderHook(() => useCountdown(65));
    expect(result.current.label).toBe('01:05');
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current.seconds).toBe(64);
    expect(result.current.label).toBe('01:04');
  });

  it('stops at zero and fires onExpire exactly once', () => {
    const onExpire = vi.fn();
    const { result } = renderHook(() => useCountdown(1, { onExpire }));
    act(() => vi.advanceTimersByTime(1000));
    expect(result.current.seconds).toBe(0);
    expect(onExpire).toHaveBeenCalledOnce();
    act(() => vi.advanceTimersByTime(3000));
    expect(onExpire).toHaveBeenCalledOnce();
  });

  it('does not tick while inactive', () => {
    const { result } = renderHook(() => useCountdown(30, { active: false }));
    act(() => vi.advanceTimersByTime(5000));
    expect(result.current.seconds).toBe(30);
  });
});

describe('useLockdown', () => {
  const wrapper = ({ children }: { children: ReactNode }) => (
    <AuthProvider>{children}</AuthProvider>
  );

  beforeEach(() => {
    localStorage.setItem(
      'asag.auth',
      JSON.stringify({ userId: 'u1', orgId: 'o1', role: 'student' }),
    );
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string | URL, _init?: RequestInit) =>
        Promise.resolve(new Response(null, { status: 204 })),
      ),
    );
  });

  afterEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    Object.defineProperty(document, 'hidden', { configurable: true, value: false });
  });

  function lastEvent(fetchMock: ReturnType<typeof vi.fn>): { url: string; type: string } {
    const calls = fetchMock.mock.calls;
    const [url, init] = calls[calls.length - 1];
    const body = JSON.parse((init as RequestInit).body as string);
    return { url: String(url), type: body.event_type };
  }

  it('reports tab_hidden on visibilitychange and increments the count', () => {
    const { result } = renderHook(() => useLockdown('att-1', true), { wrapper });
    Object.defineProperty(document, 'hidden', { configurable: true, value: true });
    act(() => document.dispatchEvent(new Event('visibilitychange')));

    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const evt = lastEvent(fetchMock);
    expect(evt.url).toContain('/attempts/att-1/proctor_event');
    expect(evt.type).toBe('tab_hidden');
    expect(result.current).toBe(1);
  });

  it('reports window_blur and blocked keys, and stops after unmount', () => {
    const { unmount } = renderHook(() => useLockdown('att-1', true), { wrapper });
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;

    act(() => window.dispatchEvent(new Event('blur')));
    expect(lastEvent(fetchMock).type).toBe('window_blur');

    act(() => document.dispatchEvent(new KeyboardEvent('keydown', { key: 'F12' })));
    expect(lastEvent(fetchMock).type).toBe('key_blocked');

    const countBefore = fetchMock.mock.calls.length;
    unmount();
    act(() => window.dispatchEvent(new Event('blur')));
    expect(fetchMock.mock.calls.length).toBe(countBefore);
  });

  it('does not attach listeners when inactive', () => {
    renderHook(() => useLockdown('att-1', false), { wrapper });
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    act(() => window.dispatchEvent(new Event('blur')));
    expect(fetchMock.mock.calls.length).toBe(0);
  });
});
