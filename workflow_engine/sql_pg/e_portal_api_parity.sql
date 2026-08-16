/*
  PostgreSQL parity for e_portal.sp* procedures extracted from
  workflow_engine/sql_mssql/e_portal_api.sql.

  Depends on:
    e_portal_schema.sql  – e_portal."NavTree", e_portal."AppRole2Node",
                            e_portal."AppRole2Roles", e_portal."Roles",
                            e_portal."UserRoles", e_portal."SyUsers",
                            e_portal."EPSessions"
    portal_clinical_schema.sql – portal."Samples", portal."Patients"
*/

-- ──────────────────────────────────────────────────────────────────────────────
-- e_portal.spSessionSetUserId
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION e_portal.spsessionsetuserid(
  p_uni_session_id text,
  p_user_id bigint
)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE v_max_start timestamptz;
BEGIN
  SELECT MAX(ep."StartDate") INTO v_max_start
  FROM e_portal."EPSessions" ep WHERE ep."SqlSessionId" = pg_backend_pid();

  UPDATE e_portal."EPSessions"
  SET "UserId" = p_user_id
  WHERE "UniSessionId" = p_uni_session_id AND "StartDate" = v_max_start;
END;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- e_portal.spRoleGrant  (recursive grant to self + ancestors)
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION e_portal.sprolegrant(
  p_node_id int,
  p_app_role_id smallint
)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
  v_id     int := p_node_id;
  v_child  int;
  v_count  int;
BEGIN
  -- Grant up the ancestry chain
  WHILE v_id IS NOT NULL AND v_id >= 0 LOOP
    INSERT INTO e_portal."AppRole2Node" ("AppRoleId", "NodeId")
    VALUES (p_app_role_id, v_id)
    ON CONFLICT DO NOTHING;

    SELECT "ParentID" INTO v_id FROM e_portal."NavTree" WHERE "ID" = v_id;
  END LOOP;

  -- Grant to children recursively
  v_id := -1;
  SELECT COUNT(*) INTO v_count FROM e_portal."NavTree" WHERE "ParentID" = p_node_id;
  WHILE v_count > 0 LOOP
    SELECT MIN("ID") INTO v_child FROM e_portal."NavTree"
    WHERE "ParentID" = p_node_id AND "ID" > v_id;
    PERFORM e_portal.sprolegrant(v_child, p_app_role_id);
    v_count := v_count - 1;
    v_id := v_child;
  END LOOP;
END;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- e_portal.spRoleDeny  (recursive deny to self + children)
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION e_portal.sproledeny(
  p_node_id int,
  p_app_role_id smallint
)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
  v_id    int := -1;
  v_count int;
  v_child int;
BEGIN
  DELETE FROM e_portal."AppRole2Node"
  WHERE "AppRoleId" = p_app_role_id AND "NodeId" = p_node_id;

  SELECT COUNT(*) INTO v_count FROM e_portal."NavTree" WHERE "ParentID" = p_node_id;
  WHILE v_count > 0 LOOP
    SELECT MIN("ID") INTO v_child FROM e_portal."NavTree"
    WHERE "ParentID" = p_node_id AND "ID" > v_id;
    PERFORM e_portal.sproledeny(v_child, p_app_role_id);
    v_count := v_count - 1;
    v_id := v_child;
  END LOOP;
END;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- e_portal.spRemoveUserRole
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION e_portal.spremoveuserrole(
  p_user_id bigint,
  p_role_id bigint
)
RETURNS void LANGUAGE sql AS $$
  DELETE FROM e_portal."UserRoles"
  WHERE "UserId" = p_user_id AND "RoleId" = p_role_id;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- e_portal.spNodeSetName
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION e_portal.spnodesetname(
  p_id int,
  p_name text
)
RETURNS void LANGUAGE sql AS $$
  UPDATE e_portal."NavTree" SET "Caption" = p_name WHERE "ID" = p_id;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- e_portal.spNodeNewChild
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION e_portal.spnodenewchild(
  p_parent_id int
)
RETURNS TABLE(new_id int)
LANGUAGE plpgsql AS $$
DECLARE
  v_children int;
  v_id       int;
BEGIN
  SELECT COUNT(*) INTO v_children FROM e_portal."NavTree" WHERE "ParentID" = p_parent_id;
  INSERT INTO e_portal."NavTree" ("ParentID", "Caption", "Seq")
  VALUES (p_parent_id, 'New Node', v_children + 1)
  RETURNING "ID" INTO v_id;
  RETURN QUERY SELECT v_id;
END;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- e_portal.spNodeMove  (swap Seq between two sibling nodes)
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION e_portal.spnodemove(
  p_src_id int,
  p_dst_id int
)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
  v_src_seq int;
  v_dst_seq int;
BEGIN
  SELECT "Seq" INTO v_src_seq FROM e_portal."NavTree" WHERE "ID" = p_src_id;
  SELECT "Seq" INTO v_dst_seq FROM e_portal."NavTree" WHERE "ID" = p_dst_id;
  UPDATE e_portal."NavTree" SET "Seq" = v_dst_seq WHERE "ID" = p_src_id;
  UPDATE e_portal."NavTree" SET "Seq" = v_src_seq WHERE "ID" = p_dst_id;
END;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- e_portal.spNodeDelete
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION e_portal.spnodedelete(
  p_id int
)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
  v_parent_id int;
  v_seq       int;
BEGIN
  SELECT "ParentID", "Seq" INTO v_parent_id, v_seq FROM e_portal."NavTree" WHERE "ID" = p_id;
  DELETE FROM e_portal."NavTree" WHERE "ID" = p_id;
  UPDATE e_portal."NavTree"
  SET "Seq" = "Seq" - 1
  WHERE "ParentID" = v_parent_id AND "Seq" > v_seq;
