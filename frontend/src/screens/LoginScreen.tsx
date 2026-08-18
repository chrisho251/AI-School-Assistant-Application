/* LoginScreen — brand panel + sign-in form. Ported from fr-screens-common.jsx.
 *
 * Hybrid dev login (plan §6 Q1): pick a role, then the User ID / Org ID fields
 * prefill from the seeded demo identity (VITE_DEMO_*) for one-click sign-in but
 * stay editable so any seeded user can log in. Email/password are cosmetic — the
 * backend authenticates the assembled dev-token, not these. */
import { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';

import { Icon } from '@/components/Icon';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/inputs';
import { demoUser, useAuth } from '@/lib/auth';
import type { Role } from '@/lib/types';

const BULLETS = [
  { icon: 'shield' as const, text: 'Grounded answers — only from your own class materials.' },
  { icon: 'quiz' as const, text: 'Auto-generated quizzes, graded with you in control.' },
  { icon: 'sparkles' as const, text: 'Every answer links back to the exact source.' },
];

const ROLE_CARDS = [
  { id: 'teacher' as Role, icon: 'cap' as const, label: 'Teacher', sub: 'Create & grade' },
  { id: 'student' as Role, icon: 'book' as const, label: 'Student', sub: 'Learn & take quizzes' },
];

function isUuid(v: string): boolean {
  return /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v.trim());
}

