/*
  Register split-detector workflow actions (PostgreSQL, run once per wf database).

  Prerequisites:
    - wf schema deployed (workflow_engine/sql_pg/*.sql)
    - wf_repo_upsert_workflow_action.sql applied

  Upserts:
    pipeline.dmp_select          → methyl-dmp-select
    pipeline.gene_select         → methyl-gene-select
    pipeline.gene_feature_select → methyl-gene-feature-select
    validation.biomarker_filter  → validation.biomarker-filter

  Prefer full catalog + task schemas (recommended for distributed workers):
    bash scripts/bootstrap_distributed_workers.sh --skip-schema --use-gateway-only

  This script is a lightweight alternative when you only need these four rows
  (Azure SQL equivalent: workflow_engine/sql_mssql/wf_split_detector_actions_seed.sql).
*/

DO $$
BEGIN
  IF to_regprocedure('wf.wf_repo_upsert_workflow_action(text,text,text)') IS NULL THEN
    RAISE EXCEPTION 'Prerequisite missing: deploy wf_repo_upsert_workflow_action.sql first';
  END IF;
END $$;

CALL wf.wf_repo_upsert_workflow_action(
  'pipeline.dmp_select', 'methyl-dmp-select', 'pipeline.dmp_select');
CALL wf.wf_repo_upsert_workflow_action(
  'pipeline.gene_select', 'methyl-gene-select', 'pipeline.gene_select');
CALL wf.wf_repo_upsert_workflow_action(
  'pipeline.gene_feature_select', 'methyl-gene-feature-select', 'pipeline.gene_feature_select');
CALL wf.wf_repo_upsert_workflow_action(
  'validation.biomarker_filter', 'validation.biomarker-filter', 'validation.biomarker_filter');

DO $$
BEGIN
  RAISE NOTICE 'Upserted split-detector actions: pipeline.dmp_select, pipeline.gene_select, pipeline.gene_feature_select, validation.biomarker_filter';
END $$;
