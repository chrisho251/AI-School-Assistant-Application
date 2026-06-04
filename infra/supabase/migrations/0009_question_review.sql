-- 0009_question_review.sql — needs_review flag on generated questions
-- Depends on: 0004_assessment.sql
--
-- The quiz generator and the grounding-validation pass flag questions whose
-- answer is not fully supported by the cited chunks. Teachers fix these before
-- publishing — so the flag must survive the draft round-trip, not just live in
-- memory at generation time.

alter table questions
    add column if not exists needs_review boolean not null default false;

create index if not exists questions_needs_review_idx
    on questions(needs_review)
    where needs_review;
