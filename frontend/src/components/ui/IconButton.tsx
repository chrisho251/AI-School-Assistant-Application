/* IconButton — square 38px hover/active affordance for icon-only controls.
 * Ported from fr-ui.jsx (values kept identical). */
import { useState, type CSSProperties, type ReactNode } from 'react';

const A = 'var(--fr-accent)';
const A_SOFT = 'var(--fr-accent-soft)';

interface IconButtonProps {
  children: ReactNode;
  label: string;
  onClick?: () => void;
  active?: boolean;
  style?: CSSProperties;
}

export function IconButton({ children, label, onClick, active, style }: IconButtonProps) {
  const [h, setH] = useState(false);
  return (
    <button
      aria-label={label}
      title={label}
      onClick={onClick}
      onMouseEnter={() => setH(true)}
      onMouseLeave={() => setH(false)}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        width: 38,
        height: 38,
        borderRadius: 11,
        border: 'none',
        cursor: 'pointer',
        background: active ? A_SOFT : h ? 'var(--slate-100)' : 'transparent',
        color: active ? A : 'var(--text-muted)',
        transition: 'all var(--dur-fast) var(--ease-out)',
        ...style,
      }}
    >
      {children}
    </button>
  );
}
