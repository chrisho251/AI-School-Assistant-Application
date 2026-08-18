/* Typed HTTP client for the ASAG FastAPI backend — the single place the UI talks
 * to the network (R-FE3). Mirrors ui/lib/api.py 1:1; non-2xx responses raise
 * ApiError so screens can render a clean message. The bearer token is fixed per
 * instance (one client per logged-in user, built by AuthContext).
 *
 * Base URL: VITE_API_URL when set (prod), else "/api" — which Vite proxies to the
 * backend in dev (see vite.config.ts), sidestepping CORS. */
import type {
  AnswerReview,
  AnswerSubmission,
  Attempt,
  Difficulty,
  Notebook,
  ProctorEventOut,
  Quiz,
  QuestionType,
  QuizSummary,
  Source,
} from './types';

const BASE_URL = import.meta.env.VITE_API_URL || '/api';

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`${status}: ${detail}`);
    this.name = 'ApiError';
  }
}

async function extractDetail(resp: Response): Promise<string> {
  try {
    const body = await resp.clone().json();
    if (body && typeof body === 'object' && 'detail' in body) {
      return String((body as { detail: unknown }).detail);
    }
    return JSON.stringify(body);
  } catch {
    return (await resp.text().catch(() => '')) || resp.statusText;
  }
}

export class ApiClient {
  readonly token: string;
  private readonly baseUrl: string;

  constructor(token: string, baseUrl: string = BASE_URL) {
    this.token = token;
    this.baseUrl = baseUrl.replace(/\/$/, '');
  }

  private get authHeader(): Record<string, string> {
    return { Authorization: `Bearer ${this.token}` };
  }

  private async request<T>(method: string, path: string, init: RequestInit = {}): Promise<T> {
    const resp = await fetch(`${this.baseUrl}${path}`, {
      method,
      ...init,
      headers: { ...this.authHeader, ...(init.headers ?? {}) },
    });
    if (resp.status >= 400) throw new ApiError(resp.status, await extractDetail(resp));
    if (resp.status === 204) return undefined as T;
    const text = await resp.text();
    return (text ? JSON.parse(text) : undefined) as T;
  }

  private json<T>(method: string, path: string, body?: unknown): Promise<T> {
    return this.request<T>(method, path, {
      headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  }

  // ---- Meta ----
  health(): Promise<Record<string, string>> {
    return this.request('GET', '/health');
  }

  // ---- Notebooks ----
  listNotebooks(): Promise<Notebook[]> {
    return this.request('GET', '/notebooks');
  }

  getNotebook(notebookId: string): Promise<Notebook> {
    return this.request('GET', `/notebooks/${notebookId}`);
  }

  createNotebook(input: {
    classId: string;
    title: string;
    subject?: string | null;
    description?: string | null;
  }): Promise<Notebook> {
    return this.json('POST', '/notebooks', {
      class_id: input.classId,
      title: input.title,
      subject: input.subject ?? null,
      description: input.description ?? null,
    });
  }

  // ---- Sources ----
  uploadSource(input: { notebookId: string; file: File }): Promise<Source> {
    const form = new FormData();
    form.append('notebook_id', input.notebookId);
    form.append('file', input.file, input.file.name);
    return this.request('POST', '/sources', { body: form });
  }

  listSources(notebookId: string): Promise<Source[]> {
    return this.request('GET', `/sources/notebook/${notebookId}`);
  }

  // ---- Quizzes ----
  generateQuiz(input: {
    notebookId: string;
    title: string;
    mix: Partial<Record<QuestionType, number>>;
    difficulty?: Difficulty;
  }): Promise<QuizSummary> {
    return this.json('POST', '/quizzes/generate', {
      notebook_id: input.notebookId,
      title: input.title,
      mix: input.mix,
      difficulty: input.difficulty ?? 'medium',
    });
  }

  listQuizzes(notebookId: string): Promise<QuizSummary[]> {
    return this.request('GET', `/quizzes/notebook/${notebookId}`);
  }

  getQuiz(quizId: string): Promise<Quiz> {
    return this.request('GET', `/quizzes/${quizId}`);
  }

  publishQuiz(quizId: string): Promise<QuizSummary> {
    return this.json('PATCH', `/quizzes/${quizId}/publish`);
  }

  // ---- Attempts + review ----
  startAttempt(quizId: string): Promise<Attempt> {
    return this.json('POST', '/attempts/start', { quiz_id: quizId });
  }

  submitAttempt(attemptId: string, answers: AnswerSubmission[]): Promise<Attempt> {
    return this.json('POST', `/attempts/${attemptId}/submit`, { answers });
  }

  getAttempt(attemptId: string): Promise<Attempt> {
    return this.request('GET', `/attempts/${attemptId}`);
  }

  listAttempts(quizId: string): Promise<Attempt[]> {
    return this.request('GET', `/attempts/quiz/${quizId}`);
  }

  getAttemptAnswers(attemptId: string): Promise<AnswerReview[]> {
    return this.request('GET', `/attempts/${attemptId}/answers`);
  }

  overrideAnswerScore(input: {
    attemptId: string;
    answerId: string;
    score: number;
    feedback?: string | null;
  }): Promise<Record<string, string>> {
    return this.json('PATCH', `/attempts/${input.attemptId}/answers/${input.answerId}/score`, {
      score: input.score,
      feedback: input.feedback ?? null,
    });
  }

  finalizeAttempt(attemptId: string): Promise<Record<string, number>> {
    return this.json('POST', `/attempts/${attemptId}/finalize`);
  }

  // ---- Proctor events ----
  recordProctorEvent(
    attemptId: string,
    eventType: string,
    payload: Record<string, unknown> = {},
  ): Promise<void> {
    return this.json('POST', `/attempts/${attemptId}/proctor_event`, {
      event_type: eventType,
      payload,
    });
  }

  getProctorEvents(attemptId: string): Promise<ProctorEventOut[]> {
    return this.request('GET', `/attempts/${attemptId}/proctor_events`);
  }

  // ---- Chat (SSE) ----
  /* Yield answer tokens from GET /chat/{notebookId}. Uses fetch + a stream reader
   * (not EventSource, which cannot send the Authorization header) and parses the
   * SSE frames the way the Python client does: event:token → yield, event:error →
   * throw ApiError, event:done → stop. */
  async *streamChat(input: {
    notebookId: string;
    question: string;
    conversationId?: string;
    signal?: AbortSignal;
  }): AsyncGenerator<string, void, unknown> {
    const params = new URLSearchParams({ q: input.question });
    if (input.conversationId) params.set('conversation_id', input.conversationId);

    const resp = await fetch(`${this.baseUrl}/chat/${input.notebookId}?${params}`, {
      headers: { ...this.authHeader, Accept: 'text/event-stream' },
      signal: input.signal,
    });
    if (resp.status >= 400) throw new ApiError(resp.status, await extractDetail(resp));
    if (!resp.body) throw new ApiError(502, 'Empty chat stream');

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let event = 'message';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let nl: number;
      while ((nl = buffer.indexOf('\n')) !== -1) {
        const line = buffer.slice(0, nl).replace(/\r$/, '');
        buffer = buffer.slice(nl + 1);

        if (line.startsWith('event:')) {
          event = line.slice(6).trim();
        } else if (line.startsWith('data:')) {
          // SSE strips exactly one optional leading space after the colon.
          let data = line.slice(5);
          if (data.startsWith(' ')) data = data.slice(1);
          if (event === 'error') throw new ApiError(502, data);
          if (event === 'token') yield data;
        } else if (line === '') {
          event = 'message'; // blank line terminates one SSE event
        }
      }
    }
  }
}
