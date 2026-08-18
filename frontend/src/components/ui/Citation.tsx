/* Citation [N] marker + SourceChip — the anti-hallucination affordance (R-FE4):
 * every grounded answer renders [N] markers that highlight their source chip.
 * Ported from fr-ui.jsx. */
import { useState } from 'react';

import { Icon, type IconName } from '@/components/Icon';

const A = 'var(--fr-accent)';
const A_SOFT = 'var(--fr-accent-soft)';

interface CitationProps {
  n: number;
  active?: boolean;
  title?: string;
  onClick?: () => void;
}

export function Citation({ n, active, title, onClick }: CitationProps) {
  const [h, setH] = useState(false);
  return (
    <sup
      onClick={onClick}
      onMouseEnter={() => setH(true)}
      onMouseLeave={() => setH(false)}
      title={title}
      style={{
        cursor: 'pointer',
        fontFamily: 'var(--font-mono)',
        fontSize: 11,
        fontWeight: 700,
        lineHeight: 1,
        padding: '2px 5px',
        margin: '0 1px',
        borderRadius: 6,
        verticalAlign: 'super',
        background: active ? A : h ? A_SOFT : 'var(--indigo-50)',
        color: active ? '#fff' : A,
        border: '1px solid ' + (active ? A : 'var(--indigo-200)'),
        transition: 'all var(--dur-fast) var(--ease-out)',
      }}
    >
      {n}
    </sup>
  );
}

const TYPE_GLYPH: Record<string, IconName> = {
  pdf: 'fileText',
  docx: 'fileText',
  image: 'image',
  code: 'code',
};

interface SourceChipProps {
  index: number;
  filename: string;
  locator: string;
  type: string;
  active?: boolean;
  onClick?: () => void;
}

export function SourceChip({ index, filename, locator, type, active, onClick }: SourceChipProps) {
  const [h, setH] = useState(false);
  const glyph = TYPE_GLYPH[type] ?? 'fileText';
  return (
    <button
      onClick={onClick}
      onMouseEnter={() => setH(true)}
      onMouseLeave={() => setH(false)}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        width: '100%',
        textAlign: 'left',
        cursor: 'pointer',
        padding: '10px 12px',
        borderRadius: 13,
        fontFamily: 'var(--font-sans)',
        background: active ? A_SOFT : h ? 'var(--slate-50)' : '#fff',
        border: '1.5px solid ' + (active ? A : 'var(--border)'),
        transition: 'all var(--dur-fast) var(--ease-out)',
      }}
    >
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 24,
          height: 24,
          borderRadius: 8,
          flex: 'none',
          background: active ? A : 'var(--indigo-50)',
          color: active ? '#fff' : A,
          fontFamily: 'var(--font-mono)',
          fontSize: 11.5,
          fontWeight: 700,
        }}
      >
        {index}
      </span>
      <span style={{ flex: 1, minWidth: 0 }}>
        <span
          style={{
            display: 'block',
            fontSize: 13,
            fontWeight: 600,
            color: 'var(--text-strong)',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}
        >
          {filename}
        </span>
        <span
          style={{
            display: 'block',
            fontSize: 11.5,
            color: 'var(--text-muted)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          {locator}
        </span>
      </span>
      <Icon name={glyph} size={15} color="var(--text-faint)" />
    </button>
  );
}
