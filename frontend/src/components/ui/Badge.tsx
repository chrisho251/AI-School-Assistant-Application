/* Badge — small pill label in a tone; `dot` prefixes a status dot, `solid` fills
 * the background with the tone's saturated colour. Ported from fr-ui.jsx. */
import type { CSSProperties, ReactNode } from 'react';

const A = 'var(--fr-accent)';
const A_SOFT = 'var(--fr-accent-soft)';

export type BadgeTone =
  'neutral' | 'brand' | 'success' | 'warning' | 'danger' | 'info' | 'ai' | 'student' | 'teacher';

const TONES: Record<BadgeTone, [string, string]> = {
  neutral: ['var(--slate-100)', 'var(--slate-600)'],
  brand: [A_SOFT, A],
  success: ['var(--green-50)', 'var(--green-700)'],
  warning: ['var(--amber-50)', 'var(--amber-700)'],
  danger: ['var(--red-50)', 'var(--red-700)'],
  info: ['var(--blue-50)', 'var(--blue-700)'],
  ai: ['var(--violet-50)', 'var(--violet-700)'],
  student: ['var(--teal-50)', 'var(--teal-700)'],
  teacher: ['var(--amber-50)', 'var(--amber-700)'],
};

/** Saturated foreground for a tone — used as the `solid` background fill. */
export function fg2(tone: BadgeTone): string {
  const map: Partial<Record<BadgeTone, string>> = {
    brand: 'var(--fr-accent)',
    success: 'var(--green-600)',
    danger: 'var(--red-600)',
    info: 'var(--blue-600)',
    ai: 'var(--violet-600)',
  };
  return map[tone] ?? 'var(--slate-600)';
}

interface BadgeProps {
  children: ReactNode;
  tone?: BadgeTone;
  dot?: boolean;
  solid?: boolean;
  style?: CSSProperties;
}

export function Badge({ children, tone = 'neutral', dot, solid, style }: BadgeProps) {
  const [bg, fg] = solid ? [fg2(tone), '#fff'] : TONES[tone];
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        padding: dot ? '4px 10px 4px 8px' : '4px 10px',
        borderRadius: 999,
        background: bg,
        color: fg,
        fontSize: 12,
        fontWeight: 600,
        lineHeight: 1.3,
        ...style,
      }}
    >
      {dot && (
        <span style={{ width: 6, height: 6, borderRadius: 999, background: solid ? '#fff' : fg }} />
      )}
      {children}
    </span>
  );
}
