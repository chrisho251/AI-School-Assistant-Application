/* NotebookDetail (teacher) — sources list (poll while ingesting) + upload +
 * "generate from sources" panel. Ported from fr-screens-teacher.jsx, wired to
 * GET/POST /sources and GET /notebooks/{id}.
 *
 * Slides generation has no API in the POC, so that button is disabled; the Quiz
 * button hands off to the Quizzes screen scoped to this notebook. */
import { useRef } from 'react';
import { useNavigate, useParams } from 'react-router-dom';

import { Icon, type IconName } from '@/components/Icon';
import { Alert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { StatusPill } from '@/components/ui/StatusPill';
import { useNotebook, useSources, useUploadSource } from '@/lib/query';

const TYPE_GLYPH: Record<string, IconName> = {
  pdf: 'fileText',
  docx: 'fileText',
  image: 'image',
  code: 'code',
};

// Map the backend's ingestion_status (pending|processing|ready|failed) onto the
// StatusPill vocabulary (which the mock defines as ready/ingesting).
function pillStatus(s: string): string {
  if (s === 'pending' || s === 'processing') return 'ingesting';
  return s; // 'ready' maps directly; 'failed' falls back to a neutral pill.
}

export function NotebookDetail() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const notebook = useNotebook(id);
  const sources = useSources(id);
  const upload = useUploadSource(id);
  const fileInput = useRef<HTMLInputElement>(null);

  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) upload.mutate(file);
    e.target.value = ''; // allow re-picking the same file
  };

  const rows = sources.data ?? [];

  return (
    <div style={{ padding: '30px 34px', maxWidth: 980, margin: '0 auto' }}>
      <input
        ref={fileInput}
        type="file"
        accept=".pdf,.png,.jpg,.jpeg"
        onChange={onPick}
        style={{ display: 'none' }}
      />

      <button
        onClick={() => navigate('/notebooks')}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          color: 'var(--text-muted)',
          fontSize: 13,
          fontWeight: 600,
          padding: 0,
          marginBottom: 14,
        }}
      >
        <Icon name="chevronRight" size={15} style={{ transform: 'rotate(180deg)' }} /> Back to
        notebooks
      </button>

      <div
        style={{
          display: 'flex',
          alignItems: 'flex-start',
          marginBottom: 22,
          gap: 16,
          flexWrap: 'wrap',
        }}
      >
        <div style={{ flex: 1, minWidth: 200 }}>
          {notebook.data?.subject && (
            <div
              style={{
                fontSize: 11.5,
                fontWeight: 700,
                letterSpacing: '.05em',
                textTransform: 'uppercase',
                color: 'var(--fr-accent)',
                marginBottom: 5,
              }}
            >
              {notebook.data.subject}
            </div>
          )}
          <h1
            style={{
              fontSize: 26,
              fontWeight: 800,
              margin: 0,
              color: 'var(--text-strong)',
              letterSpacing: '-0.01em',
            }}
          >
            {notebook.data?.title ?? 'Notebook'}
          </h1>
        </div>
        <Button
          variant="primary"
          iconLeft={<Icon name="upload" size={17} />}
          onClick={() => fileInput.current?.click()}
          disabled={upload.isPending}
        >
          {upload.isPending ? 'Uploading…' : 'Upload source'}
        </Button>
      </div>

      {upload.isError && (
        <div style={{ marginBottom: 16 }}>
          <Alert tone="danger" icon={<Icon name="alert" size={16} />}>
            {(upload.error as Error).message}
          </Alert>
        </div>
      )}

      <div
        style={{ display: 'grid', gridTemplateColumns: '1fr 290px', gap: 20, alignItems: 'start' }}
      >
        <Card padding={0}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              padding: '16px 20px',
              borderBottom: '1px solid var(--border-faint)',
            }}
          >
            <h3
              style={{
                fontSize: 15.5,
                fontWeight: 700,
                color: 'var(--text-strong)',
                margin: 0,
                flex: 1,
              }}
            >
              Sources
            </h3>
            <Badge tone="neutral">{rows.length} files</Badge>
          </div>

          {sources.isLoading && (
            <div style={{ padding: '18px 20px', color: 'var(--text-muted)', fontSize: 13.5 }}>
              Loading sources…
            </div>
          )}
          {!sources.isLoading && rows.length === 0 && (
            <div style={{ padding: '18px 20px', color: 'var(--text-muted)', fontSize: 13.5 }}>
              No sources yet — upload a PDF or image to get started.
            </div>
          )}

          {rows.map((s, i) => (
            <div
              key={s.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 13,
                padding: '15px 20px',
                borderTop: i ? '1px solid var(--border-faint)' : 'none',
              }}
            >
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: 40,
                  height: 40,
                  borderRadius: 12,
                  background: 'var(--slate-50)',
                  flex: 'none',
                }}
              >
                <Icon
                  name={TYPE_GLYPH[s.source_type] ?? 'fileText'}
                  size={18}
                  color="var(--text-muted)"
                />
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div
                  style={{
                    fontSize: 14,
                    fontWeight: 600,
                    color: 'var(--text-strong)',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {s.original_filename}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  {s.source_type.toUpperCase()}
                </div>
              </div>
              <StatusPill status={pillStatus(s.ingestion_status)} />
            </div>
          ))}

          <div style={{ padding: '14px 20px', borderTop: '1px dashed var(--border-strong)' }}>
            <button
              onClick={() => fileInput.current?.click()}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 9,
                width: '100%',
                padding: '13px',
                borderRadius: 13,
                border: '1.5px dashed var(--border-strong)',
                background: 'var(--slate-50)',
                color: 'var(--text-muted)',
                fontSize: 13.5,
                fontWeight: 600,
                fontFamily: 'var(--font-sans)',
                cursor: 'pointer',
              }}
            >
              <Icon name="upload" size={16} /> Add a PDF or image as a source
            </button>
          </div>
        </Card>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <Card>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
              <Icon name="sparkles" size={17} color="var(--violet-600)" />
              <b style={{ fontSize: 14.5, color: 'var(--text-strong)' }}>Generate from sources</b>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <Button
                block
                variant="soft"
                iconLeft={<Icon name="layers" size={17} />}
                style={{ justifyContent: 'flex-start' }}
                disabled
              >
                Lecture slides
              </Button>
              <Button
                block
                variant="soft"
                iconLeft={<Icon name="quiz" size={17} />}
                style={{ justifyContent: 'flex-start' }}
                onClick={() => navigate(`/quizzes?nb=${id}`)}
              >
                Quiz
              </Button>
            </div>
          </Card>
          <Alert tone="ai" icon={<Icon name="sparkles" size={16} />}>
            Everything ASAG generates cites the exact source chunks it draws from.
          </Alert>
        </div>
      </div>
    </div>
  );
}
