/*
  PostgreSQL parity for RBAC.sp* / RBAC.usp_* procedures extracted from
  workflow_engine/sql_mssql/rbac_api.sql.

  Schema note: PG uses quoted PascalCase "RBAC"."Sessions" etc. (from rbac_schema.sql).
  A lowercase rbac synonym schema is NOT created; callers use the quoted form.
  The trigger RBAC.trg_UserRoleGrants_EnforceBypassScopeApproval is omitted here
  (PG trigger DDL requires a separate trigger function + CREATE TRIGGER; the
  business rule is enforced at the application layer for the PG deployment).

  Depends on:
    rbac_schema.sql   – "RBAC"."Sessions", "RBAC"."Users", "RBAC"."Session_Roles",
                         "RBAC"."Group_Users", "RBAC"."Group_Roles", "RBAC"."Roles",
                         "RBAC"."Role_Permissions", "RBAC"."Permissions",
                         "RBAC"."IdentityProviders", "RBAC"."ScopeIdentityProviders",
                         "RBAC"."ExternalIdentities", "RBAC"."UserRoleGrants",
                         "RBAC"."BypassScopeApprovals"
    portal_clinical_schema.sql – portal."NavTree", portal."Role2Node"
*/

-- ──────────────────────────────────────────────────────────────────────────────
-- RBAC.spGetUserIdByEmail  → rbac.spgetuseridebyemail
-- ──────────────────────────────────────────────────────────────────────────────

-- Minimal role view used by NavTree helpers (Azure has richer definition).
CREATE OR REPLACE VIEW "e_portal"."viewUserAllRoles" AS
SELECT ur."UserId" AS "UserId", ur."RoleId" AS "RoleId"
FROM "e_portal"."UserRoles" ur;
CREATE OR REPLACE VIEW portal."viewUserAllRoles" AS
SELECT * FROM "e_portal"."viewUserAllRoles";

CREATE OR REPLACE FUNCTION "RBAC".spgetuseridbyemail(
  p_email text
)
RETURNS TABLE(user_id int)
LANGUAGE sql STABLE AS $$
  SELECT u."ID"
  FROM "RBAC"."Users" u
  WHERE u.email = p_email AND u."Active" = 1;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- RBAC.spGetUserRoles  → rbac.spgetuserroles
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION "RBAC".spgetuserroles(
  p_user_id int
)
RETURNS TABLE(user_id int, role text, role_id int)
LANGUAGE sql STABLE AS $$
  SELECT DISTINCT
    p_user_id AS user_id,
    r."Name"::text AS role,
    r."ID"   AS role_id
  FROM "RBAC"."Group_Users"  gu
  JOIN "RBAC"."Group_Roles"  gr ON gr."GroupID" = gu."GroupID"
  JOIN "RBAC"."Roles"        r  ON r."ID"       = gr."RoleID"
  WHERE gu."UserID" = p_user_id
  ORDER BY 2;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- RBAC.usp_session_revoke_role
-- Returns two result sets in MSSQL (revocation summary + status envelope).
-- PG: returns the revocation summary; status is surfaced via RAISE on error.
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION "RBAC".usp_session_revoke_role(
  p_session_id int,
  p_role_id int
)
RETURNS TABLE(session_id int, role_id int, rows_affected bigint)
LANGUAGE plpgsql AS $$
DECLARE v_rows bigint;
BEGIN
  IF p_session_id IS NULL OR p_session_id <= 0 THEN
    RAISE EXCEPTION 'ValidationError: session_id must be > 0.';
  END IF;
  IF p_role_id IS NULL OR p_role_id <= 0 THEN
    RAISE EXCEPTION 'ValidationError: role_id must be > 0.';
  END IF;

  DELETE FROM "RBAC"."Session_Roles"
  WHERE "SessionID" = p_session_id AND "RoleID" = p_role_id;
  GET DIAGNOSTICS v_rows = ROW_COUNT;

  RETURN QUERY SELECT p_session_id, p_role_id, v_rows;
