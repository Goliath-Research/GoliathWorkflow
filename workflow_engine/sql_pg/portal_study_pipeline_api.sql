/*
  Study pipeline listing + stage rollup for EpiPortal (PostgreSQL).
  Twin of sql_mssql/portal_study_pipeline_api.sql.
*/

CREATE TABLE IF NOT EXISTS wf.pipeline_stage_map (
  action_name_prefix text NOT NULL PRIMARY KEY,
  stage_key varchar(32) NOT NULL,
  stage_seq smallint NOT NULL
);

INSERT INTO wf.pipeline_stage_map (action_name_prefix, stage_key, stage_seq)
VALUES
  ('sample.download',            'download',      10),
  ('sample.parabricks',          'alignment',     20),
  ('sample.methylgrapher',       'alignment',     20),
  ('sample.mojo',                'alignment',     20),
  ('sample.trim',                'alignment_qc',  25),
  ('sample.methyl_qc',           'alignment_qc',  30),
  ('sample.methyl_extract',      'extraction',    40),
  ('sample.extraction_qc',       'extraction_qc', 45),
  ('sample.archive',             'archive',       50),
  ('sample.delete',              'cleanup',       55),
  ('sample.qc_failed',           'archive',       50),
  ('validation.plan_iterations', 'feature_mc',    60),
  ('pipeline.centroid',          'feature_mc',    61),
  ('pipeline.detector',          'feature_mc',    62),
  ('validation.stability',       'stability',     70),
  ('validation.prepare_freeze',  'freeze',        80),
  ('pipeline.mapper',            'biological',    90),
  ('pipeline.enricher',          'biological',    91),
  ('pipeline.progression',       'biological',    92),
  ('pipeline.cell_deconv',       'biological',    93),
  ('validation.model_mc',        'modeling',     100),
  ('pipeline.classifier',        'modeling',     101),
  ('validation.select_best',     'selection',    110),
  ('validation.post_model',      'validation',   120),
  ('pipeline.predictor',         'prediction',   130)
ON CONFLICT (action_name_prefix) DO UPDATE
SET stage_key = EXCLUDED.stage_key,
    stage_seq = EXCLUDED.stage_seq;

CREATE OR REPLACE FUNCTION wf.fn_pipeline_stage_for_action(p_action_name text)
RETURNS TABLE (stage_key varchar(32), stage_seq smallint)
LANGUAGE sql
STABLE
AS $$
  SELECT m.stage_key, m.stage_seq
  FROM wf.pipeline_stage_map m
  WHERE p_action_name IS NOT NULL
    AND left(p_action_name, length(m.action_name_prefix)) = m.action_name_prefix
  ORDER BY length(m.action_name_prefix) DESC
  LIMIT 1;
$$;

CREATE OR REPLACE FUNCTION wf.fn_instance_kind(p_workflow_name text)
RETURNS varchar(32)
LANGUAGE sql
IMMUTABLE
AS $$
  SELECT CASE
    WHEN lower(coalesce(p_workflow_name, '')) LIKE '%sample%prep%'
      OR lower(coalesce(p_workflow_name, '')) LIKE '%sample_prep%'
      THEN 'sample_prep'
    WHEN lower(coalesce(p_workflow_name, '')) LIKE '%predict%'
      OR lower(coalesce(p_workflow_name, '')) LIKE '%blind%'
      THEN 'prediction'
    ELSE 'study_lifecycle'
  END;
$$;

DROP FUNCTION IF EXISTS portal.sp_list_study_instances(bigint, text, int);

CREATE OR REPLACE FUNCTION portal.sp_list_study_instances(
  p_study_row_id bigint,
  p_status_filter text DEFAULT NULL,
  p_top_n int DEFAULT 100
)
RETURNS TABLE (
  workflow_instance_id bigint,
  workflow_version_id bigint,
  workflow_def_id bigint,
  workflow_name text,
  instance_kind varchar(32),
  version_major int,
  version_minor int,
  status text,
  started_at_utc timestamptz,
  completed_at_utc timestamptz,
  domain_program_id bigint,
  pipeline_profile_id bigint,
  assay_procedure_id bigint,
  linked_at_utc timestamptz
)
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
  v_top int := LEAST(GREATEST(COALESCE(p_top_n, 100), 1), 500);
  v_filter text := NULLIF(btrim(p_status_filter), '');
