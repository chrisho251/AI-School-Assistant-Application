-- 0005_rls.sql — Row-level security policies
-- Enables RLS on all user-data tables and defines access control policies
-- Assumes session variables set current_user_id and current_org_id
-- Idempotent: DROP POLICY IF EXISTS before every CREATE POLICY

-- Helper function to get current user ID from session variable
create or replace function current_user_id() returns uuid as $$
    select (current_setting('app.current_user_id', true))::uuid
$$ language sql stable;

-- Helper function to get current org ID from session variable
create or replace function current_org_id() returns uuid as $$
    select (current_setting('app.current_org_id', true))::uuid
$$ language sql stable;

-- Enable RLS on all user-facing tables (idempotent — safe to run multiple times)
alter table organizations enable row level security;
alter table users enable row level security;
alter table classes enable row level security;
alter table class_members enable row level security;
alter table notebooks enable row level security;
alter table notebook_acl enable row level security;
alter table sources enable row level security;
alter table chunks enable row level security;
alter table conversations enable row level security;
alter table messages enable row level security;
alter table artifacts enable row level security;
alter table quizzes enable row level security;
alter table questions enable row level security;
alter table attempts enable row level security;
alter table answers enable row level security;

-- USERS
drop policy if exists "users_read_own_org" on users;
create policy "users_read_own_org" on users
    for select using (org_id = current_org_id());

drop policy if exists "users_insert_own" on users;
create policy "users_insert_own" on users
    for insert with check (org_id = current_org_id() and id = current_user_id());

drop policy if exists "users_update_own" on users;
create policy "users_update_own" on users
    for update using (id = current_user_id());

-- CLASSES
drop policy if exists "classes_read_own_org" on classes;
create policy "classes_read_own_org" on classes
    for select using (org_id = current_org_id());

-- CLASS_MEMBERS
drop policy if exists "class_members_read_own_org" on class_members;
create policy "class_members_read_own_org" on class_members
    for select using (
        class_id in (select id from classes where org_id = current_org_id())
    );

-- NOTEBOOKS: user can read if they are owner, have ACL grant, or are class member/teacher
drop policy if exists "notebooks_read_own" on notebooks;
create policy "notebooks_read_own" on notebooks
    for select using (
        owner_id = current_user_id()
        or exists (
            select 1 from notebook_acl
            where notebook_acl.notebook_id = notebooks.id
            and notebook_acl.user_id = current_user_id()
        )
        or exists (
            select 1 from class_members cm
            where cm.class_id = notebooks.class_id
            and cm.student_id = current_user_id()
        )
        or exists (
            select 1 from users u
            where u.id = current_user_id()
            and u.id = (select teacher_id from classes where id = notebooks.class_id)
        )
    );

drop policy if exists "notebooks_insert_own" on notebooks;
create policy "notebooks_insert_own" on notebooks
    for insert with check (owner_id = current_user_id());

drop policy if exists "notebooks_update_own" on notebooks;
create policy "notebooks_update_own" on notebooks
    for update using (owner_id = current_user_id());

-- NOTEBOOK_ACL
-- Note: recursion-free versions defined in 0007_fix_rls_recursion.sql
-- These are left here as original; 0007 drops and recreates them correctly.
drop policy if exists "notebook_acl_read_own" on notebook_acl;
create policy "notebook_acl_read_own" on notebook_acl
    for select using (
        notebook_id in (
            select id from notebooks where owner_id = current_user_id()
        )
    );

drop policy if exists "notebook_acl_write_owner" on notebook_acl;
create policy "notebook_acl_write_owner" on notebook_acl
    for insert with check (
        notebook_id in (
            select id from notebooks where owner_id = current_user_id()
        )
    );

-- SOURCES
drop policy if exists "sources_read_notebook" on sources;
create policy "sources_read_notebook" on sources
    for select using (
        notebook_id in (
            select id from notebooks
            where owner_id = current_user_id()
            or exists (
                select 1 from notebook_acl
                where notebook_acl.notebook_id = notebooks.id
                and notebook_acl.user_id = current_user_id()
            )
            or exists (
                select 1 from class_members cm
                where cm.class_id = notebooks.class_id
                and cm.student_id = current_user_id()
            )
            or exists (
                select 1 from users u
                where u.id = current_user_id()
                and u.id = (select teacher_id from classes where id = notebooks.class_id)
            )
        )
    );

drop policy if exists "sources_insert_notebook_owner" on sources;
create policy "sources_insert_notebook_owner" on sources
    for insert with check (
        notebook_id in (
            select id from notebooks where owner_id = current_user_id()
        )
    );

