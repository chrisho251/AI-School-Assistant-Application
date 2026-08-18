/* QuizzesScreen (teacher) — generate grounded quizzes for a notebook and publish
 * drafts. Ported from fr-screens-teacher.jsx, wired to /quizzes/*.
 *
 * The sidebar nav is global (not notebook-scoped), and there is no "all quizzes"
 * endpoint, so this screen selects a notebook (from ?nb or the first notebook) and
 * lists that notebook's quizzes. Each card lazy-loads its questions via GET
 * /quizzes/{id} since the list endpoint returns summaries only. */
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';

import { Icon } from '@/components/Icon';
import { Alert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Select } from '@/components/ui/inputs';
import { Spinner } from '@/components/ui/Spinner';
import { StatusPill } from '@/components/ui/StatusPill';
import { useGenerateQuiz, useNotebooks, usePublishQuiz, useQuiz, useQuizzes } from '@/lib/query';
import type { QuizSummary } from '@/lib/types';

function QuizCard({ quiz, notebookId }: { quiz: QuizSummary; notebookId: string }) {
  const full = useQuiz(quiz.id);
  const publish = usePublishQuiz(notebookId);
  const isDraft = quiz.status === 'draft';

  return (
    <Card padding={22} accent={isDraft ? 'ai' : undefined}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <h3
          style={{ fontSize: 18, fontWeight: 700, color: 'var(--text-strong)', margin: 0, flex: 1 }}
        >
          {quiz.title}
        </h3>
        {isDraft && (
          <Badge tone="ai" dot>
            AI draft
          </Badge>
        )}
        <StatusPill status={quiz.status} />
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {full.isLoading && (
          <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>Loading questions…</span>
        )}
        {(full.data?.questions ?? []).map((qq, i) => (
          <div
            key={qq.id}
            style={{
              display: 'flex',
              gap: 11,
              fontSize: 14,
              color: 'var(--text-body)',
              alignItems: 'flex-start',
            }}
          >
            <span
              style={{
                fontFamily: 'var(--font-mono)',
                color: 'var(--text-faint)',
                fontSize: 12.5,
                paddingTop: 2,
                flex: 'none',
              }}
            >
              {i + 1}
            </span>
            <span style={{ lineHeight: 1.45 }}>
              <Badge tone="neutral" style={{ marginRight: 8, verticalAlign: 1 }}>
                {qq.type}
              </Badge>
              {qq.stem}
            </span>
          </div>
        ))}
      </div>

      {isDraft && (
        <div
          style={{
            display: 'flex',
            gap: 10,
            marginTop: 18,
            paddingTop: 16,
            borderTop: '1px solid var(--border-faint)',
          }}
        >
          <Button
            size="sm"
            iconLeft={<Icon name="check" size={15} />}
            onClick={() => publish.mutate(quiz.id)}
            disabled={publish.isPending}
          >
            {publish.isPending ? 'Publishing…' : 'Publish to students'}
          </Button>
        </div>
      )}
    </Card>
  );
}

export function QuizzesScreen() {
  const [params, setParams] = useSearchParams();
  const notebooks = useNotebooks();
  const [notebookId, setNotebookId] = useState(params.get('nb') ?? '');

  // Default the selector to the first notebook once the list loads.
  useEffect(() => {
    if (!notebookId && notebooks.data && notebooks.data.length > 0) {
      setNotebookId(notebooks.data[0].id);
    }
  }, [notebookId, notebooks.data]);

  const quizzes = useQuizzes(notebookId);
  const generate = useGenerateQuiz(notebookId);
  const selected = notebooks.data?.find((n) => n.id === notebookId);

  const onSelect = (id: string) => {
    setNotebookId(id);
    setParams(id ? { nb: id } : {});
  };

  const onGenerate = () => {
    if (!notebookId) return;
    const title = `${selected?.title ?? 'Notebook'} — quiz`;
    generate.mutate({ title, mix: { mcq: 5 }, difficulty: 'medium' });
  };

  const list = quizzes.data ?? [];

  return (
    <div style={{ padding: '30px 34px', maxWidth: 900, margin: '0 auto' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          marginBottom: 20,
          gap: 16,
          flexWrap: 'wrap',
        }}
      >
        <div style={{ flex: 1, minWidth: 200 }}>
          <div
            style={{
              fontSize: 11.5,
              fontWeight: 700,
              letterSpacing: '.05em',
              textTransform: 'uppercase',
              color: 'var(--fr-accent)',
              marginBottom: 6,
            }}
          >
            Notebook
          </div>
          <div style={{ maxWidth: 320 }}>
            <Select
              value={notebookId}
              onChange={(e) => onSelect(e.target.value)}
              options={(notebooks.data ?? []).map((n) => ({ value: n.id, label: n.title }))}
            />
          </div>
        </div>
        <Button
          iconLeft={generate.isPending ? undefined : <Icon name="sparkles" size={17} />}
          onClick={onGenerate}
          disabled={generate.isPending || !notebookId}
        >
          {generate.isPending ? (
            <>
              <Spinner color="#fff" /> Generating…
            </>
          ) : (
            'Generate quiz'
          )}
        </Button>
      </div>

      {generate.isPending && (
        <div style={{ marginBottom: 16 }}>
          <Alert tone="ai" icon={<Icon name="sparkles" size={16} />}>
            Writing grounded questions… Each one is anchored to specific source chunks.
          </Alert>
        </div>
      )}
      {generate.isError && (
        <div style={{ marginBottom: 16 }}>
          <Alert tone="danger" icon={<Icon name="alert" size={16} />}>
            {(generate.error as Error).message}
          </Alert>
        </div>
      )}

      {quizzes.isLoading && (
        <p style={{ color: 'var(--text-muted)', fontSize: 14.5 }}>Loading quizzes…</p>
      )}
      {!quizzes.isLoading && list.length === 0 && (
        <p style={{ color: 'var(--text-muted)', fontSize: 14.5 }}>
          No quizzes yet — generate one from this notebook&apos;s sources.
        </p>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {list.map((q) => (
          <QuizCard key={q.id} quiz={q} notebookId={notebookId} />
        ))}
      </div>
    </div>
  );
}