END;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- RBAC.usp_session_is_authorized
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION "RBAC".usp_session_is_authorized(
  p_session_id int,
  p_obj_id int,
  p_operation_id int
)
RETURNS TABLE(session_id int, obj_id int, operation_id int, is_authorized boolean)
LANGUAGE plpgsql STABLE AS $$
BEGIN
  IF p_session_id IS NULL OR p_session_id <= 0 THEN
    RAISE EXCEPTION 'ValidationError: session_id must be > 0.';
  END IF;
  IF p_obj_id IS NULL OR p_obj_id <= 0 THEN
    RAISE EXCEPTION 'ValidationError: obj_id must be > 0.';
  END IF;
  IF p_operation_id IS NULL OR p_operation_id <= 0 THEN
    RAISE EXCEPTION 'ValidationError: operation_id must be > 0.';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM "RBAC"."Sessions" WHERE "ID" = p_session_id) THEN
    RAISE EXCEPTION 'BusinessRule: Session not found.';
  END IF;

  RETURN QUERY
  WITH sess_user AS (
    SELECT s."UserID" FROM "RBAC"."Sessions" s WHERE s."ID" = p_session_id
  ),
  effective_roles AS (
    SELECT sr."RoleID"
    FROM "RBAC"."Session_Roles" sr
    WHERE sr."SessionID" = p_session_id
    UNION
    SELECT gr."RoleID"
    FROM sess_user su
    JOIN "RBAC"."Group_Users" gu ON gu."UserID" = su."UserID"
    JOIN "RBAC"."Group_Roles" gr ON gr."GroupID" = gu."GroupID"
  )
  SELECT
    p_session_id, p_obj_id, p_operation_id,
    EXISTS (
      SELECT 1
      FROM effective_roles er
      JOIN "RBAC"."Role_Permissions" rp ON rp."RoleID" = er."RoleID"
      JOIN "RBAC"."Permissions" p ON p."ID" = rp."PermissionID"
      WHERE p."ObjID" = p_obj_id AND p."OperationID" = p_operation_id
    ) AS is_authorized;
END;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- RBAC.usp_session_get_effective_roles_v2
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION "RBAC".usp_session_get_effective_roles_v2(
  p_session_id int
)
RETURNS TABLE(
  session_id int, role_id int, role_name text, role_source text, bypass_scope boolean
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
  IF p_session_id IS NULL OR p_session_id <= 0 THEN
    RAISE EXCEPTION 'ValidationError: session_id must be > 0.';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM "RBAC"."Sessions" WHERE "ID" = p_session_id) THEN
    RAISE EXCEPTION 'BusinessRule: Session not found.';
  END IF;

  RETURN QUERY
  WITH sess_user AS (
    SELECT s."UserID" FROM "RBAC"."Sessions" s WHERE s."ID" = p_session_id
  ),
  effective_roles AS (
    SELECT sr."RoleID", 'DirectSessionRole'::text AS role_source
    FROM "RBAC"."Session_Roles" sr
    WHERE sr."SessionID" = p_session_id
    UNION
    SELECT gr."RoleID", 'GroupInheritedRole'::text
    FROM sess_user su
    JOIN "RBAC"."Group_Users" gu ON gu."UserID" = su."UserID"
    JOIN "RBAC"."Group_Roles" gr ON gr."GroupID" = gu."GroupID"
  )
  SELECT DISTINCT
    p_session_id,
    er."RoleID",
    r."Name"::text AS role_name,
    er.role_source,
    COALESCE(r."BypassScope", false) AS bypass_scope
  FROM effective_roles er
  JOIN "RBAC"."Roles" r ON r."ID" = er."RoleID"
  ORDER BY er.role_source, er."RoleID";
END;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- RBAC.usp_session_get_effective_permissions
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION "RBAC".usp_session_get_effective_permissions(
  p_session_id int
)
RETURNS TABLE(
  role_id int, role_name text, permission_id int, permission_name text,
  obj_id int, operation_id int, role_source text
)
LANGUAGE plpgsql STABLE AS $$
BEGIN
  IF p_session_id IS NULL OR p_session_id <= 0 THEN
    RAISE EXCEPTION 'ValidationError: session_id must be > 0.';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM "RBAC"."Sessions" WHERE "ID" = p_session_id) THEN
    RAISE EXCEPTION 'BusinessRule: Session not found.';
  END IF;

  RETURN QUERY
  WITH sess_user AS (
    SELECT s."UserID" FROM "RBAC"."Sessions" s WHERE s."ID" = p_session_id
  ),
  effective_roles AS (
    SELECT sr."RoleID", 'DirectSessionRole'::text AS role_source
    FROM "RBAC"."Session_Roles" sr WHERE sr."SessionID" = p_session_id
    UNION
    SELECT gr."RoleID", 'GroupInheritedRole'::text
    FROM sess_user su
    JOIN "RBAC"."Group_Users" gu ON gu."UserID" = su."UserID"
    JOIN "RBAC"."Group_Roles" gr ON gr."GroupID" = gu."GroupID"
  )
  SELECT DISTINCT
    er."RoleID",
    r."Name"::text AS role_name,
    rp."PermissionID",
    p."Name"::text AS permission_name,
    p."ObjID",
    p."OperationID",
    er.role_source
  FROM effective_roles er
  JOIN "RBAC"."Roles"            r  ON r."ID"    = er."RoleID"
  JOIN "RBAC"."Role_Permissions" rp ON rp."RoleID" = er."RoleID"
  JOIN "RBAC"."Permissions"      p  ON p."ID"    = rp."PermissionID"
  ORDER BY er.role_source, er."RoleID", rp."PermissionID";
