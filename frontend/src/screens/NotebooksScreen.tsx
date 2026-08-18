/* NotebooksScreen — greeting + search + grid of notebook cards, plus teacher
 * create. Ported from fr-screens-common.jsx, wired to GET/POST /notebooks.
 *
 * Q4 adapter: the wire has no `sources` count or `ready` flag (only id/title/
 * subject), so those mock affordances are omitted. Create needs a class_id but no
 * classes endpoint exists → the form prefills the seeded demo class (editable). */
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { Icon, type IconName } from '@/components/Icon';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Field, Input, Textarea } from '@/components/ui/inputs';
import { DEMO, useAuth } from '@/lib/auth';
import { useCreateNotebook, useNotebooks } from '@/lib/query';
import type { Notebook } from '@/lib/types';

const SUBJECT_TINT: Record<string, [string, string, IconName]> = {
  Biology: ['var(--green-50)', 'var(--green-600)', 'bookOpen'],
  History: ['var(--amber-50)', 'var(--amber-600)', 'book'],
  'Computer Science': ['var(--blue-50)', 'var(--blue-600)', 'code'],
};
const DEFAULT_TINT: [string, string, IconName] = [
  'var(--indigo-50)',
  'var(--fr-accent)',
  'notebook',
];

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
}

function CreateNotebookModal({ onClose }: { onClose: () => void }) {
  const navigate = useNavigate();
  const create = useCreateNotebook();
  const [title, setTitle] = useState('');
  const [subject, setSubject] = useState('');
  const [description, setDescription] = useState('');
  const [classId, setClassId] = useState(DEMO.classId);

  const submit = () => {
    create.mutate(
      { classId, title, subject: subject || null, description: description || null },
      { onSuccess: (nb) => navigate(`/notebooks/${nb.id}`) },
    );
  };

  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(15,23,42,.35)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
        zIndex: 50,
      }}
    >
      <div onClick={(e) => e.stopPropagation()} style={{ width: '100%', maxWidth: 460 }}>
        <Card padding={26}>
          <h2
            style={{
              fontSize: 20,
              fontWeight: 800,
              color: 'var(--text-strong)',
              margin: '0 0 4px',
            }}
          >
            New notebook
          </h2>
          <p style={{ margin: '0 0 20px', fontSize: 13.5, color: 'var(--text-muted)' }}>
            Create a class notebook, then upload sources to it.
          </p>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
            <Input
              label="Title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Biology 12 — Photosynthesis"
            />
            <Input
              label="Subject"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              placeholder="Biology"
            />
            <Field label="Description">
              <Textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                rows={2}
                placeholder="Optional"
              />
            </Field>
            <Input label="Class ID" value={classId} onChange={(e) => setClassId(e.target.value)} />
            {create.isError && (
              <div style={{ fontSize: 12.5, color: 'var(--red-600)' }}>
                {(create.error as Error).message}
              </div>
            )}
            <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 4 }}>
              <Button variant="ghost" onClick={onClose}>
                Cancel
              </Button>
              <Button
                onClick={submit}
                disabled={!title.trim() || !classId.trim() || create.isPending}
              >
                {create.isPending ? 'Creating…' : 'Create notebook'}
              </Button>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}

export function NotebooksScreen() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const { data, isLoading, isError, error } = useNotebooks();
  const [query, setQuery] = useState('');
  const [creating, setCreating] = useState(false);

  const role = user?.role ?? 'student';
  const firstName = (user?.name ?? role).split(' ').slice(-1)[0];

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return data ?? [];
    return (data ?? []).filter(
      (nb) => nb.title.toLowerCase().includes(q) || (nb.subject ?? '').toLowerCase().includes(q),
    );
  }, [data, query]);

  const openNotebook = (nb: Notebook) => {
    if (role === 'teacher') navigate(`/notebooks/${nb.id}`);
    else navigate(`/chat?nb=${nb.id}`);
  };

  return (
    <div style={{ padding: '30px 34px', maxWidth: 1080, margin: '0 auto' }}>
      {creating && <CreateNotebookModal onClose={() => setCreating(false)} />}

      <div
        style={{
          display: 'flex',
          alignItems: 'flex-end',
          marginBottom: 24,
          gap: 16,
          flexWrap: 'wrap',
        }}
      >
        <div style={{ flex: 1, minWidth: 220 }}>
          <h1
            style={{
              fontSize: 28,
              fontWeight: 800,
              color: 'var(--text-strong)',
              margin: '0 0 4px',
              letterSpacing: '-0.01em',
            }}
          >
            {greeting()}, {firstName}
          </h1>
          <p style={{ margin: 0, fontSize: 15, color: 'var(--text-muted)' }}>
            {role === 'teacher'
              ? "Here are the class notebooks you're working on."
              : 'Materials your teachers have shared with you.'}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <div style={{ width: 220 }}>
            <Input
              placeholder="Search notebooks…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              iconLeft={<Icon name="search" size={15} />}
            />
          </div>
          {role === 'teacher' && (
            <Button iconLeft={<Icon name="plus" size={18} />} onClick={() => setCreating(true)}>
              New notebook
            </Button>
          )}
        </div>
      </div>

      {isLoading && (
        <p style={{ color: 'var(--text-muted)', fontSize: 14.5 }}>Loading notebooks…</p>
      )}

      {isError && (
        <p style={{ color: 'var(--red-600)', fontSize: 14.5 }}>
          Couldn&apos;t load notebooks: {(error as Error).message}
        </p>
      )}

      {!isLoading && !isError && filtered.length === 0 && (
        <p style={{ color: 'var(--text-muted)', fontSize: 14.5 }}>
          {query ? 'No notebooks match your search.' : 'No notebooks yet.'}
        </p>
      )}

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(310px, 1fr))',
          gap: 18,
        }}
      >
        {filtered.map((nb) => {
          const [bg, fg, glyph] = (nb.subject && SUBJECT_TINT[nb.subject]) || DEFAULT_TINT;
          return (
            <Card key={nb.id} interactive onClick={() => openNotebook(nb)} padding={20}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14 }}>
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: 50,
                    height: 50,
                    borderRadius: 16,
                    background: bg,
                    flex: 'none',
                  }}
                >
                  <Icon name={glyph} size={24} color={fg} />
                </span>
                <div style={{ flex: 1, minWidth: 0, paddingTop: 2 }}>
                  {nb.subject && (
                    <div
                      style={{
                        fontSize: 11.5,
                        fontWeight: 700,
                        letterSpacing: '.04em',
                        textTransform: 'uppercase',
                        color: fg,
                        marginBottom: 3,
                      }}
                    >
                      {nb.subject}
                    </div>
                  )}
                  <h3
                    style={{
                      fontSize: 16.5,
                      fontWeight: 700,
                      color: 'var(--text-strong)',
                      margin: 0,
                      lineHeight: 1.3,
                    }}
                  >
                    {nb.title}
                  </h3>
                </div>
              </div>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  marginTop: 16,
                  paddingTop: 16,
                  borderTop: '1px solid var(--border-faint)',
                  fontSize: 13,
                  fontWeight: 600,
                  color: 'var(--fr-accent)',
                }}
              >
                {role === 'teacher' ? 'Open notebook' : 'Start asking'}{' '}
                <Icon name="arrowRight" size={15} color="var(--fr-accent)" />
              </div>
            </Card>
          );
        })}
      </div>
    </div>
  );
}