-- CHUNKS
drop policy if exists "chunks_read_notebook" on chunks;
create policy "chunks_read_notebook" on chunks
    for select using (
        notebook_id in (
            select id from notebooks
            where owner_id = current_user_id()
            or exists (
                select 1 from notebook_acl
                where notebook_acl.notebook_id = notebooks.id
                and notebook_acl.user_id = current_user_id()
            )
            or exists (
                select 1 from class_members cm
                where cm.class_id = notebooks.class_id
                and cm.student_id = current_user_id()
            )
            or exists (
                select 1 from users u
                where u.id = current_user_id()
                and u.id = (select teacher_id from classes where id = notebooks.class_id)
            )
        )
    );

-- CONVERSATIONS
drop policy if exists "conversations_read_own" on conversations;
create policy "conversations_read_own" on conversations
    for select using (user_id = current_user_id());

drop policy if exists "conversations_insert_own" on conversations;
create policy "conversations_insert_own" on conversations
    for insert with check (user_id = current_user_id());

-- MESSAGES
drop policy if exists "messages_read_conversation" on messages;
create policy "messages_read_conversation" on messages
    for select using (
        conversation_id in (
            select id from conversations where user_id = current_user_id()
        )
    );

drop policy if exists "messages_insert_own_conversation" on messages;
create policy "messages_insert_own_conversation" on messages
    for insert with check (
        conversation_id in (
            select id from conversations where user_id = current_user_id()
        )
    );

-- ARTIFACTS
drop policy if exists "artifacts_read_notebook" on artifacts;
create policy "artifacts_read_notebook" on artifacts
    for select using (
        notebook_id in (
            select id from notebooks
            where owner_id = current_user_id()
            or exists (
                select 1 from notebook_acl
                where notebook_acl.notebook_id = notebooks.id
                and notebook_acl.user_id = current_user_id()
            )
            or exists (
                select 1 from class_members cm
                where cm.class_id = notebooks.class_id
                and cm.student_id = current_user_id()
            )
            or exists (
                select 1 from users u
                where u.id = current_user_id()
                and u.id = (select teacher_id from classes where id = notebooks.class_id)
            )
        )
    );

-- QUIZZES
drop policy if exists "quizzes_read_notebook" on quizzes;
create policy "quizzes_read_notebook" on quizzes
    for select using (
        notebook_id in (
            select id from notebooks
            where owner_id = current_user_id()
            or exists (
                select 1 from notebook_acl
                where notebook_acl.notebook_id = notebooks.id
                and notebook_acl.user_id = current_user_id()
            )
            or exists (
                select 1 from class_members cm
                where cm.class_id = notebooks.class_id
                and cm.student_id = current_user_id()
            )
            or exists (
                select 1 from users u
                where u.id = current_user_id()
                and u.id = (select teacher_id from classes where id = notebooks.class_id)
            )
        )
    );

drop policy if exists "quizzes_insert_own" on quizzes;
create policy "quizzes_insert_own" on quizzes
    for insert with check (created_by = current_user_id());

-- QUESTIONS
drop policy if exists "questions_read_quiz" on questions;
create policy "questions_read_quiz" on questions
    for select using (
        quiz_id in (
            select id from quizzes
            where notebook_id in (
                select id from notebooks
                where owner_id = current_user_id()
                or exists (
                    select 1 from notebook_acl
                    where notebook_acl.notebook_id = notebooks.id
                    and notebook_acl.user_id = current_user_id()
                )
                or exists (
                    select 1 from class_members cm
                    where cm.class_id = notebooks.class_id
                    and cm.student_id = current_user_id()
                )
                or exists (
                    select 1 from users u
                    where u.id = current_user_id()
                    and u.id = (select teacher_id from classes where id = notebooks.class_id)
                )
            )
        )
    );

-- ATTEMPTS
drop policy if exists "attempts_read_own" on attempts;
create policy "attempts_read_own" on attempts
    for select using (
        student_id = current_user_id()
        or quiz_id in (
            select id from quizzes where created_by = current_user_id()
        )
    );

drop policy if exists "attempts_insert_own" on attempts;
create policy "attempts_insert_own" on attempts
    for insert with check (student_id = current_user_id());

-- ANSWERS
drop policy if exists "answers_read_own" on answers;
create policy "answers_read_own" on answers
    for select using (
        attempt_id in (
            select id from attempts
            where student_id = current_user_id()
            or quiz_id in (
                select id from quizzes where created_by = current_user_id()
            )
        )
    );

drop policy if exists "answers_insert_own_attempt" on answers;
create policy "answers_insert_own_attempt" on answers
    for insert with check (
        attempt_id in (
            select id from attempts where student_id = current_user_id()
        )
    );

drop policy if exists "answers_update_own_or_quiz_creator" on answers;
create policy "answers_update_own_or_quiz_creator" on answers
    for update using (
        attempt_id in (
            select id from attempts
            where student_id = current_user_id()
            or quiz_id in (
                select id from quizzes where created_by = current_user_id()
            )
        )
    );
