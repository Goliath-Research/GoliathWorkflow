/*
  PostgreSQL parity for Onboarding.sp* procedures extracted from
  workflow_engine/sql_mssql/onboarding_api.sql.

  Depends on:
    onboarding_schema.sql  – "Onboarding"."Invitations", "Onboarding"."AuditLog",
                              "Onboarding"."ApprovalQueue", "Onboarding"."InvitationBatches"
    rbac_schema.sql        – "RBAC"."Users", "RBAC"."ExternalIdentities",
                              "RBAC"."IdentityProviders", "RBAC"."ScopeIdentityProviders",
                              "RBAC"."UserRoleGrants"
    contract_api_parity.sql – "Contract".spcontractvalidatescopeaccess,
                               "Contract".spcontractvalidaterolegrant
*/

-- ──────────────────────────────────────────────────────────────────────────────
-- onboarding.spacceptinvitation
-- Full port of Onboarding.spAcceptInvitation.
-- Returns: invitation_id, user_id, scope_id, provider_id, contract_id,
--          granted_role_id, grant_type, role_grant_applied
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION "Onboarding".spacceptinvitation(
  p_invitation_id bigint,
  p_issuer text,
  p_subject text,
  p_email text,
  p_full_name text,
  p_utc_now timestamptz DEFAULT NULL
)
RETURNS TABLE(
  invitation_id bigint,
  user_id int,
  scope_id int,
  provider_id int,
  contract_id int,
  granted_role_id int,
  grant_type text,
  role_grant_applied boolean
)
LANGUAGE plpgsql AS $$
DECLARE
  v_now                  timestamptz := COALESCE(p_utc_now, now() AT TIME ZONE 'utc');
  v_normalized_email     text := lower(btrim(p_email));
  v_scope_id             int;
  v_inv_email            text;
  v_expected_provider_id int;
  v_expected_domain      text;
  v_default_role_id      int;
  v_grant_type           text;
  v_inv_status           text;
  v_expires_at_utc       timestamptz;
  v_contract_id          int;
  v_role_allowed         boolean;
  v_role_requires_approval boolean;
  v_role_reason          text;
  v_granted_role_id      int;
  v_granted_scope_id     int;
  v_user_id              int;
  v_existing_ei_user_id  int;
