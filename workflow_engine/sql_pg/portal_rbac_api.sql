/*
  Portal RBAC admin façade (PostgreSQL).
  Twin of sql_mssql/portal_rbac_api.sql.

  EpiPortal Admin screens call portal.sp_* only — not "RBAC".* write functions.
  Quoted PascalCase tables from rbac_schema.sql / onboarding_schema.sql.
*/

CREATE OR REPLACE FUNCTION portal.sp_list_users(p_include_inactive boolean DEFAULT false)
RETURNS TABLE (
  user_id int,
  full_name text,
  email text,
  active int
)
LANGUAGE sql
STABLE
AS $$
  SELECT u."ID", u."FullName"::text, u.email::text, u."Active"
  FROM "RBAC"."Users" u
  WHERE p_include_inactive OR u."Active" = 1
  ORDER BY u."FullName", u.email;
$$;

CREATE OR REPLACE FUNCTION portal.sp_get_user(p_user_id int)
RETURNS TABLE (
  user_id int,
  full_name text,
  email text,
  active int
)
LANGUAGE sql
STABLE
AS $$
  SELECT u."ID", u."FullName"::text, u.email::text, u."Active"
  FROM "RBAC"."Users" u
  WHERE u."ID" = p_user_id;
$$;

CREATE OR REPLACE FUNCTION portal.sp_upsert_user(
  p_email text,
  p_full_name text,
  p_active int DEFAULT 1,
  OUT user_id int
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_email varchar(50);
BEGIN
  v_email := lower(btrim(p_email));
  IF v_email IS NULL OR v_email = '' THEN
    RAISE EXCEPTION 'email is required';
  END IF;
  IF p_full_name IS NULL OR btrim(p_full_name) = '' THEN
    RAISE EXCEPTION 'full_name is required';
  END IF;

  SELECT u."ID" INTO user_id FROM "RBAC"."Users" u WHERE u.email = v_email;
  IF user_id IS NULL THEN
    INSERT INTO "RBAC"."Users" ("FullName", email, "Active")
    VALUES (p_full_name, v_email, COALESCE(p_active, 1))
    RETURNING "ID" INTO user_id;
  ELSE
    UPDATE "RBAC"."Users"
    SET "FullName" = p_full_name,
        "Active" = COALESCE(p_active, "Active")
    WHERE "ID" = user_id;
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_list_user_identities(p_user_id int)
RETURNS TABLE (
  identity_id int,
  provider_id int,
  provider_name text,
  subject text,
  email_snapshot text,
  active boolean,
  last_login_at_utc timestamptz
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    ei."ID",
    ei."ProviderID",
    p."Name"::text,
    ei."Subject"::text,
    ei."EmailSnapshot"::text,
    ei."Active",
    ei."LastLoginAtUtc"
  FROM "RBAC"."ExternalIdentities" ei
  INNER JOIN "RBAC"."IdentityProviders" p ON p."ProviderID" = ei."ProviderID"
  WHERE ei."UserID" = p_user_id
  ORDER BY ei."ID";
$$;

CREATE OR REPLACE FUNCTION portal.sp_list_roles()
RETURNS TABLE (
  role_id int,
  name text,
  bypass_scope boolean
)
LANGUAGE sql
STABLE
AS $$
  SELECT r."ID", r."Name"::text, r."BypassScope"
  FROM "RBAC"."Roles" r
  ORDER BY r."Name";
$$;

CREATE OR REPLACE FUNCTION portal.sp_list_permissions(p_role_id int DEFAULT NULL)
RETURNS TABLE (
  permission_id int,
  name text,
  obj_id int,
  operation_id int,
  role_id int
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    p."ID",
    p."Name"::text,
    p."ObjID",
    p."OperationID",
    rp."RoleID"
  FROM "RBAC"."Permissions" p
  LEFT JOIN "RBAC"."Role_Permissions" rp
    ON rp."PermissionID" = p."ID" AND (p_role_id IS NULL OR rp."RoleID" = p_role_id)
  WHERE p_role_id IS NULL OR rp."RoleID" = p_role_id
  ORDER BY p."Name";
$$;

CREATE OR REPLACE FUNCTION portal.sp_list_scopes(p_include_inactive boolean DEFAULT false)
RETURNS TABLE (
  scope_id int,
  scope_type text,
  name text,
  institution_id int,
  lab_id int,
  owner_user_id int,
  active boolean
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    s."ScopeID",
    s."ScopeType"::text,
    s."Name"::text,
    s."InstitutionID",
    s."LabID",
    s."OwnerUserID",
    s."Active"
  FROM "RBAC"."Scopes" s
  WHERE p_include_inactive OR s."Active"
  ORDER BY s."Name";
$$;

CREATE OR REPLACE FUNCTION portal.sp_get_scope(p_scope_id int)
RETURNS TABLE (
  scope_id int,
  scope_type text,
  name text,
  institution_id int,
  lab_id int,
  owner_user_id int,
  active boolean
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    s."ScopeID",
    s."ScopeType"::text,
    s."Name"::text,
    s."InstitutionID",
    s."LabID",
    s."OwnerUserID",
    s."Active"
  FROM "RBAC"."Scopes" s
  WHERE s."ScopeID" = p_scope_id;
$$;

CREATE OR REPLACE FUNCTION portal.sp_grant_user_role(
  p_user_id int,
  p_role_id int,
  p_grant_type text,
  p_scope_id int DEFAULT NULL,
  p_approval_id bigint DEFAULT NULL
)
RETURNS TABLE (inserted boolean, grant_id bigint)
LANGUAGE plpgsql
AS $$
DECLARE
  v_bypass boolean;
  v_grant varchar(16);
  v_id bigint;
BEGIN
  SELECT r."BypassScope" INTO v_bypass FROM "RBAC"."Roles" r WHERE r."ID" = p_role_id;
  IF v_bypass IS NULL THEN
    RAISE EXCEPTION 'role_id not found';
  END IF;

  v_grant := upper(btrim(p_grant_type));
  IF v_grant NOT IN ('SCOPED', 'GLOBAL') THEN
    RAISE EXCEPTION 'grant_type must be SCOPED or GLOBAL';
  END IF;
  IF v_bypass AND v_grant <> 'GLOBAL' THEN
    RAISE EXCEPTION 'BypassScope roles require GLOBAL grant type';
  END IF;
  IF v_bypass THEN
    IF p_approval_id IS NULL THEN
      RAISE EXCEPTION 'BypassScope GLOBAL grants require approval_id';
    END IF;
    IF NOT EXISTS (
      SELECT 1 FROM "RBAC"."BypassScopeApprovals" a
      WHERE a."ApprovalID" = p_approval_id
        AND a."UserID" = p_user_id
        AND a."RoleID" = p_role_id
        AND a."Status" = 'APPROVED'
    ) THEN
      RAISE EXCEPTION 'approval_id is not an APPROVED BypassScope approval for this user and role';
    END IF;
  END IF;

  IF v_grant = 'GLOBAL' THEN
    p_scope_id := NULL;
  END IF;
  IF v_grant = 'SCOPED' AND (p_scope_id IS NULL OR p_scope_id <= 0) THEN
    RAISE EXCEPTION 'scope_id is required for SCOPED grants';
  END IF;

  IF EXISTS (
    SELECT 1 FROM "RBAC"."UserRoleGrants" g
    WHERE g."UserID" = p_user_id AND g."RoleID" = p_role_id AND g."GrantType" = v_grant
      AND ((g."ScopeID" IS NULL AND p_scope_id IS NULL) OR g."ScopeID" = p_scope_id)
      AND g."Active"
  ) THEN
    RETURN QUERY SELECT false, NULL::bigint;
    RETURN;
  END IF;

  INSERT INTO "RBAC"."UserRoleGrants" (
    "UserID", "RoleID", "GrantType", "ScopeID", "Active", "GrantedAtUtc", "ApprovalID"
  )
  VALUES (
    p_user_id, p_role_id, v_grant, p_scope_id, true, now() AT TIME ZONE 'utc', p_approval_id
  )
  RETURNING "ID" INTO v_id;

  RETURN QUERY SELECT true, v_id;
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_list_user_role_grants(p_user_id int)
RETURNS TABLE (
  grant_id int,
  user_id int,
  role_id int,
  role_name text,
  grant_type text,
  scope_id int,
  scope_name text,
  active boolean,
  granted_at_utc timestamptz,
  revoked_at_utc timestamptz,
  approval_id bigint
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    g."ID",
    g."UserID",
    g."RoleID",
    r."Name"::text,
    g."GrantType"::text,
    g."ScopeID",
    s."Name"::text,
    g."Active",
    g."GrantedAtUtc",
    g."RevokedAtUtc",
    g."ApprovalID"
  FROM "RBAC"."UserRoleGrants" g
  INNER JOIN "RBAC"."Roles" r ON r."ID" = g."RoleID"
  LEFT JOIN "RBAC"."Scopes" s ON s."ScopeID" = g."ScopeID"
  WHERE g."UserID" = p_user_id
  ORDER BY g."Active" DESC, r."Name";
$$;

CREATE OR REPLACE FUNCTION portal.sp_revoke_user_role(
  p_user_id int,
  p_role_id int,
  p_grant_type text,
  p_scope_id int DEFAULT NULL
)
RETURNS TABLE (rows_updated bigint)
LANGUAGE plpgsql
AS $$
DECLARE
  v_grant varchar(16) := upper(btrim(p_grant_type));
  v_n bigint;
BEGIN
  UPDATE "RBAC"."UserRoleGrants"
  SET "Active" = false, "RevokedAtUtc" = now() AT TIME ZONE 'utc'
  WHERE "UserID" = p_user_id AND "RoleID" = p_role_id AND "GrantType" = v_grant
    AND "Active"
    AND (("ScopeID" IS NULL AND p_scope_id IS NULL) OR "ScopeID" = p_scope_id);
  GET DIAGNOSTICS v_n = ROW_COUNT;
  RETURN QUERY SELECT v_n;
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_list_user_groups()
RETURNS TABLE (group_id int, name text)
LANGUAGE sql
STABLE
AS $$
  SELECT g."ID", g."Name"::text
  FROM "RBAC"."Groups" g
  ORDER BY g."Name";
$$;

CREATE OR REPLACE FUNCTION portal.sp_set_user_group_members(
  p_group_id int,
  p_user_ids jsonb
)
RETURNS TABLE (members bigint)
LANGUAGE plpgsql
AS $$
DECLARE v_n bigint;
BEGIN
  DELETE FROM "RBAC"."Group_Users" WHERE "GroupID" = p_group_id;
  INSERT INTO "RBAC"."Group_Users" ("GroupID", "UserID", "AddedAt")
  SELECT DISTINCT p_group_id, (j.value)::int, now() AT TIME ZONE 'utc'
  FROM jsonb_array_elements_text(COALESCE(p_user_ids, '[]'::jsonb)) j
  WHERE (j.value)::int IS NOT NULL;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  RETURN QUERY SELECT v_n;
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_set_user_group_roles(
  p_group_id int,
  p_role_ids jsonb
)
RETURNS TABLE (roles bigint)
LANGUAGE plpgsql
AS $$
DECLARE v_n bigint;
BEGIN
  DELETE FROM "RBAC"."Group_Roles" WHERE "GroupID" = p_group_id;
  INSERT INTO "RBAC"."Group_Roles" ("GroupID", "RoleID")
  SELECT DISTINCT p_group_id, (j.value)::int
  FROM jsonb_array_elements_text(COALESCE(p_role_ids, '[]'::jsonb)) j
  WHERE (j.value)::int IS NOT NULL;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  RETURN QUERY SELECT v_n;
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_list_user_sessions(p_user_id int)
RETURNS TABLE (
  session_id int,
  name text,
  user_id int,
  created timestamptz,
  active_scope_id int,
  auth_provider_id int,
  authenticated_at_utc timestamptz
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    s."ID",
    s."Name"::text,
    s."UserID",
    s."Created",
    s."ActiveScopeID",
    s."AuthProviderID",
    s."AuthenticatedAtUtc"
  FROM "RBAC"."Sessions" s
  WHERE s."UserID" = p_user_id
  ORDER BY s."Created" DESC;
$$;

CREATE OR REPLACE FUNCTION portal.sp_list_role_nav_nodes(
  p_role_id int,
  p_scope_id int DEFAULT NULL
)
RETURNS TABLE (
  scope_id int,
  role_id int,
  node_id int,
  caption text,
  parent_id int
)
LANGUAGE sql
STABLE
AS $$
  SELECT rn."ScopeId", rn."RoleId", rn."NodeId", n."Caption"::text, n."ParentID"
  FROM portal."Role2Node" rn
  INNER JOIN portal."NavTree" n ON n."ID" = rn."NodeId"
  WHERE rn."RoleId" = p_role_id
    AND (p_scope_id IS NULL OR rn."ScopeId" = p_scope_id)
  ORDER BY n."Caption";
$$;

CREATE OR REPLACE FUNCTION portal.sp_grant_role_nav_node(
  p_role_id int,
  p_node_id int,
  p_scope_id int
)
RETURNS TABLE (ok boolean)
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO portal."Role2Node" ("RoleId", "NodeId", "ScopeId")
  VALUES (p_role_id, p_node_id, p_scope_id)
  ON CONFLICT ("ScopeId", "RoleId", "NodeId") DO NOTHING;
  RETURN QUERY SELECT true;
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_deny_role_nav_node(
  p_role_id int,
  p_node_id int,
  p_scope_id int
)
RETURNS TABLE (rows_deleted bigint)
LANGUAGE plpgsql
AS $$
DECLARE v_n bigint;
BEGIN
  DELETE FROM portal."Role2Node"
  WHERE "RoleId" = p_role_id AND "NodeId" = p_node_id AND "ScopeId" = p_scope_id;
  GET DIAGNOSTICS v_n = ROW_COUNT;
  RETURN QUERY SELECT v_n;
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_create_invitation_batch(
  p_scope_id int,
  p_created_by_user_id int
)
RETURNS TABLE (batch_id bigint)
LANGUAGE plpgsql
AS $$
DECLARE v_id bigint;
BEGIN
  INSERT INTO "Onboarding"."InvitationBatches" ("ScopeID", "CreatedByUserID", "Status", "CreatedAtUtc")
  VALUES (p_scope_id, p_created_by_user_id, 'OPEN', now() AT TIME ZONE 'utc')
  RETURNING "BatchID" INTO v_id;
  RETURN QUERY SELECT v_id;
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_create_invitation(
  p_scope_id int,
  p_email text,
  p_expected_provider_id int,
  p_expires_at_utc timestamptz,
  p_batch_id bigint DEFAULT NULL,
  p_default_role_id int DEFAULT NULL,
  p_grant_type text DEFAULT 'SCOPED',
  p_expected_domain text DEFAULT NULL
)
RETURNS TABLE (invitation_id bigint)
LANGUAGE plpgsql
AS $$
DECLARE
  v_id bigint;
  v_grant varchar(16) := upper(COALESCE(p_grant_type, 'SCOPED'));
BEGIN
  INSERT INTO "Onboarding"."Invitations" (
    "BatchID", "ScopeID", "Email", "ExpectedProviderID", "ExpectedDomain",
    "DefaultRoleID", "GrantType", "ExpiresAtUtc", "Status", "CreatedAtUtc"
  )
  VALUES (
    p_batch_id, p_scope_id, lower(btrim(p_email)), p_expected_provider_id,
    p_expected_domain, p_default_role_id, v_grant, p_expires_at_utc, 'PENDING',
    now() AT TIME ZONE 'utc'
  )
  RETURNING "InvitationID" INTO v_id;
  RETURN QUERY SELECT v_id;
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_list_invitations(
  p_scope_id int DEFAULT NULL,
  p_status text DEFAULT NULL
)
RETURNS TABLE (
  invitation_id bigint,
  batch_id bigint,
  scope_id int,
  email text,
  default_role_id int,
  grant_type text,
  status text,
  expires_at_utc timestamptz,
  accepted_by_user_id int,
  accepted_at_utc timestamptz,
  created_at_utc timestamptz
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    i."InvitationID",
    i."BatchID",
    i."ScopeID",
    i."Email"::text,
    i."DefaultRoleID",
    i."GrantType"::text,
    i."Status"::text,
    i."ExpiresAtUtc",
    i."AcceptedByUserID",
    i."AcceptedAtUtc",
    i."CreatedAtUtc"
  FROM "Onboarding"."Invitations" i
  WHERE (p_scope_id IS NULL OR i."ScopeID" = p_scope_id)
    AND (p_status IS NULL OR i."Status" = p_status)
  ORDER BY i."CreatedAtUtc" DESC;
$$;

CREATE OR REPLACE FUNCTION portal.sp_revoke_invitation(p_invitation_id bigint)
RETURNS TABLE (rows_updated bigint)
LANGUAGE plpgsql
AS $$
DECLARE v_n bigint;
BEGIN
  UPDATE "Onboarding"."Invitations"
  SET "Status" = 'REVOKED'
  WHERE "InvitationID" = p_invitation_id AND "Status" = 'PENDING';
  GET DIAGNOSTICS v_n = ROW_COUNT;
  RETURN QUERY SELECT v_n;
END;
$$;