END;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- RBAC.usp_session_assign_role
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION "RBAC".usp_session_assign_role(
  p_session_id int,
  p_role_id int
)
RETURNS TABLE(session_id int, role_id int)
LANGUAGE plpgsql AS $$
BEGIN
  IF p_session_id IS NULL OR p_session_id <= 0 THEN
    RAISE EXCEPTION 'ValidationError: session_id must be > 0.';
  END IF;
  IF p_role_id IS NULL OR p_role_id <= 0 THEN
    RAISE EXCEPTION 'ValidationError: role_id must be > 0.';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM "RBAC"."Sessions" WHERE "ID" = p_session_id) THEN
    RAISE EXCEPTION 'BusinessRule: Session not found.';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM "RBAC"."Roles" WHERE "ID" = p_role_id) THEN
    RAISE EXCEPTION 'BusinessRule: Role not found.';
  END IF;

  INSERT INTO "RBAC"."Session_Roles" ("SessionID", "RoleID")
  VALUES (p_session_id, p_role_id)
  ON CONFLICT DO NOTHING;

  RETURN QUERY
  SELECT sr."SessionID", sr."RoleID"
  FROM "RBAC"."Session_Roles" sr
  WHERE sr."SessionID" = p_session_id AND sr."RoleID" = p_role_id;
END;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- RBAC.spResolveUserByScopeIdentity
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION "RBAC".spresolveuserbyscopeidentity(
  p_scope_id int,
  p_issuer text,
  p_subject text
)
RETURNS TABLE(provider_id int, user_id int)
LANGUAGE plpgsql AS $$
DECLARE
  v_provider_id int;
  v_user_id     int;
BEGIN
  IF p_scope_id IS NULL OR p_scope_id <= 0
     OR p_issuer IS NULL OR btrim(p_issuer) = ''
     OR p_subject IS NULL OR btrim(p_subject) = ''
  THEN
    RAISE EXCEPTION 'ValidationError: scope_id, issuer and subject are required.';
  END IF;

  SELECT ip."ProviderID" INTO v_provider_id
  FROM "RBAC"."ScopeIdentityProviders" sip
  JOIN "RBAC"."IdentityProviders" ip ON ip."ProviderID" = sip."ProviderID"
  WHERE sip."ScopeID" = p_scope_id AND sip."Active" = true
    AND ip."Active" = true AND ip."Issuer" = p_issuer
  LIMIT 1;

  IF v_provider_id IS NULL THEN
    RAISE EXCEPTION 'BusinessRule: Scope is not configured for the provided issuer.';
  END IF;

  SELECT ei."UserID" INTO v_user_id
  FROM "RBAC"."ExternalIdentities" ei
  JOIN "RBAC"."Users" u ON u."ID" = ei."UserID"
  WHERE ei."ProviderID" = v_provider_id AND ei."Subject" = p_subject
    AND ei."Active" = true AND u."Active" = 1
  LIMIT 1;

  IF v_user_id IS NOT NULL THEN
    UPDATE "RBAC"."ExternalIdentities"
    SET "LastLoginAtUtc" = now() AT TIME ZONE 'utc'
    WHERE "ProviderID" = v_provider_id AND "Subject" = p_subject AND "UserID" = v_user_id;
  END IF;

  RETURN QUERY SELECT v_provider_id, v_user_id;
END;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- RBAC.spGetUserNavTree  (portal NavTree filtered by role + scope)
-- Uses portal."viewUserAllRoles" which must exist (created in portal_clinical_schema).
-- Returns nodes the user is authorised to see based on Role2Node grants.
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION "RBAC".spgetusernavtree(
  p_user_id int,
  p_role_id int,
  p_scope_id int DEFAULT NULL
)
RETURNS TABLE(id smallint, parent_id smallint, caption text, seq smallint, info_id int)
LANGUAGE sql STABLE AS $$
  WITH user_authorized_nodes AS (
    SELECT rn."NodeId", n."NodePath"
    FROM portal."Role2Node" rn
    JOIN portal."NavTree" n ON n."ID" = rn."NodeId"
    JOIN portal."viewUserAllRoles" u ON u."RoleId" = rn."RoleId" AND u."UserId" = p_user_id
    WHERE rn."RoleId" = p_role_id
      AND (p_scope_id IS NULL OR rn."ScopeId" = p_scope_id)
  ),
  visible_tree AS (
    SELECT n."ID", n."ParentID", n."Caption", n."Seq", n."InfoID", n."SortPath"
    FROM portal."NavTree" n
    WHERE EXISTS (
      SELECT 1 FROM user_authorized_nodes uan
      WHERE uan."NodeId" = n."ID" OR uan."NodePath" LIKE n."NodePath" || '/%'
    )
  )
  SELECT
    vt."ID"::smallint, vt."ParentID"::smallint,
    vt."Caption"::text, vt."Seq"::smallint, vt."InfoID"
  FROM visible_tree vt
  ORDER BY vt."SortPath", vt."ID";
$$;
