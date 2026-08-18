import { act, renderHook } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import { AuthProvider, buildDevToken, useAuth } from '@/lib/auth';

import type { ReactNode } from 'react';

const wrapper = ({ children }: { children: ReactNode }) => <AuthProvider>{children}</AuthProvider>;

afterEach(() => {
  localStorage.clear();
});

describe('buildDevToken', () => {
  it('formats dev.<userId>.<orgId>.<role>', () => {
    expect(buildDevToken({ userId: 'u1', orgId: 'o1', role: 'teacher' })).toBe('dev.u1.o1.teacher');
  });
});

describe('AuthProvider', () => {
  it('login sets user + token and persists to localStorage', () => {
    const { result } = renderHook(() => useAuth(), { wrapper });

    act(() => result.current.login({ userId: 'u1', orgId: 'o1', role: 'student' }));

    expect(result.current.user).toMatchObject({ userId: 'u1', role: 'student' });
    expect(result.current.token).toBe('dev.u1.o1.student');
    expect(JSON.parse(localStorage.getItem('asag.auth')!)).toMatchObject({ role: 'student' });
  });

  it('restores a persisted user on mount', () => {
    localStorage.setItem(
      'asag.auth',
      JSON.stringify({ userId: 'u2', orgId: 'o2', role: 'teacher' }),
    );
    const { result } = renderHook(() => useAuth(), { wrapper });
    expect(result.current.token).toBe('dev.u2.o2.teacher');
  });

  it('logout clears user + token + storage', () => {
    const { result } = renderHook(() => useAuth(), { wrapper });
    act(() => result.current.login({ userId: 'u1', orgId: 'o1', role: 'teacher' }));
    act(() => result.current.logout());

    expect(result.current.user).toBeNull();
    expect(result.current.token).toBeNull();
    expect(localStorage.getItem('asag.auth')).toBeNull();
  });
});