END;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- e_portal.spNodeCutPaste
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION e_portal.spnodecutpaste(
  p_src_id int,
  p_dst_id int
)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
  v_src_parent int;
  v_old_seq    int;
  v_new_seq    int;
BEGIN
  SELECT "ParentID", "Seq" INTO v_src_parent, v_old_seq FROM e_portal."NavTree" WHERE "ID" = p_src_id;
  SELECT COALESCE(MAX("Seq"), 0) + 1 INTO v_new_seq FROM e_portal."NavTree" WHERE "ParentID" = p_dst_id;

  UPDATE e_portal."NavTree"
  SET "ParentID" = p_dst_id, "Seq" = v_new_seq
  WHERE "ID" = p_src_id;

  UPDATE e_portal."NavTree"
  SET "Seq" = "Seq" - 1
  WHERE "ParentID" = v_src_parent AND "Seq" > v_old_seq;
END;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- e_portal.spGetNavTree  (full subtree from a root)
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION e_portal.spgetnavtree(p_root_id smallint)
RETURNS TABLE(id smallint, parent_id smallint, caption text, seq smallint, form_id int)
LANGUAGE sql STABLE AS $$
  WITH RECURSIVE tree AS (
    SELECT "ID", "ParentID", "Caption", "Seq", "InfoID"
    FROM e_portal."NavTree" WHERE "ID" = p_root_id
    UNION ALL
    SELECT n."ID", n."ParentID", n."Caption", n."Seq", n."InfoID"
    FROM e_portal."NavTree" n JOIN tree t ON n."ParentID" = t."ID"
  )
  SELECT "ID"::smallint, "ParentID"::smallint, "Caption"::text, "Seq"::smallint, "InfoID"
  FROM tree ORDER BY "ID";
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- e_portal.spGetUserNavTree  (nodes authorised for user + role)
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION e_portal.spgetusernavtree(
  p_user_id bigint,
  p_app_role_id smallint
)
RETURNS TABLE(id smallint, parent_id smallint, caption text, seq smallint, info_id int)
LANGUAGE sql STABLE AS $$
  WITH RECURSIVE full_tree AS (
    SELECT "ID", "ParentID", "Caption", "Seq", "InfoID"
    FROM e_portal."NavTree" WHERE "ID" = 1
    UNION ALL
    SELECT n."ID", n."ParentID", n."Caption", n."Seq", n."InfoID"
    FROM e_portal."NavTree" n JOIN full_tree ft ON n."ParentID" = ft."ID"
  ),
  user_authorized AS (
    SELECT r."NodeId"
    FROM e_portal."AppRole2Node" r
    JOIN "e_portal"."viewUserAllRoles" u ON r."AppRoleId" = u."RoleId" AND u."UserId" = p_user_id
    WHERE r."AppRoleId" = p_app_role_id
  )
  SELECT t."ID"::smallint, t."ParentID"::smallint, t."Caption"::text, t."Seq"::smallint, t."InfoID"
  FROM full_tree t
  WHERE t."ID" IN (SELECT "NodeId" FROM user_authorized)
  ORDER BY t."ID";
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- e_portal.spGetUserRoles
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION e_portal.spgetuserroles(p_user_id bigint)
RETURNS TABLE(user_id bigint, role_id bigint, role text, included boolean)
LANGUAGE sql STABLE AS $$
  WITH permissions AS (
    SELECT p_user_id AS uid, r."RoleId", r."Name" AS role, false AS included
    FROM e_portal."Roles" r
    UNION
    SELECT ur."UserId", r."RoleId", r."Name", true
    FROM e_portal."UserRoles" ur
    JOIN e_portal."Roles" r ON ur."RoleId" = r."RoleId"
    WHERE ur."UserId" = p_user_id
  )
  SELECT uid, "RoleId", role, BOOL_OR(included)
  FROM permissions
  GROUP BY uid, "RoleId", role;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- e_portal.spGetUserIdByEmail
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION e_portal.spgetuseridbyemail(p_email text)
RETURNS TABLE(user_id bigint)
LANGUAGE sql STABLE AS $$
  SELECT "UserId" FROM e_portal."SyUsers" WHERE "Email" = p_email;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- e_portal.spGetUserAppRoles
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION e_portal.spgetuserapproles(p_user_id bigint)
RETURNS TABLE(user_id bigint, role_id bigint, role text)
LANGUAGE sql STABLE AS $$
  SELECT su."UserId", r."RoleId", r."Name"::text AS role
  FROM e_portal."SyUsers" su
  JOIN e_portal."UserRoles" ur ON ur."UserId" = su."UserId"
  JOIN e_portal."Roles" r ON r."RoleId" = ur."RoleId"
  WHERE su."UserId" = p_user_id;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- e_portal.spGetSamplesByPatient
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION e_portal.spgetsamplesbypatient(p_id int)
RETURNS TABLE(id int, age numeric, height numeric, weight numeric)
LANGUAGE sql STABLE AS $$
  SELECT s."ID", s."Age", s."Height", s."Weight"
  FROM portal."Samples" s WHERE s."ID" = p_id;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- e_portal.spGetAllPatients
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION e_portal.spgetallpatients()
RETURNS TABLE(id int, name text, sex text)
LANGUAGE sql STABLE AS $$
  SELECT p."ID", p."Name"::text, p."Sex"::text
  FROM portal."Patients" p
  ORDER BY p."ID";
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- e_portal.spAddUserRole
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION e_portal.spadduserrole(
  p_user_id bigint,
  p_role_id bigint
)
RETURNS void LANGUAGE sql AS $$
  INSERT INTO e_portal."UserRoles" ("UserId", "RoleId")
  VALUES (p_user_id, p_role_id)
  ON CONFLICT DO NOTHING;
$$;
