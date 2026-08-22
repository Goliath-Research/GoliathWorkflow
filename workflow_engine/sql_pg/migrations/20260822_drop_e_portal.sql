-- Drop leftover uniGUI schema. Azure SQL no longer has e_portal.
-- portal.UserRoles + portal.viewUserAllRoles replace e_portal.viewUserAllRoles
-- for RBAC.spGetUserNavTree. Not in deploy_azure.sh (idempotent leftover cleanup).

CREATE TABLE IF NOT EXISTS portal."UserRoles" (
  "UserId" bigint NOT NULL,
  "RoleId" integer NOT NULL,
  CONSTRAINT "PK_portal_UserRoles" PRIMARY KEY ("UserId", "RoleId")
);

CREATE OR REPLACE VIEW portal."viewUserAllRoles" AS
SELECT ur."UserId" AS "UserId", ur."RoleId" AS "RoleId"
FROM portal."UserRoles" ur;

DROP SCHEMA IF EXISTS e_portal CASCADE;
