/* Logo — mark + "ASAG" wordmark. Ported from fr-shell.jsx.
 * The mark SVG lives in public/ so it resolves at the site root. */

interface LogoProps {
  size?: number;
  showText?: boolean;
}

export function Logo({ size = 36, showText = true }: LogoProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
      <img
        src="/logo-mark.svg"
        width={size}
        height={size}
        alt=""
        style={{ borderRadius: size * 0.28 }}
      />
      {showText && (
        <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.1 }}>
          <b
            style={{
              fontSize: 18,
              fontWeight: 800,
              color: 'var(--text-strong)',
              letterSpacing: '-0.02em',
            }}
          >
            ASAG
          </b>
          <span style={{ fontSize: 10.5, color: 'var(--text-muted)', fontWeight: 500 }}>
            AI School Assistant &amp; Grader
          </span>
        </div>
      )}
    </div>
  );
}
