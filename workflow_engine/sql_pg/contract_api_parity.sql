/*
  PostgreSQL parity for Contract.sp* procedures extracted from
  workflow_engine/sql_mssql/contract_api.sql.

  Depends on:
    contract_schema.sql  – "Contract"."Contracts", "Contract"."ContractScopes",
                            "Contract"."ContractWorkflowEntitlements",
                            "Contract"."WorkflowUsageCounters",
                            "Contract"."ContractRolePolicies"
*/

-- ──────────────────────────────────────────────────────────────────────────────
-- "Contract".spcontractvalidatescopeaccess
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION "Contract".spcontractvalidatescopeaccess(
  p_scope_id int,
  p_utc_now timestamptz DEFAULT NULL
)
RETURNS TABLE(is_allowed boolean, contract_id int, reason_code text)
LANGUAGE plpgsql STABLE AS $$
DECLARE v_now timestamptz := COALESCE(p_utc_now, now() AT TIME ZONE 'utc');
BEGIN
  IF p_scope_id IS NULL OR p_scope_id <= 0 THEN
    RETURN QUERY SELECT false, NULL::int, 'INVALID_SCOPE';
    RETURN;
  END IF;

  RETURN QUERY
  WITH scope_contract AS (
    SELECT c."ContractID"
    FROM "Contract"."ContractScopes" cs
    JOIN "Contract"."Contracts" c ON c."ContractID" = cs."ContractID"
    WHERE cs."ScopeID" = p_scope_id
      AND cs."Status" = 'ACTIVE'
      AND cs."EffectiveFromUtc" <= v_now
      AND (cs."EffectiveToUtc" IS NULL OR cs."EffectiveToUtc" >= v_now)
      AND c."Status" = 'ACTIVE'
      AND c."StartDateUtc" <= v_now
      AND (c."EndDateUtc" IS NULL OR c."EndDateUtc" >= v_now)
    ORDER BY cs."EffectiveFromUtc" DESC, c."ContractID" DESC
    LIMIT 1
  )
  SELECT
    EXISTS (SELECT 1 FROM scope_contract) AS is_allowed,
    (SELECT "ContractID" FROM scope_contract LIMIT 1) AS contract_id,
    CASE WHEN EXISTS (SELECT 1 FROM scope_contract) THEN 'OK' ELSE 'NO_ACTIVE_CONTRACT_FOR_SCOPE' END AS reason_code;
END;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- contract.spcontractvalidateworkflowexecution
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION "Contract".spcontractvalidateworkflowexecution(
  p_scope_id int,
  p_workflow_def_id bigint,
  p_utc_now timestamptz DEFAULT NULL
)
RETURNS TABLE(
  is_allowed boolean, contract_id int, reason_code text,
  runs_executed int, max_runs_per_period int, period_type text
)
LANGUAGE plpgsql STABLE AS $$
DECLARE
  v_now        timestamptz := COALESCE(p_utc_now, now() AT TIME ZONE 'utc');
  v_allowed    boolean;
  v_cid        int;
  v_reason     text;
  v_enabled    boolean;
  v_max_runs   int;
  v_period_type text;
  v_period_start timestamptz;
  v_runs_exec  int := 0;
