/* Alert — tinted callout with optional icon + title. Ported from fr-ui.jsx. */
import type { ReactNode } from 'react';

export type AlertTone = 'info' | 'warning' | 'success' | 'danger' | 'ai';

// [bg, border, fg]
const TONES: Record<AlertTone, [string, string, string]> = {
  info: ['var(--blue-50)', 'var(--blue-200)', 'var(--blue-700)'],
  warning: ['var(--amber-50)', 'var(--amber-200)', 'var(--amber-700)'],
  success: ['var(--green-50)', 'var(--green-200)', 'var(--green-700)'],
  danger: ['var(--red-50)', 'var(--red-200)', 'var(--red-700)'],
  ai: ['var(--violet-50)', 'var(--violet-200)', 'var(--violet-700)'],
};

interface AlertProps {
  children: ReactNode;
  tone?: AlertTone;
  title?: string;
  icon?: ReactNode;
}

export function Alert({ children, tone = 'info', title, icon }: AlertProps) {
  const [bg, border, fg] = TONES[tone];
  return (
    <div
      style={{
        display: 'flex',
        gap: 11,
        padding: '13px 15px',
        borderRadius: 15,
        background: bg,
        border: '1px solid ' + border,
      }}
    >
      {icon && <span style={{ color: fg, flex: 'none', marginTop: 1 }}>{icon}</span>}
      <div style={{ fontSize: 13.5, lineHeight: 1.55, color: fg }}>
        {title && <div style={{ fontWeight: 700, marginBottom: 2 }}>{title}</div>}
        <div style={{ color: 'var(--text-body)' }}>{children}</div>
      </div>
    </div>
  );
}