BEGIN
  IF p_invitation_id IS NULL OR p_invitation_id <= 0
     OR p_issuer IS NULL OR btrim(p_issuer) = ''
     OR p_subject IS NULL OR btrim(p_subject) = ''
     OR p_email IS NULL OR btrim(p_email) = ''
     OR p_full_name IS NULL OR btrim(p_full_name) = ''
  THEN
    RAISE EXCEPTION 'ValidationError: invitation_id, issuer, subject, email and full_name are required.';
  END IF;

  -- Lock the invitation row
  SELECT
    i."ScopeID",
    lower(btrim(i."Email")),
    i."ExpectedProviderID",
    i."ExpectedDomain",
    i."DefaultRoleID",
    i."GrantType",
    i."Status",
    i."ExpiresAtUtc"
  INTO v_scope_id, v_inv_email, v_expected_provider_id, v_expected_domain,
       v_default_role_id, v_grant_type, v_inv_status, v_expires_at_utc
  FROM "Onboarding"."Invitations" i
  WHERE i."InvitationID" = p_invitation_id
  FOR UPDATE;

  IF v_scope_id IS NULL THEN
    RAISE EXCEPTION 'BusinessRule: Invitation not found.';
  END IF;
  IF v_inv_status <> 'PENDING' THEN
    RAISE EXCEPTION 'BusinessRule: Invitation is not pending.';
  END IF;
  IF v_expires_at_utc < v_now THEN
    UPDATE "Onboarding"."Invitations"
    SET "Status" = 'EXPIRED'
    WHERE "InvitationID" = p_invitation_id AND "Status" = 'PENDING';
    RAISE EXCEPTION 'BusinessRule: Invitation has expired.';
  END IF;
  IF v_inv_email <> v_normalized_email THEN
    RAISE EXCEPTION 'BusinessRule: Invitation email does not match authenticated email.';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM "RBAC"."IdentityProviders" ip
    WHERE ip."ProviderID" = v_expected_provider_id AND ip."Active" = true AND ip."Issuer" = p_issuer
  ) THEN
    RAISE EXCEPTION 'BusinessRule: Invitation provider does not match authenticated issuer.';
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM "RBAC"."ScopeIdentityProviders" sip
    WHERE sip."ScopeID" = v_scope_id AND sip."ProviderID" = v_expected_provider_id AND sip."Active" = true
  ) THEN
    RAISE EXCEPTION 'BusinessRule: Scope is not active for invitation provider.';
  END IF;
  IF v_expected_domain IS NOT NULL AND right(v_normalized_email, length(v_expected_domain)+1) <> '@' || lower(v_expected_domain) THEN
    RAISE EXCEPTION 'BusinessRule: Authenticated email is outside expected domain.';
  END IF;

  -- Validate scope contract
  SELECT a.contract_id INTO v_contract_id
  FROM "Contract".spcontractvalidatescopeaccess(v_scope_id, v_now) a
  WHERE a.is_allowed;

  IF v_contract_id IS NULL THEN
    RAISE EXCEPTION 'BusinessRule: Scope has no active contract for invitation acceptance.';
  END IF;

  -- Upsert user
  SELECT u."ID" INTO v_user_id FROM "RBAC"."Users" u WHERE u."Email" = v_normalized_email FOR UPDATE;
  IF v_user_id IS NULL THEN
    INSERT INTO "RBAC"."Users" ("FullName", "Email", "Active")
    VALUES (p_full_name, v_normalized_email, true)
    RETURNING "ID" INTO v_user_id;
  ELSE
    UPDATE "RBAC"."Users"
    SET "FullName" = p_full_name, "Active" = true
    WHERE "ID" = v_user_id AND ("FullName" <> p_full_name OR "Active" = false);
  END IF;

  -- Upsert external identity
  SELECT ei."UserID" INTO v_existing_ei_user_id
  FROM "RBAC"."ExternalIdentities" ei
  WHERE ei."ProviderID" = v_expected_provider_id AND ei."Subject" = p_subject
  FOR UPDATE;

  IF v_existing_ei_user_id IS NOT NULL AND v_existing_ei_user_id <> v_user_id THEN
    RAISE EXCEPTION 'BusinessRule: External identity is already bound to a different user.';
  END IF;

  IF v_existing_ei_user_id IS NULL THEN
    INSERT INTO "RBAC"."ExternalIdentities"
      ("UserID","ProviderID","Subject","EmailSnapshot","Active","LastLoginAtUtc")
    VALUES (v_user_id, v_expected_provider_id, p_subject, v_normalized_email, true, v_now);
  ELSE
    UPDATE "RBAC"."ExternalIdentities"
    SET "UserID" = v_user_id, "EmailSnapshot" = v_normalized_email,
        "Active" = true, "LastLoginAtUtc" = v_now
    WHERE "ProviderID" = v_expected_provider_id AND "Subject" = p_subject;
  END IF;

  -- Role grant
  v_granted_role_id := NULL;
  IF v_default_role_id IS NOT NULL THEN
    SELECT a.is_allowed, a.reason_code
    INTO v_role_allowed, v_role_reason
    FROM "Contract".spcontractvalidaterolegrant(v_scope_id, v_default_role_id, v_now) a
    LIMIT 1;

    -- RequiresApproval not exposed in PG contract API; treat NOT allowed as rejection.
    IF NOT COALESCE(v_role_allowed, false) THEN
      RAISE EXCEPTION 'BusinessRule: Invitation role/grant is not allowed by contract (%).', v_role_reason;
    END IF;

    v_granted_scope_id := CASE WHEN v_grant_type = 'SCOPED' THEN v_scope_id ELSE NULL END;

    INSERT INTO "RBAC"."UserRoleGrants" ("UserID","RoleID","GrantType","ScopeID","Active")
    VALUES (v_user_id, v_default_role_id, v_grant_type, v_granted_scope_id, true)
    ON CONFLICT DO NOTHING;

    v_granted_role_id := v_default_role_id;
  END IF;

  -- Accept invitation
  UPDATE "Onboarding"."Invitations"
  SET "Status" = 'ACCEPTED', "AcceptedByUserID" = v_user_id, "AcceptedAtUtc" = v_now
  WHERE "InvitationID" = p_invitation_id;

  -- Audit
  INSERT INTO "Onboarding"."AuditLog"
    ("ScopeID","InvitationID","ActorUserID","EventType","EventDataJson")
  VALUES (
    v_scope_id, p_invitation_id, v_user_id, 'INVITATION_ACCEPTED',
    jsonb_build_object(
      'ContractID', v_contract_id,
      'ProviderID', v_expected_provider_id,
      'GrantedRoleID', v_granted_role_id,
      'GrantType', v_grant_type,
      'RolePolicyReasonCode', COALESCE(v_role_reason, 'OK')
    )
  );

  RETURN QUERY
  SELECT
    p_invitation_id, v_user_id, v_scope_id, v_expected_provider_id,
    v_contract_id, v_granted_role_id, v_grant_type,
    (v_granted_role_id IS NOT NULL) AS role_grant_applied;
END;
$$;
