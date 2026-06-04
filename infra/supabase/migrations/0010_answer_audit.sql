-- 0010_answer_audit.sql — audit column for teacher score overrides
-- Depends on: 0004_assessment.sql
--
-- Teacher review (Session 7B) overrides answer scores and finalises attempts.
-- We must record *who* last wrote each answer's score so an override is auditable
-- (proposal §8 — audit log on answers). The existing updated_at says *when*;
-- updated_by says *who*. Nullable: rows graded only by the auto-grader have no
-- teacher attribution.

alter table answers
    add column if not exists updated_by uuid references users(id);