BEGIN
  -- Scope access check
  SELECT a.is_allowed, a.contract_id, a.reason_code
  INTO v_allowed, v_cid, v_reason
  FROM "Contract".spcontractvalidatescopeaccess(p_scope_id, v_now) a;

  IF NOT COALESCE(v_allowed, false) THEN
    RETURN QUERY SELECT false, v_cid, 'NO_ACTIVE_CONTRACT_FOR_SCOPE', 0, NULL::int, NULL::text;
    RETURN;
  END IF;

  SELECT e."Enabled", e."MaxRunsPerPeriod", e."PeriodType"
  INTO v_enabled, v_max_runs, v_period_type
  FROM "Contract"."ContractWorkflowEntitlements" e
  WHERE e."ContractID" = v_cid AND e."WorkflowDefID" = p_workflow_def_id;

  IF v_enabled IS NULL OR NOT v_enabled THEN
    RETURN QUERY SELECT false, v_cid, 'WORKFLOW_NOT_ENTITLED', 0, NULL::int, NULL::text;
    RETURN;
  END IF;

  IF v_max_runs IS NOT NULL AND v_period_type IS NOT NULL THEN
    v_period_start := CASE v_period_type
      WHEN 'DAY'   THEN date_trunc('day',  v_now AT TIME ZONE 'utc')
      WHEN 'WEEK'  THEN date_trunc('week', v_now AT TIME ZONE 'utc')
      WHEN 'MONTH' THEN date_trunc('month',v_now AT TIME ZONE 'utc')
    END;

    SELECT COALESCE(w."RunsExecuted", 0) INTO v_runs_exec
    FROM "Contract"."WorkflowUsageCounters" w
    WHERE w."ContractID" = v_cid AND w."ScopeID" = p_scope_id
      AND w."WorkflowDefID" = p_workflow_def_id
      AND w."PeriodType" = v_period_type AND w."PeriodStartUtc" = v_period_start;

    IF v_runs_exec >= v_max_runs THEN
      RETURN QUERY SELECT false, v_cid, 'WORKFLOW_QUOTA_EXCEEDED', v_runs_exec, v_max_runs, v_period_type;
      RETURN;
    END IF;
  END IF;

  RETURN QUERY SELECT true, v_cid, 'OK', COALESCE(v_runs_exec,0), v_max_runs, v_period_type;
END;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- contract.spcontractconsumeworkflowquota
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION "Contract".spcontractconsumeworkflowquota(
  p_scope_id int,
  p_workflow_def_id bigint,
  p_consume_runs int DEFAULT 1,
  p_utc_now timestamptz DEFAULT NULL
)
RETURNS TABLE(
  is_allowed boolean, contract_id int, reason_code text,
  runs_executed int, max_runs_per_period int, period_type text,
  period_start_utc timestamptz
)
LANGUAGE plpgsql AS $$
DECLARE
  v_now         timestamptz := COALESCE(p_utc_now, now() AT TIME ZONE 'utc');
  v_cid         int;
  v_enabled     boolean;
  v_max_runs    int;
  v_period_type text;
  v_period_start timestamptz;
  v_runs_exec   int := 0;
  v_new_runs    int;
