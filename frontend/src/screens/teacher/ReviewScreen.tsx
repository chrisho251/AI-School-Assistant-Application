/* ReviewScreen (teacher) — review an auto-graded attempt, override scores, and
 * finalise. Ported from fr-screens-teacher.jsx, wired to /attempts/*.
 *
 * Contract gaps vs. the mock (backend unchanged, D4): AnswerReview has no
 * max_score and no boolean `correct`, so the score control is a free numeric input
 * and correctness is inferred (short → LLM judge; mcq → correct when auto_score>0).
 * The "student" is shown by a shortened id — no student-name field on the wire.
 * Selection is in-screen (notebook → quiz → attempt) since the nav is global. */
import { useState } from 'react';

import { Icon } from '@/components/Icon';
import { Avatar } from '@/components/ui/Avatar';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { inputStyle, Select } from '@/components/ui/inputs';
import { StatusPill } from '@/components/ui/StatusPill';
import {
  useAttemptAnswers,
  useAttempts,
  useFinalizeAttempt,
  useNotebooks,
  useOverrideScore,
  useProctorEvents,
  useQuizzes,
} from '@/lib/query';
import type { AnswerReview } from '@/lib/types';

function shortId(id: string): string {
  return id.slice(0, 8);
}

function renderResponse(response: Record<string, unknown>): string {
  if (typeof response.text === 'string') return response.text;
  if (typeof response.selected_key === 'string') return `Selected: ${response.selected_key}`;
  const entries = Object.entries(response);
  return entries.length ? entries.map(([k, v]) => `${k}: ${String(v)}`).join(', ') : '—';
}

function fmtTime(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString();
}

const DANGER_EVENTS = new Set(['tab_hidden', 'window_blur', 'fullscreen_exit']);

function ScoreInput({ value, onCommit }: { value: number; onCommit: (v: number) => void }) {
  const [text, setText] = useState(String(value));
  const [f, setF] = useState(false);
  return (
    <input
      type="number"
      step="0.5"
      min="0"
      value={text}
      onChange={(e) => setText(e.target.value)}
      onFocus={() => setF(true)}
      onBlur={() => {
        setF(false);
        const n = parseFloat(text);
        if (!Number.isNaN(n) && n !== value) onCommit(n);
      }}
      style={{ ...inputStyle(f), width: 90, padding: '8px 10px', fontFamily: 'var(--font-mono)' }}
    />
  );
}

function AnswerCard({
  answer,
  onOverride,
}: {
  answer: AnswerReview;
  onOverride: (answerId: string, score: number) => void;
}) {
  const current = answer.teacher_score ?? answer.auto_score ?? 0;
  const isJudged = answer.type === 'short' || answer.type === 'essay';
  const correct = !isJudged && (answer.auto_score ?? 0) > 0;

  return (
    <Card padding={20}>
      <div style={{ display: 'flex', gap: 12, marginBottom: 14 }}>
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 26,
            height: 26,
            borderRadius: 8,
            flex: 'none',
            background: 'var(--fr-accent-soft)',
            fontFamily: 'var(--font-mono)',
            fontSize: 13,
            fontWeight: 700,
            color: 'var(--fr-accent)',
          }}
        >
          {answer.ordinal + 1}
        </span>
        <h3
          style={{
            fontSize: 15.5,
            fontWeight: 700,
            color: 'var(--text-strong)',
            margin: 0,
            flex: 1,
            lineHeight: 1.5,
            paddingTop: 2,
          }}
        >
          {answer.stem}
        </h3>
        {isJudged ? (
          <Badge tone="ai" dot>
            LLM judge
          </Badge>
        ) : correct ? (
          <Badge tone="success" dot>
            Correct
          </Badge>
        ) : (
          <Badge tone="danger" dot>
            Incorrect
          </Badge>
        )}
      </div>

      <div
        style={{
          background: 'var(--slate-50)',
          borderRadius: 13,
          padding: '12px 14px',
          fontSize: 14,
          color: 'var(--text-body)',
          marginBottom: 12,
          lineHeight: 1.55,
        }}
      >
        <span
          style={{
            display: 'block',
            color: 'var(--text-faint)',
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: '.05em',
            marginBottom: 4,
          }}
        >
          STUDENT RESPONSE
        </span>
        {renderResponse(answer.response)}
      </div>

      {answer.auto_feedback && (
        <div
          style={{
            display: 'flex',
            gap: 8,
            fontSize: 13.5,
            color: 'var(--text-body)',
            marginBottom: 14,
            padding: '10px 12px',
            borderRadius: 12,
            background: 'var(--violet-50)',
          }}
        >
          <Icon
            name="sparkles"
            size={15}
            color="var(--violet-600)"
            style={{ marginTop: 2, flex: 'none' }}
          />
          <span>
            <b style={{ color: 'var(--violet-700)' }}>Judge feedback. </b>
            {answer.auto_feedback}
          </span>
        </div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: 14, paddingTop: 4 }}>
        <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>Auto score</span>
        <span
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 14,
            fontWeight: 700,
            color: 'var(--text-strong)',
          }}
        >
          {answer.auto_score ?? '—'}
        </span>
        <span style={{ flex: 1 }} />
        <span style={{ fontSize: 12.5, color: 'var(--text-muted)', fontWeight: 600 }}>
          Your score
        </span>
        <ScoreInput value={current} onCommit={(v) => onOverride(answer.answer_id, v)} />
      </div>
    </Card>
  );
}

