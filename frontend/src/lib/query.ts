/* react-query hooks over ApiClient (R-FE7: server state cached here, not in
 * component state). Query keys are keyed by resource + id so mutations can
 * invalidate precisely. Lists that reflect async backend work (source ingestion,
 * attempt grading) poll on an interval until they settle. */
import { useMutation, useQuery, useQueryClient, type UseQueryResult } from '@tanstack/react-query';

import { useApi } from './auth';
import type { AnswerSubmission, Difficulty, QuestionType } from './types';
import type {
  AnswerReview,
  Attempt,
  Notebook,
  ProctorEventOut,
  Quiz,
  QuizSummary,
  Source,
} from './types';
import { ApiClient } from './api';

export const keys = {
  notebooks: ['notebooks'] as const,
  notebook: (id: string) => ['notebooks', id] as const,
  sources: (nbId: string) => ['sources', nbId] as const,
  quizzes: (nbId: string) => ['quizzes', nbId] as const,
  quiz: (id: string) => ['quiz', id] as const,
  attempts: (quizId: string) => ['attempts', quizId] as const,
  attemptAnswers: (attemptId: string) => ['attempt-answers', attemptId] as const,
  proctorEvents: (attemptId: string) => ['proctor-events', attemptId] as const,
};

/** ApiClient is only ever consumed inside the authed shell, so it is non-null there. */
function useClient(): ApiClient {
  const api = useApi();
  if (!api) throw new Error('API client unavailable — not authenticated');
  return api;
}

// --------------------------------------------------------------------------- //
// Queries                                                                      //
// --------------------------------------------------------------------------- //

export function useNotebooks(): UseQueryResult<Notebook[]> {
  const api = useClient();
  return useQuery({ queryKey: keys.notebooks, queryFn: () => api.listNotebooks() });
}

export function useNotebook(id: string): UseQueryResult<Notebook> {
  const api = useClient();
  return useQuery({
    queryKey: keys.notebook(id),
    queryFn: () => api.getNotebook(id),
    enabled: !!id,
  });
}

const INGESTING = new Set(['pending', 'processing']);

export function useSources(notebookId: string): UseQueryResult<Source[]> {
  const api = useClient();
  return useQuery({
    queryKey: keys.sources(notebookId),
    queryFn: () => api.listSources(notebookId),
    enabled: !!notebookId,
    // Poll while any source is still ingesting so the StatusPill flips to ready.
    refetchInterval: (query) =>
      (query.state.data ?? []).some((s) => INGESTING.has(s.ingestion_status)) ? 2500 : false,
  });
}

export function useQuizzes(notebookId: string): UseQueryResult<QuizSummary[]> {
  const api = useClient();
  return useQuery({
    queryKey: keys.quizzes(notebookId),
    queryFn: () => api.listQuizzes(notebookId),
    enabled: !!notebookId,
  });
}

export function useQuiz(id: string): UseQueryResult<Quiz> {
  const api = useClient();
  return useQuery({ queryKey: keys.quiz(id), queryFn: () => api.getQuiz(id), enabled: !!id });
}

export function useAttempts(quizId: string): UseQueryResult<Attempt[]> {
  const api = useClient();
  return useQuery({
    queryKey: keys.attempts(quizId),
    queryFn: () => api.listAttempts(quizId),
    enabled: !!quizId,
  });
}

export function useAttemptAnswers(attemptId: string): UseQueryResult<AnswerReview[]> {
  const api = useClient();
  return useQuery({
    queryKey: keys.attemptAnswers(attemptId),
    queryFn: () => api.getAttemptAnswers(attemptId),
    enabled: !!attemptId,
    // Auto-grading is async; poll until every answer has an auto_score.
    refetchInterval: (query) =>
      (query.state.data ?? []).some((a) => a.auto_score == null) ? 2500 : false,
  });
}

export function useProctorEvents(attemptId: string): UseQueryResult<ProctorEventOut[]> {
  const api = useClient();
  return useQuery({
    queryKey: keys.proctorEvents(attemptId),
    queryFn: () => api.getProctorEvents(attemptId),
    enabled: !!attemptId,
  });
}

// --------------------------------------------------------------------------- //
// Mutations                                                                    //
// --------------------------------------------------------------------------- //

export function useCreateNotebook() {
  const api = useClient();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      classId: string;
      title: string;
      subject?: string | null;
      description?: string | null;
    }) => api.createNotebook(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.notebooks }),
  });
}

export function useUploadSource(notebookId: string) {
  const api = useClient();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => api.uploadSource({ notebookId, file }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.sources(notebookId) }),
  });
}

export function useGenerateQuiz(notebookId: string) {
  const api = useClient();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: {
      title: string;
      mix: Partial<Record<QuestionType, number>>;
      difficulty?: Difficulty;
    }) => api.generateQuiz({ notebookId, ...input }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.quizzes(notebookId) }),
  });
}

export function usePublishQuiz(notebookId: string) {
  const api = useClient();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (quizId: string) => api.publishQuiz(quizId),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.quizzes(notebookId) }),
  });
}

export function useStartAttempt() {
  const api = useClient();
  return useMutation({ mutationFn: (quizId: string) => api.startAttempt(quizId) });
}

export function useSubmitAttempt(attemptId: string) {
  const api = useClient();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (answers: AnswerSubmission[]) => api.submitAttempt(attemptId, answers),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.attemptAnswers(attemptId) }),
  });
}

export function useOverrideScore(attemptId: string) {
  const api = useClient();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: { answerId: string; score: number; feedback?: string | null }) =>
      api.overrideAnswerScore({ attemptId, ...input }),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.attemptAnswers(attemptId) }),
  });
}

export function useFinalizeAttempt(attemptId: string) {
  const api = useClient();
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.finalizeAttempt(attemptId),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.attemptAnswers(attemptId) }),
  });
}
