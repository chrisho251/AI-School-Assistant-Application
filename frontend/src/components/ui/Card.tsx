/* Card — white surface; `interactive` lifts 3px with an indigo edge on hover;
 * `accent` adds a role-tinted left border. Ported from fr-ui.jsx. */
import { useState, type CSSProperties, type ReactNode } from 'react';

const A = 'var(--fr-accent)';

export type CardAccent = 'ai' | 'teacher' | 'student' | 'brand';

interface CardProps {
  children: ReactNode;
  padding?: number;
  interactive?: boolean;
  accent?: CardAccent;
  onClick?: () => void;
  style?: CSSProperties;
}

const ACCENT_COLORS: Record<CardAccent, string> = {
  ai: 'var(--violet-400)',
  teacher: 'var(--amber-400)',
  student: 'var(--teal-400)',
  brand: A,
};

export function Card({ children, padding = 22, interactive, accent, onClick, style }: CardProps) {
  const [h, setH] = useState(false);
  return (
    <div
      onClick={onClick}
      onMouseEnter={() => interactive && setH(true)}
      onMouseLeave={() => interactive && setH(false)}
      style={{
        background: '#fff',
        borderRadius: 'var(--fr-card-radius)',
        padding,
        border: '1px solid ' + (h ? 'var(--indigo-200)' : 'var(--border-faint)'),
        borderLeft: accent ? '4px solid ' + ACCENT_COLORS[accent] : undefined,
        boxShadow: h ? 'var(--fr-shadow-lift)' : 'var(--fr-shadow-card)',
        transform: h ? 'translateY(-3px)' : 'none',
        cursor: interactive ? 'pointer' : 'default',
        transition: 'all var(--dur-base) var(--ease-out)',
        ...style,
      }}
    >
      {children}
    </div>
  );
}