BEGIN
  IF p_study_row_id IS NULL OR p_study_row_id <= 0 THEN
    RAISE EXCEPTION 'study_row_id is required';
  END IF;

  RETURN QUERY
  SELECT
      i.id,
      i.workflow_version_id,
      d.id,
      d.name,
      wf.fn_instance_kind(d.name),
      v.version_major,
      v.version_minor,
      i.status,
      i.started_at_utc,
      i.completed_at_utc,
      l.domain_program_id,
      l.pipeline_profile_id,
      l.assay_procedure_id,
      l.created_at_utc
  FROM cfg.study_instance_link l
  INNER JOIN wf.workflow_instance i ON i.id = l.workflow_instance_id
  INNER JOIN wf.workflow_version v ON v.id = i.workflow_version_id
  INNER JOIN wf.workflow_def d ON d.id = v.workflow_def_id
  WHERE l.study_row_id = p_study_row_id
    AND (v_filter IS NULL OR i.status = v_filter)
  ORDER BY COALESCE(i.started_at_utc, l.created_at_utc) DESC, i.id DESC
  LIMIT v_top;
END;
$$;

DROP FUNCTION IF EXISTS portal.sp_get_study_pipeline_progress(bigint);

CREATE OR REPLACE FUNCTION portal.sp_get_study_pipeline_progress(
  p_study_row_id bigint
)
RETURNS TABLE (
  instance_kind varchar(32),
  workflow_instance_id bigint,
  instance_status text,
  workflow_name text,
  stage_key varchar(32),
  stage_seq smallint,
  task_count bigint,
  succeeded_count bigint,
  failed_count bigint,
  running_count bigint,
  queued_count bigint
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
  IF p_study_row_id IS NULL OR p_study_row_id <= 0 THEN
    RAISE EXCEPTION 'study_row_id is required';
  END IF;

  RETURN QUERY
  WITH latest AS (
    SELECT
      wf.fn_instance_kind(d.name) AS instance_kind,
      i.id AS workflow_instance_id,
      i.status AS instance_status,
      d.name AS workflow_name,
      ROW_NUMBER() OVER (
        PARTITION BY wf.fn_instance_kind(d.name)
        ORDER BY COALESCE(i.started_at_utc, l.created_at_utc) DESC, i.id DESC
      ) AS rn
    FROM cfg.study_instance_link l
    INNER JOIN wf.workflow_instance i ON i.id = l.workflow_instance_id
    INNER JOIN wf.workflow_version v ON v.id = i.workflow_version_id
    INNER JOIN wf.workflow_def d ON d.id = v.workflow_def_id
    WHERE l.study_row_id = p_study_row_id
  )
  SELECT
    lt.instance_kind,
    lt.workflow_instance_id,
    lt.instance_status,
    lt.workflow_name,
    COALESCE(st.stage_key, 'other')::varchar(32),
    COALESCE(st.stage_seq, 999::smallint),
    COUNT(*)::bigint,
    SUM(CASE WHEN ne.status = 'SUCCEEDED' THEN 1 ELSE 0 END)::bigint,
    SUM(CASE WHEN ne.status = 'FAILED' THEN 1 ELSE 0 END)::bigint,
    SUM(CASE WHEN ne.status = 'RUNNING' THEN 1 ELSE 0 END)::bigint,
    SUM(CASE WHEN ne.status IN ('READY', 'PENDING') THEN 1 ELSE 0 END)::bigint
  FROM latest lt
  INNER JOIN wf.node_execution ne ON ne.workflow_instance_id = lt.workflow_instance_id
  INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
  LEFT JOIN wf.workflow_action wa ON wa.id = wn.workflow_action_id
  LEFT JOIN LATERAL wf.fn_pipeline_stage_for_action(wa.action_name) st ON true
  WHERE lt.rn = 1
  GROUP BY
    lt.instance_kind,
    lt.workflow_instance_id,
    lt.instance_status,
    lt.workflow_name,
    COALESCE(st.stage_key, 'other'),
    COALESCE(st.stage_seq, 999::smallint)
  ORDER BY lt.instance_kind, COALESCE(st.stage_seq, 999::smallint);
END;
$$;
