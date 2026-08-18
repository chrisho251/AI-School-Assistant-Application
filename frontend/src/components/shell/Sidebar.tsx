/* Sidebar — app rail: logo, role-scoped nav, tip card, user footer.
 * Ported from fr-shell.jsx. Badge counts arrive as props (static mock in
 * Phase 1; wired to react-query in Phase 4). */
import { useState } from 'react';

import { Icon, type IconName } from '@/components/Icon';
import { Avatar } from '@/components/ui/Avatar';

import { Logo } from './Logo';

export type Role = 'teacher' | 'student';

export interface NavItemDef {
  id: string;
  icon: IconName;
  label: string;
  badge?: number;
}

export interface ShellUser {
  name: string;
}

interface NavItemProps {
  icon: IconName;
  label: string;
  active?: boolean;
  badge?: number;
  onClick?: () => void;
}

function NavItem({ icon, label, active, badge, onClick }: NavItemProps) {
  const [h, setH] = useState(false);
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setH(true)}
      onMouseLeave={() => setH(false)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        width: '100%',
        textAlign: 'left',
        padding: '11px 13px',
        border: 'none',
        cursor: 'pointer',
        borderRadius: 14,
        background: active ? 'var(--fr-accent)' : h ? 'var(--slate-100)' : 'transparent',
        color: active ? '#fff' : 'var(--text-body)',
        fontFamily: 'var(--font-sans)',
        fontSize: 14.5,
        fontWeight: active ? 700 : 500,
        boxShadow: active ? '0 4px 12px -4px rgba(79,70,229,.5)' : 'none',
        transition: 'all var(--dur-fast) var(--ease-out)',
      }}
    >
      <Icon name={icon} size={19} color={active ? '#fff' : 'var(--text-faint)'} />
      <span style={{ flex: 1 }}>{label}</span>
      {badge != null && (
        <span
          style={{
            minWidth: 22,
            textAlign: 'center',
            fontFamily: 'var(--font-mono)',
            fontSize: 11.5,
            fontWeight: 700,
            padding: '2px 7px',
            borderRadius: 999,
            background: active ? 'rgba(255,255,255,.22)' : 'var(--slate-100)',
            color: active ? '#fff' : 'var(--text-muted)',
          }}
        >
          {badge}
        </span>
      )}
    </button>
  );
}

interface SidebarProps {
  role: Role;
  nav: string;
  items: NavItemDef[];
  user: ShellUser;
  setNav: (id: string) => void;
  onSwitchRole: () => void;
  onLogout: () => void;
  /** When true the rail renders as a fixed slide-over (mobile). */
  mobile?: boolean;
  open?: boolean;
  onClose?: () => void;
}

export function Sidebar({
  role,
  nav,
  items,
  user,
  setNav,
  onSwitchRole,
  onLogout,
  mobile = false,
  open = false,
  onClose,
}: SidebarProps) {
  const asideStyle: React.CSSProperties = mobile
    ? {
        position: 'fixed',
        top: 0,
        left: 0,
        zIndex: 40,
        width: '278px',
        height: '100%',
        background: '#fff',
        borderRight: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        transform: open ? 'translateX(0)' : 'translateX(-100%)',
        transition: 'transform var(--dur-base) var(--ease-out)',
        boxShadow: open ? 'var(--fr-shadow-lift)' : 'none',
      }
    : {
        width: '278px',
        flex: 'none',
        background: '#fff',
        borderRight: '1px solid var(--border)',
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
      };

  return (
    <>
      {mobile && open && (
        <div
          onClick={onClose}
          style={{ position: 'fixed', inset: 0, background: 'rgba(15,23,42,.35)', zIndex: 39 }}
        />
      )}
      <aside style={asideStyle}>
        <div style={{ padding: '20px 18px 10px' }}>
          <Logo />
        </div>

        <div style={{ padding: '8px 14px 0', flex: 1, overflowY: 'auto' }}>
          <div
            style={{
              fontSize: 11,
              fontWeight: 700,
              letterSpacing: '.06em',
              textTransform: 'uppercase',
              color: 'var(--text-faint)',
              padding: '8px 13px 8px',
            }}
          >
            {role === 'teacher' ? 'Teaching' : 'Learning'}
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {items.map((it) => (
              <NavItem key={it.id} {...it} active={nav === it.id} onClick={() => setNav(it.id)} />
            ))}
          </div>

          <div
            style={{
              marginTop: 18,
              padding: 15,
              borderRadius: 16,
              background: role === 'teacher' ? 'var(--amber-50)' : 'var(--teal-50)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
              <Icon
                name={role === 'teacher' ? 'sparkles' : 'shield'}
                size={16}
                color={role === 'teacher' ? 'var(--amber-600)' : 'var(--teal-600)'}
              />
              <b style={{ fontSize: 12.5, color: 'var(--text-strong)' }}>
                {role === 'teacher' ? 'Tip' : 'Good to know'}
              </b>
            </div>
            <p style={{ margin: 0, fontSize: 12.5, lineHeight: 1.5, color: 'var(--text-body)' }}>
              {role === 'teacher'
                ? 'Every quiz and slide ASAG generates cites the exact source it came from.'
                : 'Answers come only from your class materials — with links back to the source.'}
            </p>
          </div>
        </div>

        <div style={{ padding: 12, borderTop: '1px solid var(--border-faint)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px 12px' }}>
            <Avatar name={user.name} role={role} size={38} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div
                style={{
                  fontSize: 13.5,
                  fontWeight: 700,
                  color: 'var(--text-strong)',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {user.name}
              </div>
              <div
                style={{ fontSize: 12, color: 'var(--text-muted)', textTransform: 'capitalize' }}
              >
                {role}
              </div>
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
            <NavItem
              icon="refresh"
              label={'Switch to ' + (role === 'teacher' ? 'student' : 'teacher')}
              onClick={onSwitchRole}
            />
            <NavItem icon="logout" label="Log out" onClick={onLogout} />
          </div>
        </div>
      </aside>
    </>
  );
}
