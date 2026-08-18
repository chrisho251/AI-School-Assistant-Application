/* Button — primary/secondary/soft/ghost/danger, sm/md/lg, hover-lift + press.
 * Ported from fr-ui.jsx (values kept identical). */
import { useState, type CSSProperties, type ReactNode } from 'react';

const A = 'var(--fr-accent)';
const A_HOVER = 'var(--fr-accent-hover)';
const A_SOFT = 'var(--fr-accent-soft)';

export type ButtonVariant = 'primary' | 'secondary' | 'soft' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps {
  children?: ReactNode;
  variant?: ButtonVariant;
  size?: ButtonSize;
  block?: boolean;
  iconLeft?: ReactNode;
  iconRight?: ReactNode;
  disabled?: boolean;
  onClick?: () => void;
  style?: CSSProperties;
}

const PADS: Record<ButtonSize, string> = { sm: '8px 14px', md: '11px 18px', lg: '14px 24px' };
const FONTS: Record<ButtonSize, number> = { sm: 13.5, md: 14.5, lg: 16 };

export function Button({
  children,
  variant = 'primary',
  size = 'md',
  block,
  iconLeft,
  iconRight,
  disabled,
  onClick,
  style,
}: ButtonProps) {
  const [h, setH] = useState(false);
  const [p, setP] = useState(false);

  const palette: Record<
    ButtonVariant,
    { bg: string; color: string; border: string; shadow: string }
  > = {
    primary: {
      bg: h ? A_HOVER : A,
      color: '#fff',
      border: '1px solid transparent',
      shadow: h ? '0 6px 16px -6px rgba(79,70,229,.5)' : '0 2px 6px -3px rgba(79,70,229,.45)',
    },
    secondary: {
      bg: h ? 'var(--slate-50)' : '#fff',
      color: 'var(--text-strong)',
      border: '1.5px solid var(--border-strong)',
      shadow: '0 1px 2px rgba(15,23,42,.04)',
    },
    soft: {
      bg: h ? 'var(--indigo-100)' : A_SOFT,
      color: A,
      border: '1px solid transparent',
      shadow: 'none',
    },
    ghost: {
      bg: h ? 'var(--slate-100)' : 'transparent',
      color: 'var(--text-body)',
      border: '1px solid transparent',
      shadow: 'none',
    },
    danger: {
      bg: h ? 'var(--red-700)' : 'var(--red-600)',
      color: '#fff',
      border: '1px solid transparent',
      shadow: '0 2px 6px -3px rgba(220,38,38,.45)',
    },
  };
  const pal = palette[variant];

  return (
    <button
      onClick={disabled ? undefined : onClick}
      disabled={disabled}
      onMouseEnter={() => setH(true)}
      onMouseLeave={() => {
        setH(false);
        setP(false);
      }}
      onMouseDown={() => setP(true)}
      onMouseUp={() => setP(false)}
      style={{
        display: block ? 'flex' : 'inline-flex',
        width: block ? '100%' : 'auto',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 8,
        padding: PADS[size],
        fontSize: FONTS[size],
        fontWeight: 600,
        fontFamily: 'var(--font-sans)',
        borderRadius: 'var(--fr-btn-radius)',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.55 : 1,
        lineHeight: 1.1,
        whiteSpace: 'nowrap',
        background: pal.bg,
        color: pal.color,
        border: pal.border,
        boxShadow: p ? 'none' : pal.shadow,
        transform: p ? 'translateY(0)' : h && !disabled ? 'translateY(-1px)' : 'translateY(0)',
        transition: 'all var(--dur-fast) var(--ease-out)',
        ...style,
      }}
    >
      {iconLeft}
      {children}
      {iconRight}
    </button>
  );
}
