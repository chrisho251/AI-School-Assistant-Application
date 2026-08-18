/* QuizScreen (student) — take a published quiz under browser lockdown. Ported
 * from fr-screens-student.jsx, wired to /attempts + useLockdown + useCountdown.
 *
 * The sidebar nav is global and there is no cross-notebook quiz list, so this
 * screen first selects a notebook and one of its published quizzes, then runs the
 * intro → taking → done flow. Q3 (resolved): the backend exposes no time limit, so
 * the timer uses a fixed default. Submission shapes match the graders:
 * mcq → {selected_key}, short → {text}. */
import { useState } from 'react';

import { Icon } from '@/components/Icon';
import { Alert } from '@/components/ui/Alert';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { RadioGroup } from '@/components/ui/RadioGroup';
import { Select } from '@/components/ui/inputs';
import { ProgressBar } from '@/components/ui/ProgressBar';
import { StatusPill } from '@/components/ui/StatusPill';
import { Textarea } from '@/components/ui/inputs';
import { useCountdown } from '@/hooks/useCountdown';
import { useLockdown } from '@/hooks/useLockdown';
import { useNotebooks, useQuiz, useQuizzes, useStartAttempt, useSubmitAttempt } from '@/lib/query';
import type { AnswerSubmission } from '@/lib/types';

// No time limit on the wire (Q3) — fixed default, matching the mock's 20 minutes.
const QUIZ_DURATION_SECONDS = 20 * 60;

type Phase = 'intro' | 'taking' | 'done';

