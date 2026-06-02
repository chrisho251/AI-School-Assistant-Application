-- 0006_app_role.sql — Application role for RLS-enforced access
--
-- Why: PostgreSQL superusers (postgres) bypass RLS by default.
-- The application layer needs a non-superuser role so that RLS policies
-- are enforced on every query.
--
-- asag_app: used by API connections and integration tests.
-- It has DML permissions but NO superuser / BYPASSRLS privileges,
-- so all RLS policies apply normally.

-- Idempotent role creation
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'asag_app') THEN
        CREATE ROLE asag_app NOLOGIN;
    END IF;
END;
$$;

-- Schema access
GRANT USAGE ON SCHEMA public TO asag_app;

-- Table permissions (idempotent — safe to run multiple times)
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO asag_app;

-- Sequence permissions (for UUID-based tables with any serial fallback)
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO asag_app;

-- Function execution (needed for current_user_id(), current_org_id() helpers)
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO asag_app;

-- Allow postgres (the connection user) to SET ROLE asag_app.
-- In Supabase's managed environment, SET ROLE requires explicit membership.
GRANT asag_app TO postgres;
