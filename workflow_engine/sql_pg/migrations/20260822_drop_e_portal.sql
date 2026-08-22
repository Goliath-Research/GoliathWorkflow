-- Drop leftover uniGUI schema after copying role mappings.
-- Azure SQL already has no e_portal. Not in deploy_azure.sh (idempotent leftover cleanup).
-- Must copy e_portal.UserRoles → portal.UserRoles *before* DROP SCHEMA … CASCADE,
-- otherwise RBAC.spGetUserNavTree sees an empty view on upgrade.

CREATE TABLE IF NOT EXISTS portal."UserRoles" (
  "UserId" bigint NOT NULL,
  "RoleId" integer NOT NULL,
  CONSTRAINT "PK_portal_UserRoles" PRIMARY KEY ("UserId", "RoleId")
);

DO $migrate$
BEGIN
  IF to_regclass('e_portal."UserRoles"') IS NOT NULL THEN
    EXECUTE $ins$
      INSERT INTO portal."UserRoles" ("UserId", "RoleId")
      SELECT ur."UserId", ur."RoleId"
      FROM e_portal."UserRoles" ur
      ON CONFLICT ("UserId", "RoleId") DO NOTHING
    $ins$;
  END IF;
END
$migrate$;

CREATE OR REPLACE VIEW portal."viewUserAllRoles" AS
SELECT ur."UserId" AS "UserId", ur."RoleId" AS "RoleId"
FROM portal."UserRoles" ur;

DROP SCHEMA IF EXISTS e_portal CASCADE;
