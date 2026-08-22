/*
  Contract process-pack entitlements + portal.sp_* admin façade (PostgreSQL).
  Twin of sql_mssql/portal_contract_api.sql.
*/

CREATE TABLE IF NOT EXISTS "Contract"."ContractProcessPackEntitlements" (
  "ContractID" integer NOT NULL,
  "Modality" varchar(32) NOT NULL,
  "Enabled" boolean NOT NULL DEFAULT true,
  "EffectiveFromUtc" timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  "EffectiveToUtc" timestamptz NULL,
  "CreatedAtUtc" timestamptz NOT NULL DEFAULT (now() AT TIME ZONE 'utc'),
  CONSTRAINT "PK_Contract_ProcessPackEntitlements" PRIMARY KEY ("ContractID", "Modality"),
  CONSTRAINT "CK_CPPE_Modality" CHECK (
    "Modality" IN ('methylation', 'rnaseq', 'proteomics')
  ),
  CONSTRAINT "CK_CPPE_Range" CHECK (
    "EffectiveToUtc" IS NULL OR "EffectiveToUtc" >= "EffectiveFromUtc"
  )
);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'FK_CPPE_ContractID'
  ) THEN
    ALTER TABLE "Contract"."ContractProcessPackEntitlements"
      ADD CONSTRAINT "FK_CPPE_ContractID"
      FOREIGN KEY ("ContractID") REFERENCES "Contract"."Contracts" ("ContractID");
  END IF;
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'CK_CPPE_Range'
  ) THEN
    ALTER TABLE "Contract"."ContractProcessPackEntitlements"
      ADD CONSTRAINT "CK_CPPE_Range" CHECK (
        "EffectiveToUtc" IS NULL OR "EffectiveToUtc" >= "EffectiveFromUtc"
      );
  END IF;
END $$;

CREATE OR REPLACE FUNCTION portal.fn_infer_process_pack(
  p_name text,
  p_document jsonb DEFAULT NULL
)
RETURNS varchar(32)
LANGUAGE plpgsql
IMMUTABLE
AS $$
DECLARE
  v_mod text;
  v_n text;
