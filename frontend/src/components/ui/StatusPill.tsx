/* StatusPill — maps a backend status string to tone/label/(pulse) dot.
 * Ported from fr-ui.jsx. Unknown statuses fall back to a neutral pill. */

type Tone = 'success' | 'info' | 'ai' | 'warning' | 'neutral';

const MAP: Record<string, [Tone, string, boolean]> = {
  ready: ['success', 'Ready', false],
  finalised: ['success', 'Finalised', false],
  published: ['info', 'Published', false],
  draft: ['ai', 'Draft', false],
  ingesting: ['warning', 'Ingesting', true],
  grading: ['ai', 'Grading', true],
  submitted: ['warning', 'Awaiting review', false],
};

const FG: Record<Tone, string> = {
  success: 'var(--green-600)',
  info: 'var(--blue-600)',
  ai: 'var(--violet-600)',
  warning: 'var(--amber-600)',
  neutral: 'var(--slate-500)',
};
const BG: Record<Tone, string> = {
  success: 'var(--green-50)',
  info: 'var(--blue-50)',
  ai: 'var(--violet-50)',
  warning: 'var(--amber-50)',
  neutral: 'var(--slate-100)',
};

export function StatusPill({ status }: { status: string }) {
  const [tone, label, pulse] = MAP[status] ?? ['neutral', status, false];
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '4px 11px',
        borderRadius: 999,
        background: BG[tone],
        color: FG[tone],
        fontSize: 12,
        fontWeight: 600,
      }}
    >
      <span
        style={{
          width: 7,
          height: 7,
          borderRadius: 999,
          background: FG[tone],
          animation: pulse ? 'fr-pulse 1.4s ease-in-out infinite' : 'none',
        }}
      />
      {label}
    </span>
  );
}