function AttemptReview({ attemptId, studentId }: { attemptId: string; studentId: string }) {
  const answers = useAttemptAnswers(attemptId);
  const proctor = useProctorEvents(attemptId);
  const override = useOverrideScore(attemptId);
  const finalize = useFinalizeAttempt(attemptId);

  const rows = answers.data ?? [];
  const grading = rows.some((a) => a.auto_score == null);
  const total = rows.reduce((s, a) => s + (a.teacher_score ?? a.auto_score ?? 0), 0);
  const events = proctor.data ?? [];
  const finalised = finalize.isSuccess;

  return (
    <>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          marginBottom: 20,
          flexWrap: 'wrap',
        }}
      >
        <h1
          style={{ fontSize: 24, fontWeight: 800, margin: 0, color: 'var(--text-strong)', flex: 1 }}
        >
          Review &amp; finalise
        </h1>
        <Avatar name={shortId(studentId)} role="student" size={32} />
        <span
          style={{
            fontSize: 13.5,
            color: 'var(--text-strong)',
            fontWeight: 700,
            fontFamily: 'var(--font-mono)',
          }}
        >
          {shortId(studentId)}
        </span>
        <StatusPill status={finalised ? 'finalised' : grading ? 'grading' : 'submitted'} />
      </div>

      <Card
        padding={18}
        style={{
          marginBottom: 16,
          background: 'var(--amber-50)',
          border: '1px solid var(--amber-200)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 12 }}>
          <Icon name="flag" size={16} color="var(--amber-600)" />
          <b style={{ fontSize: 14, color: 'var(--text-strong)' }}>Proctor timeline</b>
          <Badge tone={events.length ? 'danger' : 'neutral'}>{events.length} events</Badge>
        </div>
        {events.length === 0 ? (
          <div style={{ fontSize: 13.5, color: 'var(--text-muted)' }}>
            No lockdown events recorded.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
            {events.map((e, i) => (
              <div
                key={i}
                style={{ display: 'flex', alignItems: 'center', gap: 11, fontSize: 13.5 }}
              >
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    fontSize: 12.5,
                    color: 'var(--text-muted)',
                  }}
                >
                  {fmtTime(e.at)}
                </span>
                <Icon
                  name="flag"
                  size={13}
                  color={DANGER_EVENTS.has(e.type) ? 'var(--red-600)' : 'var(--amber-600)'}
                />
                <span style={{ color: 'var(--text-body)', textTransform: 'capitalize' }}>
                  {e.type.replace(/_/g, ' ')}
                </span>
              </div>
            ))}
          </div>
        )}
      </Card>

      {answers.isLoading && (
        <p style={{ color: 'var(--text-muted)', fontSize: 14.5 }}>Loading answers…</p>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {rows.map((a) => (
          <AnswerCard
            key={a.answer_id}
            answer={a}
            onOverride={(answerId, score) => override.mutate({ answerId, score })}
          />
        ))}
      </div>

      {rows.length > 0 && (
        <Card
          padding={20}
          style={{
            marginTop: 16,
            display: 'flex',
            alignItems: 'center',
            gap: 16,
            flexWrap: 'wrap',
          }}
        >
          <div style={{ flex: 1, minWidth: 140 }}>
            <div
              style={{
                fontSize: 11.5,
                fontWeight: 700,
                letterSpacing: '.05em',
                textTransform: 'uppercase',
                color: 'var(--text-faint)',
                marginBottom: 2,
              }}
            >
              {finalised ? 'Final score' : 'Provisional total'}
            </div>
            <div
              style={{
                fontSize: 32,
                fontWeight: 800,
                color: 'var(--text-strong)',
                fontFamily: 'var(--font-mono)',
              }}
            >
              {total}
            </div>
          </div>
          {finalize.isError && (
            <span style={{ fontSize: 12.5, color: 'var(--red-600)' }}>
              {(finalize.error as Error).message}
            </span>
          )}
          {finalised ? (
            <Badge tone="success" dot solid style={{ padding: '8px 14px', fontSize: 13.5 }}>
              Grade written &amp; shared
            </Badge>
          ) : (
            <Button
              size="lg"
              iconLeft={<Icon name="check" size={18} />}
              onClick={() => finalize.mutate()}
              disabled={grading || finalize.isPending}
            >
              {finalize.isPending ? 'Finalising…' : 'Finalise & release score'}
            </Button>
          )}
        </Card>
      )}
    </>
  );
}

