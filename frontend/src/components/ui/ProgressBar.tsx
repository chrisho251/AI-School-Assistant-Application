/* ProgressBar — thin filled track; tone tints the fill. Ported from fr-ui.jsx. */

export type ProgressTone = 'brand' | 'success' | 'ai';

const COLORS: Record<ProgressTone, string> = {
  brand: 'var(--fr-accent)',
  success: 'var(--green-600)',
  ai: 'var(--violet-600)',
};

interface ProgressBarProps {
  value: number;
  max?: number;
  tone?: ProgressTone;
}

export function ProgressBar({ value, max = 100, tone = 'brand' }: ProgressBarProps) {
  const pct = Math.min(100, (value / max) * 100);
  return (
    <div
      style={{
        height: 9,
        borderRadius: 999,
        background: 'var(--slate-100)',
        overflow: 'hidden',
      }}
    >
      <div
        style={{
          width: pct + '%',
          height: '100%',
          borderRadius: 999,
          background: COLORS[tone],
          transition: 'width var(--dur-slow) var(--ease-out)',
        }}
      />
    </div>
  );
}
