/* AppShell — routed app frame: sidebar + (topbar over <Outlet/>).
 *
 * Reads identity from AuthContext, derives nav items + page title from the
 * current route, and turns nav clicks / role switch / logout into navigation.
 * Ports the titles + nav tables from fr-app.jsx. */
import { useEffect, useState } from 'react';
import { Outlet, useLocation, useNavigate } from 'react-router-dom';

import type { IconName } from '@/components/Icon';
import { useMediaQuery } from '@/hooks/useMediaQuery';
import { useAuth } from '@/lib/auth';
import { useNotebooks } from '@/lib/query';
import type { Role } from '@/lib/types';

import { Sidebar, type NavItemDef } from './Sidebar';
import { Topbar } from './Topbar';

function navItems(role: Role, notebookCount?: number): NavItemDef[] {
  const nb: NavItemDef = {
    id: 'notebooks',
    icon: 'notebook',
    label: 'Notebooks',
    badge: notebookCount,
  };
  return role === 'teacher'
    ? [
        nb,
        { id: 'quizzes', icon: 'quiz' as IconName, label: 'Quizzes' },
        { id: 'review', icon: 'check' as IconName, label: 'Review & grade' },
      ]
    : [
        nb,
        { id: 'chat', icon: 'chat' as IconName, label: 'Ask & learn' },
        { id: 'quiz', icon: 'quiz' as IconName, label: 'My quizzes' },
      ];
}

function titleFor(nav: string, role: Role): [string, string] {
  switch (nav) {
    case 'notebooks':
      return role === 'teacher'
        ? ['Notebooks', 'Create, upload and manage your class materials']
        : ['Notebooks', 'Materials your teachers have shared with you'];
    case 'chat':
      return ['Ask & learn', 'Grounded answers from your class materials'];
    case 'quiz':
      return ['My quizzes', 'Take a published quiz'];
    case 'quizzes':
      return ['Quizzes', 'Generate and publish grounded quizzes'];
    case 'review':
      return ['Review & grade', 'Auto-graded attempts awaiting your sign-off'];
    default:
      return ['ASAG', ''];
  }
}

export function AppShell() {
  const { user, logout, switchRole } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const notebooks = useNotebooks();
  const isMobile = useMediaQuery('(max-width: 860px)');
  const [menuOpen, setMenuOpen] = useState(false);

  // Close the mobile slide-over whenever the route changes.
  useEffect(() => setMenuOpen(false), [location.pathname]);

  // user is guaranteed by RequireAuth; narrow for TS.
  if (!user) return null;

  const nav = location.pathname.split('/')[1] || 'notebooks';
  const [title, subtitle] = titleFor(nav, user.role);
  const isChat = nav === 'chat';

  return (
    <div
      style={{
        display: 'flex',
        height: '100vh',
        overflow: 'hidden',
        background: 'var(--fr-page)',
      }}
    >
      <Sidebar
        role={user.role}
        nav={nav}
        items={navItems(user.role, notebooks.data?.length)}
        user={{ name: user.name ?? user.role }}
        mobile={isMobile}
        open={menuOpen}
        onClose={() => setMenuOpen(false)}
        setNav={(id) => navigate(`/${id}`)}
        onSwitchRole={() => {
          switchRole();
          navigate('/notebooks');
        }}
        onLogout={() => {
          logout();
          navigate('/login');
        }}
      />
      <div
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          minWidth: 0,
          position: 'relative',
        }}
      >
        <Topbar
          title={title}
          subtitle={subtitle}
          onMenu={isMobile ? () => setMenuOpen(true) : undefined}
        />
        <main
          style={{
            flex: 1,
            minHeight: 0,
            overflowY: isChat ? 'hidden' : 'auto',
            display: isChat ? 'flex' : 'block',
          }}
        >
          <Outlet />
        </main>
      </div>
    </div>
  );
}
