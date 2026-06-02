-- 0007_fix_rls_recursion.sql — Break notebooks ↔ notebook_acl RLS cycle
--
-- Root cause:
--   notebooks_read_own  → queries notebook_acl (to check ACL grants)
--   notebook_acl_read_own → queries notebooks   (to check ownership)
--   → infinite recursion when RLS is enforced for a non-superuser role
--
-- Fix:
--   notebook_acl SELECT policy: compare only session variable (no table join)
--   notebook_acl INSERT policy: use SECURITY DEFINER helper that bypasses RLS
--     when looking up notebook ownership, so it never re-enters the cycle.

DROP POLICY IF EXISTS "notebook_acl_read_own" ON notebook_acl;
DROP POLICY IF EXISTS "notebook_acl_write_owner" ON notebook_acl;

-- SELECT: a user can see ACL rows where they are the grantee.
-- No reference to notebooks → cycle broken.
CREATE POLICY "notebook_acl_read_own" ON notebook_acl
    FOR SELECT USING (user_id = current_user_id());

-- Helper: check notebook ownership without triggering the notebooks RLS policy.
-- SECURITY DEFINER → runs as the function owner (postgres/superuser) which
-- bypasses RLS, so SELECT inside never fires notebooks_read_own again.
CREATE OR REPLACE FUNCTION is_notebook_owner(p_notebook_id uuid)
    RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER AS $$
        SELECT EXISTS(
            SELECT 1 FROM notebooks
            WHERE id = p_notebook_id
              AND owner_id = current_user_id()
        )
    $$;

GRANT EXECUTE ON FUNCTION is_notebook_owner(uuid) TO asag_app;

-- INSERT: only notebook owners may add ACL rows.
CREATE POLICY "notebook_acl_write_owner" ON notebook_acl
    FOR INSERT WITH CHECK (is_notebook_owner(notebook_id));