function QuizRunner({ quizId, notebookTitle }: { quizId: string; notebookTitle: string }) {
  const quiz = useQuiz(quizId);
  const start = useStartAttempt();
  const [attemptId, setAttemptId] = useState<string | null>(null);
  const submit = useSubmitAttempt(attemptId ?? '');
  const [phase, setPhase] = useState<Phase>('intro');
  const [answers, setAnswers] = useState<Record<string, string>>({});

  const questions = quiz.data?.questions ?? [];
  const answered = questions.filter((q) => (answers[q.id] ?? '').trim() !== '').length;

  const buildSubmission = (): AnswerSubmission[] =>
    questions.map((q) => ({
      question_id: q.id,
      response:
        q.type === 'mcq' ? { selected_key: answers[q.id] ?? '' } : { text: answers[q.id] ?? '' },
    }));

  const doSubmit = () => {
    if (!attemptId) return;
    submit.mutate(buildSubmission(), {
      onSuccess: () => {
        if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
        setPhase('done');
      },
    });
  };

  const countdown = useCountdown(QUIZ_DURATION_SECONDS, {
    active: phase === 'taking',
    onExpire: doSubmit,
  });
  useLockdown(attemptId, phase === 'taking');

  const beginLockdown = () => {
    // requestFullscreen must run inside the click gesture.
    document.documentElement.requestFullscreen?.().catch(() => {});
    start.mutate(quizId, {
      onSuccess: (attempt) => {
        setAttemptId(attempt.id);
        setPhase('taking');
      },
    });
  };

  if (phase === 'intro') {
    return (
      <div style={{ padding: '34px', maxWidth: 660, margin: '0 auto' }}>
        <Card padding={28}>
          <Badge tone="info" dot>
            Published quiz
          </Badge>
          <h1
            style={{
              fontSize: 26,
              fontWeight: 800,
              margin: '14px 0 6px',
              color: 'var(--text-strong)',
              letterSpacing: '-0.01em',
            }}
          >
            {quiz.data?.title ?? 'Quiz'}
          </h1>
          <p style={{ fontSize: 14.5, color: 'var(--text-muted)', margin: '0 0 22px' }}>
            {questions.length} questions · grounded in {notebookTitle} · 20 minutes.
          </p>

          <div style={{ display: 'flex', gap: 12, marginBottom: 20 }}>
            {[
              ['quiz', `${questions.length} questions`],
              ['clock', '20 minutes'],
              ['shield', 'Lockdown mode'],
            ].map(([ic, t]) => (
              <div
                key={t}
                style={{
                  flex: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 8,
                  padding: '14px',
                  borderRadius: 14,
                  background: 'var(--slate-50)',
                  border: '1px solid var(--border-faint)',
                }}
              >
                <Icon name={ic as 'quiz'} size={19} color="var(--fr-accent)" />
                <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-strong)' }}>
                  {t}
                </span>
              </div>
            ))}
          </div>

          <Alert
            tone="warning"
            title="This quiz runs in browser lockdown"
            icon={<Icon name="lock" size={17} />}
          >
            The page enters fullscreen. Leaving fullscreen, switching tabs, copy/paste and
            right-click are detected and logged for your teacher.
          </Alert>
          {start.isError && (
            <div style={{ marginTop: 12 }}>
              <Alert tone="danger" icon={<Icon name="alert" size={16} />}>
                {(start.error as Error).message}
              </Alert>
            </div>
          )}
          <div style={{ marginTop: 22 }}>
            <Button
              block
              size="lg"
              iconLeft={<Icon name="shield" size={19} />}
              onClick={beginLockdown}
              disabled={start.isPending || quiz.isLoading}
            >
              {start.isPending ? 'Starting…' : 'Start quiz in lockdown'}
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  if (phase === 'done') {
    return (
      <div style={{ padding: 34, maxWidth: 560, margin: '0 auto' }}>
        <Card padding={30} style={{ textAlign: 'center' }}>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 66,
              height: 66,
              borderRadius: 999,
              background: 'var(--green-50)',
              marginBottom: 16,
            }}
          >
            <Icon name="partyPopper" size={32} color="var(--green-600)" />
          </span>
          <h1
            style={{
              fontSize: 25,
              fontWeight: 800,
              margin: '0 0 8px',
              color: 'var(--text-strong)',
            }}
          >
            Nicely done — all submitted!
          </h1>
          <p
            style={{
              fontSize: 14.5,
              color: 'var(--text-muted)',
              margin: '0 auto 20px',
              maxWidth: 400,
              lineHeight: 1.6,
            }}
          >
            Your answers are being graded. Scores stay hidden until your teacher reviews and
            finalises your attempt.
          </p>
          <StatusPill status="grading" />
        </Card>
      </div>
    );
  }

  // taking — lockdown chrome
  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        background: 'var(--fr-page)',
        display: 'flex',
        flexDirection: 'column',
        zIndex: 5,
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          padding: '13px 24px',
          background: 'var(--slate-900)',
          color: '#fff',
        }}
      >
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: 30,
            height: 30,
            borderRadius: 9,
            background: 'rgba(248,113,113,.18)',
          }}
        >
          <Icon name="lock" size={16} color="var(--red-200)" />
        </span>
        <div style={{ lineHeight: 1.2 }}>
          <b style={{ fontSize: 13.5, fontWeight: 700 }}>Exam lockdown active</b>
          <div style={{ fontSize: 11.5, color: 'var(--slate-400)' }}>
            Tab switches &amp; copy/paste are logged
          </div>
        </div>
        <span style={{ flex: 1 }} />
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 8,
            fontFamily: 'var(--font-mono)',
            fontSize: 15,
            fontWeight: 600,
            background: 'rgba(255,255,255,.1)',
            padding: '7px 13px',
            borderRadius: 11,
          }}
        >
          <Icon name="clock" size={16} color="var(--slate-300)" /> {countdown.label}
        </span>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '26px 28px 40px' }}>
        <div
          style={{
            maxWidth: 700,
            margin: '0 auto',
            display: 'flex',
            flexDirection: 'column',
            gap: 16,
          }}
        >
          {questions.map((q, i) => (
            <Card key={q.id} padding={22}>
              <div style={{ display: 'flex', gap: 12, marginBottom: 16 }}>
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: 28,
                    height: 28,
                    borderRadius: 9,
                    flex: 'none',
                    background: 'var(--fr-accent-soft)',
                    fontFamily: 'var(--font-mono)',
                    fontSize: 13.5,
                    fontWeight: 700,
                    color: 'var(--fr-accent)',
                  }}
                >
                  {i + 1}
                </span>
                <h3
                  style={{
                    fontSize: 16,
                    fontWeight: 700,
                    color: 'var(--text-strong)',
                    margin: 0,
                    lineHeight: 1.5,
                    paddingTop: 2,
                  }}
                >
                  {q.stem}
                </h3>
              </div>
              {q.type === 'mcq' ? (
                <RadioGroup
                  value={answers[q.id]}
                  onChange={(v) => setAnswers((a) => ({ ...a, [q.id]: v }))}
                  options={(q.options ?? []).map((o) => ({
                    value: o.key,
                    key: o.key,
                    label: o.text,
                  }))}
                />
              ) : (
                <Textarea
                  rows={4}
                  placeholder="Type your answer…"
                  value={answers[q.id] ?? ''}
                  onChange={(e) => setAnswers((a) => ({ ...a, [q.id]: e.target.value }))}
                />
              )}
            </Card>
          ))}
        </div>
      </div>

      <div
        style={{ borderTop: '1px solid var(--border)', background: '#fff', padding: '14px 28px' }}
      >
        <div
          style={{
            maxWidth: 700,
            margin: '0 auto',
            display: 'flex',
            alignItems: 'center',
            gap: 16,
          }}
        >
          <div style={{ flex: 1 }}>
            <div
              style={{ fontSize: 13, color: 'var(--text-muted)', fontWeight: 600, marginBottom: 6 }}
            >
              {answered} of {questions.length} answered
            </div>
            <ProgressBar value={answered} max={questions.length || 1} />
          </div>
          <Button
            size="lg"
            iconLeft={<Icon name="check" size={18} />}
            onClick={doSubmit}
            disabled={submit.isPending}
          >
            {submit.isPending ? 'Submitting…' : 'Submit quiz'}
          </Button>
        </div>
      </div>
    </div>
  );
}