export function ReviewScreen() {
  const notebooks = useNotebooks();
  const [notebookId, setNotebookId] = useState('');
  const quizzes = useQuizzes(notebookId);
  const [quizId, setQuizId] = useState('');
  const attempts = useAttempts(quizId);
  const [attemptId, setAttemptId] = useState('');

  const attempt = attempts.data?.find((a) => a.id === attemptId);

  return (
    <div style={{ padding: '30px 34px', maxWidth: 840, margin: '0 auto' }}>
      <div
        style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 24 }}
      >
        <div>
          <div
            style={{
              fontSize: 11.5,
              fontWeight: 700,
              letterSpacing: '.05em',
              textTransform: 'uppercase',
              color: 'var(--text-faint)',
              marginBottom: 6,
            }}
          >
            Notebook
          </div>
          <Select
            value={notebookId}
            onChange={(e) => {
              setNotebookId(e.target.value);
              setQuizId('');
              setAttemptId('');
            }}
            options={[
              { value: '', label: 'Select…' },
              ...(notebooks.data ?? []).map((n) => ({ value: n.id, label: n.title })),
            ]}
          />
        </div>
        <div>
          <div
            style={{
              fontSize: 11.5,
              fontWeight: 700,
              letterSpacing: '.05em',
              textTransform: 'uppercase',
              color: 'var(--text-faint)',
              marginBottom: 6,
            }}
          >
            Quiz
          </div>
          <Select
            value={quizId}
            onChange={(e) => {
              setQuizId(e.target.value);
              setAttemptId('');
            }}
            options={[
              { value: '', label: 'Select…' },
              ...(quizzes.data ?? []).map((q) => ({ value: q.id, label: q.title })),
            ]}
          />
        </div>
        <div>
          <div
            style={{
              fontSize: 11.5,
              fontWeight: 700,
              letterSpacing: '.05em',
              textTransform: 'uppercase',
              color: 'var(--text-faint)',
              marginBottom: 6,
            }}
          >
            Attempt
          </div>
          <Select
            value={attemptId}
            onChange={(e) => setAttemptId(e.target.value)}
            options={[
              { value: '', label: 'Select…' },
              ...(attempts.data ?? []).map((a) => ({
                value: a.id,
                label: `${shortId(a.student_id)} · ${a.status}`,
              })),
            ]}
          />
        </div>
      </div>

      {attempt ? (
        <AttemptReview attemptId={attempt.id} studentId={attempt.student_id} />
      ) : (
        <p style={{ color: 'var(--text-muted)', fontSize: 14.5 }}>
          Pick a notebook, quiz and attempt to review.
        </p>
      )}
    </div>
  );
}
