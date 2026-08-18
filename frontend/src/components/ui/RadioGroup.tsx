/* RadioGroup — card-style single-select; selected option shows a check, others
 * show their key glyph. Used for MCQ answers and the login role picker.
 * Ported from fr-ui.jsx. */
import { Icon } from '@/components/Icon';

const A = 'var(--fr-accent)';
const A_SOFT = 'var(--fr-accent-soft)';

export interface RadioOption {
  value: string;
  label: string;
  key?: string;
}

interface RadioGroupProps {
  value?: string;
  onChange: (value: string) => void;
  options: RadioOption[];
}

export function RadioGroup({ value, onChange, options }: RadioGroupProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
      {options.map((o) => {
        const on = value === o.value;
        return (
          <button
            key={o.value}
            onClick={() => onChange(o.value)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 12,
              width: '100%',
              textAlign: 'left',
              cursor: 'pointer',
              padding: '13px 15px',
              borderRadius: 14,
              fontFamily: 'var(--font-sans)',
              background: on ? A_SOFT : '#fff',
              border: '2px solid ' + (on ? A : 'var(--border)'),
              transition: 'all var(--dur-fast) var(--ease-out)',
            }}
          >
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: 26,
                height: 26,
                borderRadius: 999,
                flex: 'none',
                background: on ? A : '#fff',
                border: '2px solid ' + (on ? A : 'var(--border-strong)'),
                color: '#fff',
                fontWeight: 700,
                fontSize: 12,
                fontFamily: 'var(--font-mono)',
              }}
            >
              {on ? <Icon name="check" size={15} color="#fff" /> : o.key}
            </span>
            <span
              style={{
                fontSize: 14.5,
                color: 'var(--text-strong)',
                fontWeight: on ? 600 : 500,
              }}
            >
              {o.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}
