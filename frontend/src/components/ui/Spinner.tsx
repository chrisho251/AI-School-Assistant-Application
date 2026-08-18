/* Spinner — indeterminate loading ring driven by the fr-spin keyframe.
 * Ported from fr-ui.jsx. */

interface SpinnerProps {
  size?: number;
  color?: string;
}

export function Spinner({ size = 17, color = 'currentColor' }: SpinnerProps) {
  return (
    <span
      style={{
        display: 'inline-block',
        width: size,
        height: size,
        borderRadius: 999,
        border: `2.5px solid ${color === '#fff' ? 'rgba(255,255,255,.35)' : 'var(--slate-200)'}`,
        borderTopColor: color,
        animation: 'fr-spin .7s linear infinite',
      }}
    />
  );
}
