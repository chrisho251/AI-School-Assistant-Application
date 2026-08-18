/* Wire types for the ASAG backend.
 *
 * Field names are snake_case to match the JSON the FastAPI layer emits (it
 * serialises pydantic field names verbatim — see src/asag/models/api.py and
 * models/question.py). Display-only shaping (e.g. a notebook "ready" flag) is
 * derived in the query/screen layer, not assumed on the wire. */

export type Role = 'teacher' | 'student';

export type QuestionType = 'mcq' | 'short' | 'essay' | 'code';

export type Difficulty = 'easy' | 'medium' | 'hard';

// NotebookOut — note there is NO ready/status/source_count on the wire (Q4).
export interface Notebook {
  id: string;
  class_id: string;
  owner_id: string;
  title: string;
  subject?: string | null;
  description?: string | null;
}

// SourceOut — ingestion_status drives the StatusPill / poll loop.
export interface Source {
  id: string;
  notebook_id: string;
  source_type: string;
  original_filename: string;
  storage_url: string;
  ingestion_status: string;
}

export interface MCQOption {
  key: string;
  text: string;
}

// A quiz question as returned by GET /quizzes/{id} — answer key omitted server-side.
export interface QuizQuestion {
  id: string;
  ordinal: number;
  type: QuestionType;
  stem: string;
  options?: MCQOption[] | null;
}

// QuizSummary (list endpoints) plus the questions attached by GET /quizzes/{id}.
export interface QuizSummary {
  id: string;
  notebook_id: string;
  title: string;
  status: string;
}

export interface Quiz extends QuizSummary {
  questions: QuizQuestion[];
}

// AttemptOut — state returned by start/submit/get.
export interface Attempt {
  id: string;
  quiz_id: string;
  student_id: string;
  status: string;
}

// One answer in a submission; response shape depends on question type
// (mcq: {selected_key}, short: {text}).
export interface AnswerSubmission {
  question_id: string;
  response: Record<string, unknown>;
}

// AnswerReview — every score column, for the teacher review screen.
export interface AnswerReview {
  answer_id: string;
  question_id: string;
  ordinal: number;
  type: QuestionType;
  stem: string;
  response: Record<string, unknown>;
  auto_score?: number | null;
  auto_feedback?: string | null;
  teacher_score?: number | null;
  teacher_feedback?: string | null;
  final_score?: number | null;
}

// A proctor timeline entry (teacher review). Matches the jsonb element the
// backend stores: {type, payload, at} (see AssessmentApiRepository.append_proctor_event).
export interface ProctorEventOut {
  type: string;
  at: string;
  payload?: Record<string, unknown>;
}

// A grounding citation rendered as [N] in a chat answer (wired in Phase 5).
export interface Citation {
  n: number;
  filename: string;
  locator: string;
  type: string;
}