BEGIN
  IF p_scope_id IS NULL OR p_scope_id <= 0
     OR p_workflow_def_id IS NULL OR p_workflow_def_id <= 0
     OR p_consume_runs IS NULL OR p_consume_runs <= 0
  THEN
    RAISE EXCEPTION 'ValidationError: scope_id, workflow_def_id and consume_runs (>0) are required.';
  END IF;

  -- Resolve active contract
  SELECT a.contract_id INTO v_cid
  FROM "Contract".spcontractvalidatescopeaccess(p_scope_id, v_now) a
  WHERE a.is_allowed;

  IF v_cid IS NULL THEN
    RAISE EXCEPTION 'BusinessRule: Scope has no active contract.';
  END IF;

  SELECT e."Enabled", e."MaxRunsPerPeriod", e."PeriodType"
  INTO v_enabled, v_max_runs, v_period_type
  FROM "Contract"."ContractWorkflowEntitlements" e
  WHERE e."ContractID" = v_cid AND e."WorkflowDefID" = p_workflow_def_id;

  IF v_enabled IS NULL OR NOT v_enabled THEN
    RAISE EXCEPTION 'BusinessRule: Workflow is not entitled for the active contract.';
  END IF;

  IF v_max_runs IS NULL OR v_period_type IS NULL THEN
    RETURN QUERY
    SELECT true, v_cid, 'OK_UNLIMITED', NULL::int, NULL::int, NULL::text, NULL::timestamptz;
    RETURN;
  END IF;

  IF v_period_type = 'DAY' THEN
    v_period_start := date_trunc('day',   v_now AT TIME ZONE 'utc');
  ELSIF v_period_type = 'WEEK' THEN
    v_period_start := date_trunc('week',  v_now AT TIME ZONE 'utc');
  ELSIF v_period_type = 'MONTH' THEN
    v_period_start := date_trunc('month', v_now AT TIME ZONE 'utc');
  ELSE
    RAISE EXCEPTION 'ValidationError: Unsupported PeriodType: %', v_period_type;
  END IF;

  -- Lock and read counter
  SELECT COALESCE(w."RunsExecuted", 0) INTO v_runs_exec
  FROM "Contract"."WorkflowUsageCounters" w
  WHERE w."ContractID" = v_cid AND w."ScopeID" = p_scope_id
    AND w."WorkflowDefID" = p_workflow_def_id
    AND w."PeriodType" = v_period_type AND w."PeriodStartUtc" = v_period_start
  FOR UPDATE;

  IF v_runs_exec IS NULL THEN
    INSERT INTO "Contract"."WorkflowUsageCounters"
      ("ContractID","ScopeID","WorkflowDefID","PeriodType","PeriodStartUtc","RunsExecuted","UpdatedAtUtc")
    VALUES (v_cid, p_scope_id, p_workflow_def_id, v_period_type, v_period_start, 0, v_now);
    v_runs_exec := 0;
  END IF;

  v_new_runs := v_runs_exec + p_consume_runs;
  IF v_new_runs > v_max_runs THEN
    RETURN QUERY
    SELECT false, v_cid, 'WORKFLOW_QUOTA_EXCEEDED', v_runs_exec, v_max_runs, v_period_type, v_period_start;
    RETURN;
  END IF;

  UPDATE "Contract"."WorkflowUsageCounters"
  SET "RunsExecuted" = v_new_runs, "UpdatedAtUtc" = v_now
  WHERE "ContractID" = v_cid AND "ScopeID" = p_scope_id
    AND "WorkflowDefID" = p_workflow_def_id
    AND "PeriodType" = v_period_type AND "PeriodStartUtc" = v_period_start;

  RETURN QUERY
  SELECT true, v_cid, 'OK', v_new_runs, v_max_runs, v_period_type, v_period_start;
END;
$$;

-- ──────────────────────────────────────────────────────────────────────────────
-- contract.spcontractvalidaterolegrant
-- Validates that granting a role to a user complies with contract role policies.
-- ──────────────────────────────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION "Contract".spcontractvalidaterolegrant(
  p_scope_id int,
  p_role_id int,
  p_utc_now timestamptz DEFAULT NULL
)
RETURNS TABLE(is_allowed boolean, contract_id int, reason_code text)
LANGUAGE plpgsql STABLE AS $$
DECLARE
  v_now     timestamptz := COALESCE(p_utc_now, now() AT TIME ZONE 'utc');
  v_allowed boolean;
  v_cid     int;
  v_reason  text;
BEGIN
  SELECT a.is_allowed, a.contract_id, a.reason_code
  INTO v_allowed, v_cid, v_reason
  FROM "Contract".spcontractvalidatescopeaccess(p_scope_id, v_now) a;

  IF NOT COALESCE(v_allowed, false) THEN
    RETURN QUERY SELECT false, v_cid, 'NO_ACTIVE_CONTRACT_FOR_SCOPE';
    RETURN;
  END IF;

  -- Check role policy for this contract
  IF NOT EXISTS (
    SELECT 1 FROM "Contract"."ContractRolePolicies" crp
    WHERE crp."ContractID" = v_cid AND crp."RoleID" = p_role_id AND crp."AllowGrant" = true
  ) THEN
    RETURN QUERY SELECT false, v_cid, 'ROLE_GRANT_NOT_PERMITTED';
    RETURN;
  END IF;

  RETURN QUERY SELECT true, v_cid, 'OK';
END;
$$;
