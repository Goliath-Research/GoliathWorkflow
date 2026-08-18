/*
  Study pipeline listing + stage rollup for EpiPortal (Azure SQL).

  - portal.sp_list_study_instances
  - portal.sp_get_study_pipeline_progress
  - wf.pipeline_stage_map (action_name prefix → science stage)

  Prerequisites: cfg.study_instance_link, wf.workflow_instance, wf.node_execution,
  wf.workflow_action. Deploy after cfg_wf_relationships.sql / portal_workflow_api.sql.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'wf.pipeline_stage_map', N'U') IS NULL
BEGIN
    CREATE TABLE wf.pipeline_stage_map (
        action_name_prefix nvarchar(128) NOT NULL,
        stage_key varchar(32) NOT NULL,
        stage_seq smallint NOT NULL,
        CONSTRAINT PK_wf_pipeline_stage_map PRIMARY KEY CLUSTERED (action_name_prefix)
    );
END
GO

MERGE wf.pipeline_stage_map AS t
USING (VALUES
    (N'sample.download',            N'download',      10),
    (N'sample.parabricks',          N'alignment',     20),
    (N'sample.methylgrapher',       N'alignment',     20),
    (N'sample.mojo',                N'alignment',     20),
    (N'sample.trim',                N'alignment_qc',  25),
    (N'sample.methyl_qc',           N'alignment_qc',  30),
    (N'sample.methyl_extract',      N'extraction',    40),
    (N'sample.extraction_qc',       N'extraction_qc', 45),
    (N'sample.archive',             N'archive',       50),
    (N'sample.delete',              N'cleanup',       55),
    (N'sample.qc_failed',           N'archive',       50),
    (N'validation.plan_iterations', N'feature_mc',    60),
    (N'pipeline.centroid',          N'feature_mc',    61),
    (N'pipeline.detector',          N'feature_mc',    62),
    (N'validation.stability',       N'stability',     70),
    (N'validation.prepare_freeze',  N'freeze',        80),
    (N'pipeline.mapper',            N'biological',    90),
    (N'pipeline.enricher',          N'biological',    91),
    (N'pipeline.progression',       N'biological',    92),
    (N'pipeline.cell_deconv',       N'biological',    93),
    (N'validation.model_mc',        N'modeling',     100),
    (N'pipeline.classifier',        N'modeling',     101),
    (N'validation.select_best',     N'selection',    110),
    (N'validation.post_model',      N'validation',   120),
    (N'pipeline.predictor',         N'prediction',   130)
) AS s(action_name_prefix, stage_key, stage_seq)
ON t.action_name_prefix = s.action_name_prefix
WHEN MATCHED THEN UPDATE SET stage_key = s.stage_key, stage_seq = s.stage_seq
WHEN NOT MATCHED THEN INSERT (action_name_prefix, stage_key, stage_seq)
    VALUES (s.action_name_prefix, s.stage_key, s.stage_seq);
GO

CREATE OR ALTER FUNCTION wf.fn_pipeline_stage_for_action(@action_name nvarchar(256))
RETURNS TABLE
AS
RETURN
(
    SELECT TOP (1) m.stage_key, m.stage_seq
    FROM wf.pipeline_stage_map m
    WHERE @action_name IS NOT NULL
      AND LEFT(@action_name, LEN(m.action_name_prefix)) = m.action_name_prefix
    ORDER BY LEN(m.action_name_prefix) DESC
);
GO

CREATE OR ALTER FUNCTION wf.fn_instance_kind(@workflow_name nvarchar(256))
RETURNS varchar(32)
AS
BEGIN
    DECLARE @n nvarchar(256) = LOWER(ISNULL(@workflow_name, N''));
    IF @n LIKE N'%sample%prep%' OR @n LIKE N'%sample_prep%' RETURN N'sample_prep';
    IF @n LIKE N'%predict%' OR @n LIKE N'%blind%' RETURN N'prediction';
    RETURN N'study_lifecycle';
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_study_instances
    @study_row_id bigint,
    @status_filter varchar(32) = NULL,
    @top_n int = 100
AS
BEGIN
    SET NOCOUNT ON;

    IF @study_row_id IS NULL OR @study_row_id <= 0
        THROW 50001, N'study_row_id is required.', 1;

    IF @top_n IS NULL OR @top_n < 1 SET @top_n = 100;
    IF @top_n > 500 SET @top_n = 500;

    DECLARE @filter varchar(32) = NULLIF(LTRIM(RTRIM(@status_filter)), N'');

    SELECT TOP (@top_n)
        i.id AS workflow_instance_id,
        i.workflow_version_id,
        d.id AS workflow_def_id,
        d.name AS workflow_name,
        wf.fn_instance_kind(d.name) AS instance_kind,
        v.version_major,
        v.version_minor,
        i.status,
        i.started_at_utc,
        i.completed_at_utc,
        l.domain_program_id,
        l.pipeline_profile_id,
        l.assay_procedure_id,
        l.created_at_utc AS linked_at_utc
    FROM cfg.study_instance_link l
    INNER JOIN wf.workflow_instance i ON i.id = l.workflow_instance_id
    INNER JOIN wf.workflow_version v ON v.id = i.workflow_version_id
    INNER JOIN wf.workflow_def d ON d.id = v.workflow_def_id
    WHERE l.study_row_id = @study_row_id
      AND (@filter IS NULL OR i.status = @filter)
    ORDER BY COALESCE(i.started_at_utc, l.created_at_utc) DESC, i.id DESC;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_get_study_pipeline_progress
    @study_row_id bigint
AS
BEGIN
    SET NOCOUNT ON;

    IF @study_row_id IS NULL OR @study_row_id <= 0
        THROW 50001, N'study_row_id is required.', 1;

    ;WITH latest AS (
        SELECT
            wf.fn_instance_kind(d.name) AS instance_kind,
            i.id AS workflow_instance_id,
            i.status AS instance_status,
            d.name AS workflow_name,
            i.started_at_utc,
            ROW_NUMBER() OVER (
                PARTITION BY wf.fn_instance_kind(d.name)
                ORDER BY COALESCE(i.started_at_utc, l.created_at_utc) DESC, i.id DESC
            ) AS rn
        FROM cfg.study_instance_link l
        INNER JOIN wf.workflow_instance i ON i.id = l.workflow_instance_id
        INNER JOIN wf.workflow_version v ON v.id = i.workflow_version_id
        INNER JOIN wf.workflow_def d ON d.id = v.workflow_def_id
        WHERE l.study_row_id = @study_row_id
    )
    SELECT
        lt.instance_kind,
        lt.workflow_instance_id,
        lt.instance_status,
        lt.workflow_name,
        COALESCE(st.stage_key, N'other') AS stage_key,
        COALESCE(st.stage_seq, 999) AS stage_seq,
        COUNT_BIG(*) AS task_count,
        SUM(CASE WHEN ne.status = N'SUCCEEDED' THEN 1 ELSE 0 END) AS succeeded_count,
        SUM(CASE WHEN ne.status = N'FAILED' THEN 1 ELSE 0 END) AS failed_count,
        SUM(CASE WHEN ne.status = N'RUNNING' THEN 1 ELSE 0 END) AS running_count,
        SUM(CASE WHEN ne.status IN (N'READY', N'PENDING') THEN 1 ELSE 0 END) AS queued_count
    FROM latest lt
    INNER JOIN wf.node_execution ne ON ne.workflow_instance_id = lt.workflow_instance_id
    INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
    LEFT JOIN wf.workflow_action wa ON wa.id = wn.workflow_action_id
    OUTER APPLY wf.fn_pipeline_stage_for_action(wa.action_name) st
    WHERE lt.rn = 1
    GROUP BY
        lt.instance_kind,
        lt.workflow_instance_id,
        lt.instance_status,
        lt.workflow_name,
        COALESCE(st.stage_key, N'other'),
        COALESCE(st.stage_seq, 999)
    ORDER BY lt.instance_kind, COALESCE(st.stage_seq, 999);
END
GO
