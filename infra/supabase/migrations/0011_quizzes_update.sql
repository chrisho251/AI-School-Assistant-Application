-- 0011_quizzes_update.sql — allow a quiz creator to update their own quizzes
--
-- Gap: 0005_rls.sql defined quizzes_read + quizzes_insert but no UPDATE policy,
-- so a teacher JWT could never change quiz status (e.g. draft → published) — RLS
-- silently blocked it. This adds an UPDATE policy scoped to the creator.
--
-- Idempotent: DROP … IF EXISTS before CREATE.

drop policy if exists "quizzes_update_own" on quizzes;
create policy "quizzes_update_own" on quizzes
    for update using (created_by = current_user_id());
