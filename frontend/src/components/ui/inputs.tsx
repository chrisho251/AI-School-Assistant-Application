/* Form inputs — Field wrapper, focus-ring Input, Textarea, chevron Select.
 * Ported from fr-ui.jsx (values kept identical). */
import {
  useState,
  type ChangeEvent,
  type CSSProperties,
  type KeyboardEvent,
  type ReactNode,
} from 'react';

import { Icon } from '@/components/Icon';

const A = 'var(--fr-accent)';

interface FieldProps {
  label?: string;
  hint?: string;
  children: ReactNode;
}

export function Field({ label, hint, children }: FieldProps) {
  return (
    <label style={{ display: 'block' }}>
      {label && (
        <div
          style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-strong)', marginBottom: 7 }}
        >
          {label}
        </div>
      )}
      {children}
      {hint && <div style={{ fontSize: 12, color: 'var(--text-muted)', marginTop: 6 }}>{hint}</div>}
    </label>
  );
}

export function inputStyle(focus: boolean): CSSProperties {
  return {
    width: '100%',
    padding: '11px 14px',
    fontSize: 14.5,
    fontFamily: 'var(--font-sans)',
    color: 'var(--text-strong)',
    background: '#fff',
    border: '1.5px solid ' + (focus ? A : 'var(--border-strong)'),
    borderRadius: 13,
    outline: 'none',
    boxShadow: focus ? 'var(--fr-ring)' : 'none',
    transition: 'all var(--dur-fast) var(--ease-out)',
  };
}

interface InputProps {
  label?: string;
  hint?: string;
  iconLeft?: ReactNode;
  type?: string;
  value?: string;
  defaultValue?: string;
  placeholder?: string;
  onChange?: (e: ChangeEvent<HTMLInputElement>) => void;
  onKeyDown?: (e: KeyboardEvent<HTMLInputElement>) => void;
}

export function Input({
  label,
  hint,
  iconLeft,
  type = 'text',
  value,
  defaultValue,
  placeholder,
  onChange,
  onKeyDown,
}: InputProps) {
  const [f, setF] = useState(false);
  const inner = (
    <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
      {iconLeft && (
        <span
          style={{
            position: 'absolute',
            left: 13,
            color: f ? A : 'var(--text-faint)',
            pointerEvents: 'none',
          }}
        >
          {iconLeft}
        </span>
      )}
      <input
        type={type}
        value={value}
        defaultValue={defaultValue}
        placeholder={placeholder}
        onChange={onChange}
        onKeyDown={onKeyDown}
        onFocus={() => setF(true)}
        onBlur={() => setF(false)}
        style={{ ...inputStyle(f), paddingLeft: iconLeft ? 38 : 14 }}
      />
    </div>
  );
  return label || hint ? (
    <Field label={label} hint={hint}>
      {inner}
    </Field>
  ) : (
    inner
  );
}

interface TextareaProps {
  rows?: number;
  value?: string;
  placeholder?: string;
  onChange?: (e: ChangeEvent<HTMLTextAreaElement>) => void;
}

export function Textarea({ rows = 4, value, placeholder, onChange }: TextareaProps) {
  const [f, setF] = useState(false);
  return (
    <textarea
      rows={rows}
      value={value}
      placeholder={placeholder}
      onChange={onChange}
      onFocus={() => setF(true)}
      onBlur={() => setF(false)}
      style={{ ...inputStyle(f), resize: 'vertical', lineHeight: 1.6 }}
    />
  );
}

interface SelectProps {
  value?: string;
  onChange?: (e: ChangeEvent<HTMLSelectElement>) => void;
  options: { value: string; label: string }[];
  size?: 'sm' | 'md';
}

export function Select({ value, onChange, options, size = 'md' }: SelectProps) {
  const [f, setF] = useState(false);
  return (
    <div style={{ position: 'relative' }}>
      <select
        value={value}
        onChange={onChange}
        onFocus={() => setF(true)}
        onBlur={() => setF(false)}
        style={{
          ...inputStyle(f),
          appearance: 'none',
          padding: size === 'sm' ? '8px 32px 8px 12px' : '11px 36px 11px 14px',
          fontSize: size === 'sm' ? 13.5 : 14.5,
          cursor: 'pointer',
          fontWeight: 600,
        }}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <span
        style={{
          position: 'absolute',
          right: 12,
          top: '50%',
          transform: 'translateY(-50%)',
          pointerEvents: 'none',
          color: 'var(--text-muted)',
        }}
      >
        <Icon name="chevronDown" size={16} />
      </span>
    </div>
  );
}
