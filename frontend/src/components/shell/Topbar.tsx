/* Topbar — page title/subtitle, optional right slot, notifications button.
 * Ported from fr-shell.jsx. */
import type { ReactNode } from 'react';

import { Icon } from '@/components/Icon';
import { IconButton } from '@/components/ui/IconButton';

interface TopbarProps {
  title: string;
  subtitle?: string;
  right?: ReactNode;
  /** Renders a menu button (mobile) that toggles the slide-over sidebar. */
  onMenu?: () => void;
}

export function Topbar({ title, subtitle, right, onMenu }: TopbarProps) {
  return (
    <header
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        padding: '16px 30px',
        borderBottom: '1px solid var(--border)',
        background: '#fff',
        flex: 'none',
      }}
    >
      {onMenu && (
        <IconButton label="Open menu" onClick={onMenu}>
          <Icon name="panelLeft" size={19} />
        </IconButton>
      )}
      <div style={{ flex: 1, minWidth: 0 }}>
        <h2
          style={{
            margin: 0,
            fontSize: 21,
            fontWeight: 800,
            color: 'var(--text-strong)',
            letterSpacing: '-0.01em',
          }}
        >
          {title}
        </h2>
        {subtitle && (
          <div style={{ fontSize: 13.5, color: 'var(--text-muted)', marginTop: 2 }}>{subtitle}</div>
        )}
      </div>
      {right}
      <IconButton label="Notifications">
        <Icon name="bell" size={19} />
      </IconButton>
    </header>
  );
}