export function QuizScreen() {
  const notebooks = useNotebooks();
  const [notebookId, setNotebookId] = useState('');
  const quizzes = useQuizzes(notebookId);
  const [quizId, setQuizId] = useState('');

  const published = (quizzes.data ?? []).filter((q) => q.status === 'published');
  const notebookTitle = notebooks.data?.find((n) => n.id === notebookId)?.title ?? 'this notebook';

  if (quizId) {
    return <QuizRunner quizId={quizId} notebookTitle={notebookTitle} />;
  }

  return (
    <div style={{ padding: '30px 34px', maxWidth: 660, margin: '0 auto' }}>
      <h1
        style={{ fontSize: 24, fontWeight: 800, color: 'var(--text-strong)', margin: '0 0 16px' }}
      >
        Choose a quiz
      </h1>
      <div style={{ maxWidth: 340, marginBottom: 22 }}>
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
          onChange={(e) => setNotebookId(e.target.value)}
          options={[
            { value: '', label: 'Select…' },
            ...(notebooks.data ?? []).map((n) => ({ value: n.id, label: n.title })),
          ]}
        />
      </div>

      {notebookId && quizzes.isLoading && (
        <p style={{ color: 'var(--text-muted)', fontSize: 14.5 }}>Loading quizzes…</p>
      )}
      {notebookId && !quizzes.isLoading && published.length === 0 && (
        <p style={{ color: 'var(--text-muted)', fontSize: 14.5 }}>
          No published quizzes in this notebook yet.
        </p>
      )}

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {published.map((q) => (
          <Card key={q.id} interactive onClick={() => setQuizId(q.id)} padding={20}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <span
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  width: 44,
                  height: 44,
                  borderRadius: 13,
                  background: 'var(--fr-accent-soft)',
                  flex: 'none',
                }}
              >
                <Icon name="quiz" size={22} color="var(--fr-accent)" />
              </span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <h3
                  style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-strong)', margin: 0 }}
                >
                  {q.title}
                </h3>
                <div style={{ fontSize: 12.5, color: 'var(--text-muted)', marginTop: 2 }}>
                  Published · lockdown
                </div>
              </div>
              <Icon name="arrowRight" size={17} color="var(--fr-accent)" />
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