export function LoginScreen() {
  const { user, login } = useAuth();
  const navigate = useNavigate();

  const [role, setRole] = useState<Role>('teacher');
  const seed = demoUser(role);
  const [userId, setUserId] = useState(seed?.userId ?? '');
  const [orgId, setOrgId] = useState(seed?.orgId ?? '');
  const [error, setError] = useState<string | null>(null);

  if (user) return <Navigate to="/notebooks" replace />;

  const pickRole = (r: Role) => {
    setRole(r);
    const s = demoUser(r);
    setUserId(s?.userId ?? '');
    setOrgId(s?.orgId ?? '');
    setError(null);
  };

  const signIn = () => {
    if (!isUuid(userId) || !isUuid(orgId)) {
      setError('User ID and Org ID must both be valid UUIDs.');
      return;
    }
    login({ userId: userId.trim(), orgId: orgId.trim(), role, name: seed?.name });
    navigate('/notebooks');
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'grid',
        gridTemplateColumns: '1.05fr 1fr',
        background: 'var(--fr-page)',
      }}
    >
      {/* Brand panel */}
      <div
        style={{
          position: 'relative',
          overflow: 'hidden',
          padding: '56px 56px',
          display: 'flex',
          flexDirection: 'column',
          background: 'linear-gradient(155deg, #4f46e5 0%, #4338ca 55%, #3730a3 100%)',
          color: '#fff',
        }}
      >
        <div
          style={{
            position: 'absolute',
            top: -120,
            right: -120,
            width: 380,
            height: 380,
            borderRadius: 999,
            background: 'rgba(255,255,255,.08)',
          }}
        />
        <div
          style={{
            position: 'absolute',
            bottom: -160,
            left: -80,
            width: 360,
            height: 360,
            borderRadius: 999,
            background: 'rgba(255,255,255,.06)',
          }}
        />
        <div style={{ position: 'relative', display: 'flex', alignItems: 'center', gap: 12 }}>
          <img
            src="/logo-mark.svg"
            width={40}
            height={40}
            alt=""
            style={{ borderRadius: 12, background: '#fff' }}
          />
          <div style={{ lineHeight: 1.1 }}>
            <b style={{ fontSize: 19, fontWeight: 800, letterSpacing: '-0.02em' }}>ASAG</b>
            <div style={{ fontSize: 11, color: 'rgba(255,255,255,.7)', fontWeight: 500 }}>
              AI School Assistant &amp; Grader
            </div>
          </div>
        </div>
        <div style={{ position: 'relative', marginTop: 'auto' }}>
          <h1
            style={{
              fontSize: 38,
              fontWeight: 800,
              lineHeight: 1.15,
              letterSpacing: '-0.02em',
              color: '#fff',
              margin: '0 0 16px',
              maxWidth: 460,
            }}
          >
            The classroom workspace that teaches, tests, and grades.
          </h1>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14, marginTop: 26 }}>
            {BULLETS.map((b) => (
              <div key={b.text} style={{ display: 'flex', alignItems: 'center', gap: 13 }}>
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: 38,
                    height: 38,
                    borderRadius: 12,
                    background: 'rgba(255,255,255,.15)',
                    flex: 'none',
                  }}
                >
                  <Icon name={b.icon} size={19} color="#fff" />
                </span>
                <span style={{ fontSize: 15, color: 'rgba(255,255,255,.92)', lineHeight: 1.4 }}>
                  {b.text}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Form panel */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: 40,
        }}
      >
        <div style={{ width: '100%', maxWidth: 380 }}>
          <h2
            style={{
              fontSize: 27,
              fontWeight: 800,
              color: 'var(--text-strong)',
              margin: '0 0 6px',
              letterSpacing: '-0.01em',
            }}
          >
            Welcome back 👋
          </h2>
          <p style={{ margin: '0 0 26px', fontSize: 14.5, color: 'var(--text-muted)' }}>
            Sign in to your classroom to get started.
          </p>

          <div
            style={{
              fontSize: 13,
              fontWeight: 600,
              color: 'var(--text-strong)',
              marginBottom: 9,
            }}
          >
            I&apos;m a…
          </div>
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1fr 1fr',
              gap: 11,
              marginBottom: 22,
            }}
          >
            {ROLE_CARDS.map((r) => {
              const on = role === r.id;
              const tint = r.id === 'teacher' ? 'var(--amber-600)' : 'var(--teal-600)';
              return (
                <button
                  key={r.id}
                  onClick={() => pickRole(r.id)}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 9,
                    padding: '16px 15px',
                    textAlign: 'left',
                    cursor: 'pointer',
                    borderRadius: 16,
                    background: on ? 'var(--fr-accent-soft)' : '#fff',
                    border: '2px solid ' + (on ? 'var(--fr-accent)' : 'var(--border)'),
                    boxShadow: on ? '0 6px 18px -10px rgba(79,70,229,.5)' : 'var(--fr-shadow-card)',
                    transition: 'all var(--dur-fast) var(--ease-out)',
                  }}
                >
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      width: 40,
                      height: 40,
                      borderRadius: 12,
                      background: on
                        ? '#fff'
                        : r.id === 'teacher'
                          ? 'var(--amber-50)'
                          : 'var(--teal-50)',
                    }}
                  >
                    <Icon name={r.icon} size={21} color={tint} />
                  </span>
                  <div>
                    <div style={{ fontSize: 14.5, fontWeight: 700, color: 'var(--text-strong)' }}>
                      {r.label}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>{r.sub}</div>
                  </div>
                </button>
              );
            })}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 15 }}>
            <Input
              key={`email-${role}`}
              label="Email"
              defaultValue={role === 'teacher' ? 'hoang@school.edu' : 'mai.lan@school.edu'}
              iconLeft={<Icon name="fileText" size={15} />}
            />
            <Input label="User ID" value={userId} onChange={(e) => setUserId(e.target.value)} />
            <Input label="Org ID" value={orgId} onChange={(e) => setOrgId(e.target.value)} />
            {error && (
              <div style={{ fontSize: 12.5, color: 'var(--red-600)', fontWeight: 500 }}>
                {error}
              </div>
            )}
            <Button
              block
              size="lg"
              iconRight={<Icon name="arrowRight" size={18} />}
              onClick={signIn}
            >
              Sign in as {role}
            </Button>
          </div>
          <p
            style={{
              margin: '20px 0 0',
              fontSize: 12.5,
              color: 'var(--text-faint)',
              textAlign: 'center',
            }}
          >
            New here?{' '}
            <span style={{ color: 'var(--fr-accent)', fontWeight: 600, cursor: 'pointer' }}>
              Ask your school admin for an invite.
            </span>
          </p>
        </div>
      </div>
    </div>
  );
}
