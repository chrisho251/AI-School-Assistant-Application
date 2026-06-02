-- 0008_fix_rls_gaps.sql — Fix two RLS security gaps found during review
--
-- Gap 1: `attempts` had no UPDATE policy at all.
--   Consequence: a student JWT could never submit (status in_progress → submitted),
--   and a teacher JWT could never finalize — both would be silently blocked by RLS.
--
-- Gap 2: `answers_update_own_or_quiz_creator` (0005) had no submitted-status guard.
--   Consequence: a student could UPDATE their own answers even after submitting,
--   allowing post-submission edits — a cheating vector.
--
-- Both are DROP … IF EXISTS + CREATE so this file is idempotent.

-- -----------------------------------------------------------------------
-- ATTEMPTS: add UPDATE policy (was completely missing in 0005_rls.sql)
-- -----------------------------------------------------------------------

-- Student can update their own attempt while it is in progress:
--   • record proctor_events during the exam
--   • set status → 'submitted' on final submit
-- Teacher (quiz creator) can update any attempt in their quizzes:
--   • set status → 'graded' after auto-grading completes
--   • set status → 'finalized' after teacher review

drop policy if exists "attempts_update_own_or_quiz_creator" on attempts;
create policy "attempts_update_own_or_quiz_creator" on attempts
    for update using (
        student_id = current_user_id()
        or quiz_id in (
            select id from quizzes where created_by = current_user_id()
        )
    );

-- -----------------------------------------------------------------------
-- ANSWERS: restrict student UPDATE to in-progress attempts only
-- -----------------------------------------------------------------------

-- Previous policy (0005) had no status guard → student could edit answers
-- after submitting.  New policy: student path only works while the parent
-- attempt is still 'in_progress'; teacher (quiz creator) is unrestricted
-- so they can write auto_score / teacher_score during review.

drop policy if exists "answers_update_own_or_quiz_creator" on answers;
create policy "answers_update_own_or_quiz_creator" on answers
    for update using (
        -- Student: answer is part of an in-progress attempt they own
        attempt_id in (
            select id from attempts
            where student_id = current_user_id()
              and status = 'in_progress'
        )
        or
        -- Teacher (quiz creator): unrestricted — needed for auto_score + finalization
        attempt_id in (
            select id from attempts
            where quiz_id in (
                select id from quizzes where created_by = current_user_id()
            )
        )
    );