BEGIN
  v_mod := lower(btrim(COALESCE(p_document #>> '{regulatory,primary_modality}', '')));
  IF v_mod IN ('methylation', 'rnaseq', 'proteomics') THEN
    RETURN v_mod;
  END IF;
  v_mod := lower(btrim(COALESCE(p_document #>> '{catalog,family}', '')));
  IF v_mod IN ('methylation', 'rnaseq', 'proteomics') THEN
    RETURN v_mod;
  END IF;
  v_n := lower(COALESCE(p_name, ''));
  IF v_n LIKE '%rnaseq%'
     OR v_n LIKE 'rna-%'
     OR v_n LIKE 'rna\_%' ESCAPE '\'
     OR v_n LIKE '%rna.seq%' THEN
    RETURN 'rnaseq';
  END IF;
  IF v_n LIKE '%proteom%' THEN
    RETURN 'proteomics';
  END IF;
  RETURN 'methylation';
END;
$$;

CREATE OR REPLACE FUNCTION portal.fn_infer_process_pack_from_context(p_context jsonb)
RETURNS varchar(32)
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT CASE
    WHEN lower(btrim(COALESCE(p_context #>> '{regulatory,primary_modality}', '')))
         IN ('methylation', 'rnaseq', 'proteomics')
      THEN lower(btrim(p_context #>> '{regulatory,primary_modality}'))
    ELSE portal.fn_infer_process_pack(
      COALESCE(p_context->>'pipelineProfile', p_context->>'pipelineProcedure'),
      NULL
    )
  END;
$$;

CREATE OR REPLACE FUNCTION portal.fn_contract_entitled_modalities(p_scope_id int)
RETURNS TABLE (modality varchar(32))
LANGUAGE sql
STABLE
AS $$
  SELECT DISTINCT e."Modality"
  FROM "Contract"."ContractProcessPackEntitlements" e
  INNER JOIN "Contract"."ContractScopes" cs ON cs."ContractID" = e."ContractID"
  INNER JOIN "Contract"."Contracts" c ON c."ContractID" = cs."ContractID"
  WHERE p_scope_id IS NOT NULL
    AND cs."ScopeID" = p_scope_id
    AND cs."Status" = 'ACTIVE'
    AND c."Status" = 'ACTIVE'
    AND e."Enabled"
    AND cs."EffectiveFromUtc" <= (now() AT TIME ZONE 'utc')
    AND (cs."EffectiveToUtc" IS NULL OR cs."EffectiveToUtc" >= (now() AT TIME ZONE 'utc'))
    AND c."StartDateUtc" <= (now() AT TIME ZONE 'utc')
    AND (c."EndDateUtc" IS NULL OR c."EndDateUtc" >= (now() AT TIME ZONE 'utc'))
    AND e."EffectiveFromUtc" <= (now() AT TIME ZONE 'utc')
    AND (e."EffectiveToUtc" IS NULL OR e."EffectiveToUtc" >= (now() AT TIME ZONE 'utc'));
$$;

CREATE OR REPLACE FUNCTION portal.sp_contract_entitled_modalities(p_scope_id int)
RETURNS TABLE (modality varchar(32))
LANGUAGE sql
STABLE
AS $$
  SELECT m.modality FROM portal.fn_contract_entitled_modalities(p_scope_id) m ORDER BY 1;
$$;

CREATE OR REPLACE FUNCTION portal.sp_list_contracts(p_include_inactive boolean DEFAULT false)
RETURNS TABLE (
  contract_id int,
  customer_id int,
  customer_name text,
  name text,
  status text,
  start_date_utc timestamptz,
  end_date_utc timestamptz,
  plan_code text,
  billing_cycle text,
  auto_renew boolean,
  terms_version text,
  created_at_utc timestamptz,
  updated_at_utc timestamptz
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    c."ContractID",
    c."CustomerID",
    cu."Name"::text,
    c."Name"::text,
    c."Status"::text,
    c."StartDateUtc",
    c."EndDateUtc",
    c."PlanCode"::text,
    c."BillingCycle"::text,
    c."AutoRenew",
    c."TermsVersion"::text,
    c."CreatedAtUtc",
    c."UpdatedAtUtc"
  FROM "Contract"."Contracts" c
  INNER JOIN portal."Customers" cu ON cu."ID" = c."CustomerID"
  WHERE p_include_inactive OR c."Status" IN ('DRAFT', 'ACTIVE')
  ORDER BY c."Name";
$$;

CREATE OR REPLACE FUNCTION portal.sp_get_contract(p_contract_id int)
RETURNS TABLE (
  contract_id int,
  customer_id int,
  customer_name text,
  name text,
  status text,
  start_date_utc timestamptz,
  end_date_utc timestamptz,
  plan_code text,
  billing_cycle text,
  auto_renew boolean,
  terms_version text,
  created_at_utc timestamptz,
  updated_at_utc timestamptz
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    c."ContractID",
    c."CustomerID",
    cu."Name"::text,
    c."Name"::text,
    c."Status"::text,
    c."StartDateUtc",
    c."EndDateUtc",
    c."PlanCode"::text,
    c."BillingCycle"::text,
    c."AutoRenew",
    c."TermsVersion"::text,
    c."CreatedAtUtc",
    c."UpdatedAtUtc"
  FROM "Contract"."Contracts" c
  INNER JOIN portal."Customers" cu ON cu."ID" = c."CustomerID"
  WHERE c."ContractID" = p_contract_id;
$$;

CREATE OR REPLACE FUNCTION portal.sp_upsert_contract(
  p_customer_id int,
  p_name text,
  p_status text DEFAULT 'DRAFT',
  p_start_date_utc timestamptz DEFAULT NULL,
  p_end_date_utc timestamptz DEFAULT NULL,
  p_plan_code text DEFAULT NULL,
  p_billing_cycle text DEFAULT NULL,
  p_auto_renew boolean DEFAULT false,
  p_terms_version text DEFAULT NULL,
  OUT contract_id int
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_status varchar(24);
  v_start timestamptz;
BEGIN
  IF p_customer_id IS NULL OR p_customer_id <= 0 THEN
    RAISE EXCEPTION 'customer_id is required';
  END IF;
  IF p_name IS NULL OR btrim(p_name) = '' THEN
    RAISE EXCEPTION 'name is required';
  END IF;
  v_status := upper(btrim(COALESCE(p_status, 'DRAFT')));
  IF v_status NOT IN ('DRAFT', 'ACTIVE', 'SUSPENDED', 'EXPIRED', 'TERMINATED') THEN
    RAISE EXCEPTION 'Invalid contract status';
  END IF;
  v_start := COALESCE(p_start_date_utc, now() AT TIME ZONE 'utc');

  SELECT c."ContractID" INTO contract_id
  FROM "Contract"."Contracts" c
  WHERE c."CustomerID" = p_customer_id;

  IF contract_id IS NULL THEN
    INSERT INTO "Contract"."Contracts" (
      "CustomerID", "Name", "Status", "StartDateUtc", "EndDateUtc",
      "PlanCode", "BillingCycle", "AutoRenew", "TermsVersion",
      "CreatedAtUtc", "UpdatedAtUtc"
    )
    VALUES (
      p_customer_id, p_name, v_status, v_start, p_end_date_utc,
      p_plan_code, p_billing_cycle, COALESCE(p_auto_renew, false), p_terms_version,
      now() AT TIME ZONE 'utc', now() AT TIME ZONE 'utc'
    )
    RETURNING "ContractID" INTO contract_id;
  ELSE
    UPDATE "Contract"."Contracts"
    SET "Name" = p_name,
        "Status" = v_status,
        "StartDateUtc" = v_start,
        "EndDateUtc" = p_end_date_utc,
        "PlanCode" = p_plan_code,
        "BillingCycle" = p_billing_cycle,
        "AutoRenew" = COALESCE(p_auto_renew, "AutoRenew"),
        "TermsVersion" = p_terms_version,
        "UpdatedAtUtc" = now() AT TIME ZONE 'utc'
    WHERE "ContractID" = contract_id;
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_list_contract_process_packs(p_contract_id int)
RETURNS TABLE (
  contract_id int,
  modality text,
  enabled boolean,
  effective_from_utc timestamptz,
  effective_to_utc timestamptz
)
LANGUAGE sql
STABLE
AS $$
  SELECT e."ContractID", e."Modality"::text, e."Enabled", e."EffectiveFromUtc", e."EffectiveToUtc"
  FROM "Contract"."ContractProcessPackEntitlements" e
  WHERE e."ContractID" = p_contract_id
  ORDER BY e."Modality";
$$;

CREATE OR REPLACE FUNCTION portal.sp_set_contract_process_packs(
  p_contract_id int,
  p_modalities jsonb
)
RETURNS TABLE (packs bigint)
LANGUAGE plpgsql
AS $$
DECLARE v_n bigint;
BEGIN
  IF NOT EXISTS (SELECT 1 FROM "Contract"."Contracts" c WHERE c."ContractID" = p_contract_id) THEN
    RAISE EXCEPTION 'contract_id not found';
  END IF;

  DELETE FROM "Contract"."ContractProcessPackEntitlements" WHERE "ContractID" = p_contract_id;

  INSERT INTO "Contract"."ContractProcessPackEntitlements" ("ContractID", "Modality", "Enabled")
  SELECT DISTINCT p_contract_id, lower(btrim(j.value)), true
  FROM jsonb_array_elements_text(COALESCE(p_modalities, '[]'::jsonb)) j
  WHERE lower(btrim(j.value)) IN ('methylation', 'rnaseq', 'proteomics');

  GET DIAGNOSTICS v_n = ROW_COUNT;
  RETURN QUERY SELECT v_n;
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_list_contract_scopes(p_contract_id int)
RETURNS TABLE (
  contract_id int,
  scope_id int,
  scope_name text,
  scope_type text,
  status text,
  activated_at_utc timestamptz,
  effective_from_utc timestamptz,
  effective_to_utc timestamptz
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    cs."ContractID",
    cs."ScopeID",
    s."Name"::text,
    s."ScopeType"::text,
    cs."Status"::text,
    cs."ActivatedAtUtc",
    cs."EffectiveFromUtc",
    cs."EffectiveToUtc"
  FROM "Contract"."ContractScopes" cs
  INNER JOIN "RBAC"."Scopes" s ON s."ScopeID" = cs."ScopeID"
  WHERE cs."ContractID" = p_contract_id
  ORDER BY s."Name";
$$;

CREATE OR REPLACE FUNCTION portal.sp_list_contract_limits(p_contract_id int)
RETURNS TABLE (
  contract_limit_id bigint,
  contract_id int,
  scope_id int,
  max_active_users int,
  max_storage_gb numeric,
  max_runs_per_month int,
  created_at_utc timestamptz
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    l."ContractLimitID",
    l."ContractID",
    l."ScopeID",
    l."MaxActiveUsers",
    l."MaxStorageGB",
    l."MaxRunsPerMonth",
    l."CreatedAtUtc"
  FROM "Contract"."ContractLimits" l
  WHERE l."ContractID" = p_contract_id
  ORDER BY l."ScopeID";
$$;

CREATE OR REPLACE FUNCTION portal.sp_list_contract_role_policies(p_contract_id int)
RETURNS TABLE (
  contract_id int,
  role_id int,
  role_name text,
  grant_type_allowed text,
  max_users_for_role int,
  requires_approval boolean,
  created_at_utc timestamptz
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    p."ContractID",
    p."RoleID",
    r."Name"::text,
    p."GrantTypeAllowed"::text,
    p."MaxUsersForRole",
    p."RequiresApproval",
    p."CreatedAtUtc"
  FROM "Contract"."ContractRolePolicies" p
  INNER JOIN "RBAC"."Roles" r ON r."ID" = p."RoleID"
  WHERE p."ContractID" = p_contract_id
  ORDER BY r."Name";
$$;

CREATE OR REPLACE FUNCTION portal.sp_set_contract_scopes(
  p_contract_id int,
  p_scopes_json jsonb
)
RETURNS TABLE (
  contract_id int,
  scope_id int,
  scope_name text,
  scope_type text,
  status text,
  activated_at_utc timestamptz,
  effective_from_utc timestamptz,
  effective_to_utc timestamptz
)
LANGUAGE plpgsql
AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM "Contract"."Contracts" c WHERE c."ContractID" = p_contract_id) THEN
    RAISE EXCEPTION 'contract_id not found';
  END IF;
  IF p_scopes_json IS NULL OR jsonb_typeof(p_scopes_json) <> 'array' THEN
    RAISE EXCEPTION 'scopes_json must be a JSON array';
  END IF;

  DELETE FROM "Contract"."ContractScopes" WHERE "ContractID" = p_contract_id;

  INSERT INTO "Contract"."ContractScopes" (
    "ContractID", "ScopeID", "Status", "ActivatedAtUtc", "EffectiveFromUtc", "EffectiveToUtc"
  )
  SELECT
    p_contract_id,
    (j->>'scope_id')::int,
    COALESCE(NULLIF(j->>'status', ''), 'ACTIVE'),
    COALESCE((j->>'activated_at_utc')::timestamptz, now() AT TIME ZONE 'utc'),
    COALESCE((j->>'effective_from_utc')::timestamptz, now() AT TIME ZONE 'utc'),
    NULLIF(j->>'effective_to_utc', '')::timestamptz
  FROM jsonb_array_elements(p_scopes_json) j
  WHERE (j->>'scope_id') IS NOT NULL;

  RETURN QUERY SELECT * FROM portal.sp_list_contract_scopes(p_contract_id);
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_set_contract_limits(
  p_contract_id int,
  p_limits_json jsonb
)
RETURNS TABLE (
  contract_limit_id bigint,
  contract_id int,
  scope_id int,
  max_active_users int,
  max_storage_gb numeric,
  max_runs_per_month int,
  created_at_utc timestamptz
)
LANGUAGE plpgsql
AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM "Contract"."Contracts" c WHERE c."ContractID" = p_contract_id) THEN
    RAISE EXCEPTION 'contract_id not found';
  END IF;
  IF p_limits_json IS NULL OR jsonb_typeof(p_limits_json) <> 'array' THEN
    RAISE EXCEPTION 'limits_json must be a JSON array';
  END IF;

  DELETE FROM "Contract"."ContractLimits" WHERE "ContractID" = p_contract_id;

  INSERT INTO "Contract"."ContractLimits" (
    "ContractID", "ScopeID", "MaxActiveUsers", "MaxStorageGB", "MaxRunsPerMonth"
  )
  SELECT
    p_contract_id,
    NULLIF(j->>'scope_id', '')::int,
    NULLIF(j->>'max_active_users', '')::int,
    NULLIF(j->>'max_storage_gb', '')::numeric,
    NULLIF(j->>'max_runs_per_month', '')::int
  FROM jsonb_array_elements(p_limits_json) j;

  RETURN QUERY SELECT * FROM portal.sp_list_contract_limits(p_contract_id);
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_set_contract_role_policies(
  p_contract_id int,
  p_policies_json jsonb
)
RETURNS TABLE (
  contract_id int,
  role_id int,
  role_name text,
  grant_type_allowed text,
  max_users_for_role int,
  requires_approval boolean,
  created_at_utc timestamptz
)
LANGUAGE plpgsql
AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM "Contract"."Contracts" c WHERE c."ContractID" = p_contract_id) THEN
    RAISE EXCEPTION 'contract_id not found';
  END IF;
  IF p_policies_json IS NULL OR jsonb_typeof(p_policies_json) <> 'array' THEN
    RAISE EXCEPTION 'policies_json must be a JSON array';
  END IF;

  DELETE FROM "Contract"."ContractRolePolicies" WHERE "ContractID" = p_contract_id;

  INSERT INTO "Contract"."ContractRolePolicies" (
    "ContractID", "RoleID", "GrantTypeAllowed", "MaxUsersForRole", "RequiresApproval"
  )
  SELECT
    p_contract_id,
    (j->>'role_id')::int,
    COALESCE(NULLIF(j->>'grant_type_allowed', ''), 'SCOPED'),
    NULLIF(j->>'max_users_for_role', '')::int,
    COALESCE((j->>'requires_approval')::boolean, false)
  FROM jsonb_array_elements(p_policies_json) j
  WHERE (j->>'role_id') IS NOT NULL;

  RETURN QUERY SELECT * FROM portal.sp_list_contract_role_policies(p_contract_id);
END;
$$;

CREATE OR REPLACE FUNCTION portal.sp_list_contract_usage(p_contract_id int)
RETURNS TABLE (
  contract_id int,
  scope_id int,
  workflow_def_id bigint,
  workflow_name text,
  period_type text,
  period_start_utc timestamptz,
  runs_executed int,
  updated_at_utc timestamptz
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    w."ContractID",
    w."ScopeID",
    w."WorkflowDefID",
    wd.name,
    w."PeriodType"::text,
    w."PeriodStartUtc",
    w."RunsExecuted",
    w."UpdatedAtUtc"
  FROM "Contract"."WorkflowUsageCounters" w
  LEFT JOIN wf.workflow_def wd ON wd.id = w."WorkflowDefID"
  WHERE w."ContractID" = p_contract_id
  ORDER BY w."PeriodStartUtc" DESC;
$$;

DO $drop$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT p.oid::regprocedure AS sig, p.prokind
    FROM pg_proc p
    JOIN pg_namespace n ON n.oid = p.pronamespace
    WHERE n.nspname = 'portal' AND p.proname IN (
      'sp_list_pipeline_profile_catalog',
      'sp_list_assay_procedure_catalog',
      'sp_list_analyte_catalog',
      'sp_list_workflow_definitions',
      'sp_create_and_start_instance'
    )
  LOOP
    IF r.prokind = 'p' THEN
      EXECUTE format('DROP PROCEDURE IF EXISTS %s CASCADE', r.sig);
    ELSE
      EXECUTE format('DROP FUNCTION IF EXISTS %s CASCADE', r.sig);
    END IF;
  END LOOP;
END $drop$;

CREATE OR REPLACE FUNCTION portal.sp_list_pipeline_profile_catalog(
  p_include_advanced boolean DEFAULT false,
  p_scope_id int DEFAULT NULL
)
RETURNS TABLE(
  id bigint,
  name text,
  version text,
  status text,
  title text,
  summary text,
  visibility text,
  lifecycle text,
  family text,
  replaced_by text,
  research_modes jsonb
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    p.id,
    p.name,
    p.version,
    p.status::text,
    p.document_json->'catalog'->>'title',
    p.document_json->'catalog'->>'summary',
    p.document_json->'catalog'->>'visibility',
    p.document_json->'catalog'->>'lifecycle',
    p.document_json->'catalog'->>'family',
    p.document_json->'catalog'->>'replacedBy',
    p.document_json->'catalog'->'researchModes'
  FROM cfg.pipeline_profile p
  WHERE p.status = 'published'
    AND p.document_json->'catalog'->>'lifecycle' = 'active'
    AND (
      p.document_json->'catalog'->>'visibility' = 'operator'
      OR (p_include_advanced AND p.document_json->'catalog'->>'visibility' = 'advanced')
    )
    AND (
      p_scope_id IS NULL
      OR portal.fn_infer_process_pack(p.name, p.document_json) IN (
        SELECT m.modality FROM portal.fn_contract_entitled_modalities(p_scope_id) m
      )
    )
  ORDER BY
    CASE p.document_json->'catalog'->>'family'
      WHEN 'samd' THEN 0
      WHEN 'staged' THEN 1
      ELSE 2
    END,
    p.name,
    p.version;
$$;

CREATE OR REPLACE FUNCTION portal.sp_list_assay_procedure_catalog(
  p_analyte text DEFAULT NULL,
  p_include_advanced boolean DEFAULT false,
  p_scope_id int DEFAULT NULL
)
RETURNS TABLE(
  id bigint,
  name text,
  version text,
  status text,
  title text,
  summary text,
  visibility text,
  lifecycle text,
  family text,
  replaced_by text,
  primary_analyte text,
  default_pipeline_profile_id bigint,
  sample_prep_program_id bigint,
  lifecycle_program_id bigint,
  analyte_expectation jsonb,
  default_pipeline_profile text,
  default_research_mode text
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    p.id,
    p.name,
    p.version,
    p.status::text,
    p.document_json->'catalog'->>'title',
    p.document_json->'catalog'->>'summary',
    p.document_json->'catalog'->>'visibility',
    p.document_json->'catalog'->>'lifecycle',
    p.document_json->'catalog'->>'family',
    p.document_json->'catalog'->>'replacedBy',
    p.primary_analyte,
    p.default_pipeline_profile_id,
    p.sample_prep_program_id,
    p.lifecycle_program_id,
    p.document_json->'analyteExpectation',
    p.document_json->>'pipelineProfile',
    p.document_json->>'researchMode'
  FROM cfg.assay_procedure p
  WHERE p.status = 'published'
    AND p.document_json->'catalog'->>'lifecycle' = 'active'
    AND (
      p.document_json->'catalog'->>'visibility' = 'operator'
      OR (p_include_advanced AND p.document_json->'catalog'->>'visibility' = 'advanced')
    )
    AND (
      p_analyte IS NULL OR btrim(p_analyte) = ''
      OR lower(COALESCE(p.primary_analyte, '')) = lower(btrim(p_analyte))
      OR lower(p.document_json->>'analyteExpectation') = lower(btrim(p_analyte))
      OR EXISTS (
        SELECT 1
        FROM jsonb_array_elements_text(
          CASE
            WHEN jsonb_typeof(p.document_json->'analyteExpectation') = 'array'
              THEN p.document_json->'analyteExpectation'
            ELSE '[]'::jsonb
          END
        ) AS a(val)
        WHERE lower(a.val) = lower(btrim(p_analyte))
      )
    )
    AND (
      p_scope_id IS NULL
      OR portal.fn_infer_process_pack(p.name, p.document_json) IN (
        SELECT m.modality FROM portal.fn_contract_entitled_modalities(p_scope_id) m
      )
    )
  ORDER BY p.name, p.version;
$$;

CREATE OR REPLACE FUNCTION portal.sp_list_analyte_catalog(
  p_include_advanced boolean DEFAULT false,
  p_scope_id int DEFAULT NULL
)
RETURNS TABLE(
  id bigint,
  name text,
  version text,
  status text,
  title text,
  summary text,
  visibility text,
  lifecycle text,
  family text,
  replaced_by text,
  aliases jsonb
)
LANGUAGE sql
STABLE
AS $$
  SELECT
    a.id,
    a.name,
    a.version,
    a.status::text,
    a.document_json->'catalog'->>'title',
    a.document_json->'catalog'->>'summary',
    a.document_json->'catalog'->>'visibility',
    a.document_json->'catalog'->>'lifecycle',
    a.document_json->'catalog'->>'family',
    a.document_json->'catalog'->>'replacedBy',
    a.document_json->'aliases'
  FROM cfg.analyte a
  WHERE a.status = 'published'
    AND a.document_json->'catalog'->>'lifecycle' = 'active'
    AND (
      a.document_json->'catalog'->>'visibility' = 'operator'
      OR (p_include_advanced AND a.document_json->'catalog'->>'visibility' = 'advanced')
    )
    AND (
      p_scope_id IS NULL
      OR portal.fn_infer_process_pack(a.name, a.document_json) IN (
        SELECT m.modality FROM portal.fn_contract_entitled_modalities(p_scope_id) m
      )
    )
  ORDER BY a.name, a.version;
$$;

CREATE OR REPLACE FUNCTION portal.sp_list_workflow_definitions(
  p_source_filter text DEFAULT NULL,
  p_scope_id int DEFAULT NULL
)
RETURNS TABLE (
  workflow_def_id bigint,
  name text,
  source text,
  workflow_version_id bigint,
  version_major int,
  version_minor int
)
LANGUAGE sql
STABLE
AS $$
  SELECT wd.id AS workflow_def_id,
         wd.name,
         COALESCE(wd.source, 'system') AS source,
         wv.id AS workflow_version_id,
         wv.version_major,
         wv.version_minor
  FROM wf.workflow_def wd
  LEFT JOIN LATERAL (
    SELECT id, version_major, version_minor
    FROM wf.workflow_version
    WHERE workflow_def_id = wd.id AND is_active = true
    ORDER BY version_major DESC, version_minor DESC
    LIMIT 1
  ) wv ON true
  WHERE (p_source_filter IS NULL OR COALESCE(wd.source, 'system') = p_source_filter)
    AND (
      p_scope_id IS NULL
      OR portal.fn_infer_process_pack(wd.name, NULL) IN (
        SELECT m.modality FROM portal.fn_contract_entitled_modalities(p_scope_id) m
      )
    )
  ORDER BY wd.name;
$$;

CREATE OR REPLACE FUNCTION portal.sp_create_and_start_instance(
  p_workflow_version_id bigint,
  p_context_json jsonb DEFAULT NULL,
  p_scope_id int DEFAULT NULL
)
RETURNS TABLE (
  id bigint,
  workflow_version_id bigint,
  status text
)
LANGUAGE plpgsql
AS $$
DECLARE
  v_instance_id bigint;
  v_pack varchar(32);
  v_allowed boolean;
  v_cid int;
  v_def_id bigint;
  v_cwe_enabled boolean;
  v_max_runs int;
  v_period_type text;
  v_period_start timestamptz;
  v_runs int := 0;
  v_now timestamptz := now() AT TIME ZONE 'utc';
BEGIN
  IF p_scope_id IS NOT NULL THEN
    SELECT a.is_allowed, a.contract_id
      INTO v_allowed, v_cid
    FROM "Contract".spcontractvalidatescopeaccess(p_scope_id, v_now) a;

    IF NOT COALESCE(v_allowed, false) THEN
      RAISE EXCEPTION 'NO_ACTIVE_CONTRACT_FOR_SCOPE';
    END IF;

    v_pack := portal.fn_infer_process_pack_from_context(p_context_json);
    IF NOT EXISTS (
      SELECT 1 FROM portal.fn_contract_entitled_modalities(p_scope_id) m
      WHERE m.modality = v_pack
    ) THEN
      RAISE EXCEPTION 'PROCESS_PACK_NOT_ENTITLED';
    END IF;

    SELECT wv.workflow_def_id INTO v_def_id
    FROM wf.workflow_version wv
    WHERE wv.id = p_workflow_version_id;
    IF v_def_id IS NULL THEN
      RAISE EXCEPTION 'workflow_version_id not found';
    END IF;

    SELECT e."Enabled", e."MaxRunsPerPeriod", e."PeriodType"
      INTO v_cwe_enabled, v_max_runs, v_period_type
    FROM "Contract"."ContractWorkflowEntitlements" e
    WHERE e."ContractID" = v_cid AND e."WorkflowDefID" = v_def_id;

    IF v_cwe_enabled IS NOT NULL AND NOT v_cwe_enabled THEN
      RAISE EXCEPTION 'WORKFLOW_NOT_ENTITLED';
    END IF;

    IF COALESCE(v_cwe_enabled, false) AND v_max_runs IS NOT NULL AND v_period_type IS NOT NULL THEN
      v_period_start := CASE v_period_type
        WHEN 'DAY' THEN date_trunc('day', v_now)
        WHEN 'WEEK' THEN date_trunc('week', v_now)
        WHEN 'MONTH' THEN date_trunc('month', v_now)
      END;
      SELECT COALESCE(w."RunsExecuted", 0) INTO v_runs
      FROM "Contract"."WorkflowUsageCounters" w
      WHERE w."ContractID" = v_cid
        AND w."ScopeID" = p_scope_id
        AND w."WorkflowDefID" = v_def_id
        AND w."PeriodType" = v_period_type
        AND w."PeriodStartUtc" = v_period_start;
      IF COALESCE(v_runs, 0) >= v_max_runs THEN
        RAISE EXCEPTION 'WORKFLOW_QUOTA_EXCEEDED';
      END IF;
    END IF;
  END IF;

  SELECT created.id INTO v_instance_id
  FROM wf.wf_repo_create_workflow_instance(p_workflow_version_id, p_context_json) AS created;

  CALL wf.sp_start_workflow_instance(v_instance_id);

  RETURN QUERY SELECT * FROM wf.wf_repo_get_workflow_instance(v_instance_id);
END;
$$;
