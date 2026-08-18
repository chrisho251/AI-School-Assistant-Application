/* Session auth for the POC dev-token scheme.
 *
 * The backend honours a `dev.<userId>.<orgId>.<role>` bearer when no JWT secret is
 * configured (see src/asag/api/deps.py::_parse_dev_token), so login just assembles
 * one from seeded UUIDs. Identity persists to localStorage so a refresh stays
 * logged in. A real Supabase handoff is the post-POC swap point.
 *
 * switchRole re-authenticates as the *other* seeded demo identity (teacher and
 * student are distinct users on the wire), matching the mock's role-flip affordance. */
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

import { ApiClient } from './api';
import type { Role } from './types';

export interface AuthUser {
  userId: string;
  orgId: string;
  role: Role;
  name?: string;
}

interface AuthContextValue {
  user: AuthUser | null;
  token: string | null;
  login: (u: AuthUser) => void;
  logout: () => void;
  switchRole: () => void;
}

const STORAGE_KEY = 'asag.auth';

export const DEMO = {
  orgId: import.meta.env.VITE_DEMO_ORG_ID ?? '',
  teacherId: import.meta.env.VITE_DEMO_TEACHER_ID ?? '',
  studentId: import.meta.env.VITE_DEMO_STUDENT_ID ?? '',
  classId: import.meta.env.VITE_DEMO_CLASS_ID ?? '',
};

export function buildDevToken(user: AuthUser): string {
  return `dev.${user.userId}.${user.orgId}.${user.role}`;
}

/** Return the seeded demo identity for a role, or null if env IDs are missing. */
export function demoUser(role: Role): AuthUser | null {
  const userId = role === 'teacher' ? DEMO.teacherId : DEMO.studentId;
  if (!userId || !DEMO.orgId) return null;
  return {
    userId,
    orgId: DEMO.orgId,
    role,
    name: role === 'teacher' ? 'Teacher Demo' : 'Student 1',
  };
}

function readStored(): AuthUser | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(readStored);

  const login = useCallback((u: AuthUser) => {
    setUser(u);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(u));
  }, []);

  const logout = useCallback(() => {
    setUser(null);
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  const switchRole = useCallback(() => {
    setUser((prev) => {
      if (!prev) return prev;
      const nextRole: Role = prev.role === 'teacher' ? 'student' : 'teacher';
      const next = demoUser(nextRole) ?? { ...prev, role: nextRole };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }, []);

  const token = user ? buildDevToken(user) : null;

  const value = useMemo<AuthContextValue>(
    () => ({ user, token, login, logout, switchRole }),
    [user, token, login, logout, switchRole],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within <AuthProvider>');
  return ctx;
}

/** Memoised ApiClient for the current token; null when logged out. */
export function useApi(): ApiClient | null {
  const { token } = useAuth();
  return useMemo(() => (token ? new ApiClient(token) : null), [token]);
}
