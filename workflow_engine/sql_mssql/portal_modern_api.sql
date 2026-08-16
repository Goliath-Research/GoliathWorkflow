-- Scripted from live Azure SQL by parity workstream
-- Modern portal.sp_* not yet in incremental sql_mssql files.

-- ============================================================
-- portal.fnGetDiseaseJsonSchema
-- Generates a read-only Draft-07 JSON Schema for a disease from
-- portal.DiseaseFieldContract. This is a FORWARD-LOOKING artifact for the
-- future "manipulate JSON in the UI" capability; it is NOT the import
-- validator (validation is portal.spSampleImportValidate). Custom annotations
-- x-target / x-collection / x-storeMode describe import routing.
-- ============================================================
CREATE OR ALTER   FUNCTION [portal].[fnGetDiseaseJsonSchema]
(
    @DiseaseID int
)
RETURNS nvarchar(max)
AS
BEGIN
    DECLARE @props nvarchar(max), @required nvarchar(max);

    SELECT @props = STRING_AGG(
        '"' + STRING_ESCAPE(c.FieldName, 'json') + '":{' +
            '"type":' +
            CASE c.DataType
                WHEN 'INT'   THEN '"integer"'
                WHEN 'FLOAT' THEN '"number"'
                WHEN 'BOOL'  THEN '"boolean"'
                ELSE '"string"'
            END +
            CASE WHEN c.DataType = 'DATE' THEN ',"format":"date"' 
                 WHEN c.DataType = 'GUID' THEN ',"format":"uuid"' ELSE '' END +
            ISNULL(',"title":"' + STRING_ESCAPE(c.FieldCaption, 'json') + '"', '') +
            ISNULL(',"minimum":' + CONVERT(varchar(40), TRY_CAST(JSON_VALUE(c.ValidationJson, '$.min') AS float)), '') +
            ISNULL(',"maximum":' + CONVERT(varchar(40), TRY_CAST(JSON_VALUE(c.ValidationJson, '$.max') AS float)), '') +
            ISNULL(',"enum":[' + en.EnumList + ']', '') +
            ',"x-target":"' + c.TargetEntity + '"' +
            ISNULL(',"x-collection":"' + STRING_ESCAPE(c.CollectionName, 'json') + '"', '') +
            ISNULL(',"x-storeMode":"' + c.ValueStoreMode + '"', '') +
        '}', ',')
    , @required = STRING_AGG(CASE WHEN c.IsRequired = 1 THEN '"' + STRING_ESCAPE(c.FieldName, 'json') + '"' END, ',')
    FROM portal.DiseaseFieldContract c
    OUTER APPLY (
        SELECT STRING_AGG('"' + STRING_ESCAPE(av.AllowedVal, 'json') + '"', ',') AS EnumList
        FROM (
            SELECT civ.ValueString AS AllowedVal
            FROM Meta.Collections col
            INNER JOIN Meta.CollectionItem ci ON ci.CollectionID = col.ID
            INNER JOIN Meta.CollectionItemValue civ ON civ.CollectionItemID = ci.ID AND civ.Name = 'code'
            WHERE col.Name = c.CollectionName AND c.ValueStoreMode = 'CODE'
            UNION ALL
            SELECT ci.ValueString
            FROM Meta.Collections col
            INNER JOIN Meta.CollectionItem ci ON ci.CollectionID = col.ID
            WHERE col.Name = c.CollectionName AND c.ValueStoreMode = 'LABEL'
            UNION ALL
            SELECT civ.ValueString
            FROM Meta.Collections col
            INNER JOIN Meta.CollectionItem ci ON ci.CollectionID = col.ID
            INNER JOIN Meta.CollectionItemValue civ ON civ.CollectionItemID = ci.ID AND civ.Name = 'reportedValue'
            WHERE col.Name = c.CollectionName AND c.ValueStoreMode = 'REPORTED'
        ) av
    ) en
    WHERE c.DiseaseID = @DiseaseID AND c.IsActive = 1;

    RETURN
        N'{"$schema":"http://json-schema.org/draft-07/schema#","type":"object","properties":{' +
        ISNULL(@props, '') + N'}' +
        ISNULL(N',"required":[' + @required + N']', N'') +
        N'}';
END
GO

-- ============================================================
-- portal.sp_activate_workflow_version
-- Makes @workflow_version_id the single active version of its workflow_def
-- (deactivates the def's other versions). Used by the Workflow Designer's
-- version management.
-- Returns the affected (workflow_def_id, workflow_version_id, is_active).
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[sp_activate_workflow_version]
    @workflow_version_id bigint
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @def_id bigint =
        (SELECT workflow_def_id FROM wf.workflow_version WHERE id = @workflow_version_id);

    IF @def_id IS NULL
        THROW 50030, N'workflow_version_id not found.', 1;

    UPDATE wf.workflow_version
    SET is_active = CASE WHEN id = @workflow_version_id THEN 1 ELSE 0 END
    WHERE workflow_def_id = @def_id;

    SELECT @def_id AS workflow_def_id, @workflow_version_id AS workflow_version_id, 1 AS is_active;
END
GO

CREATE OR ALTER PROCEDURE [portal].[sp_get_node_config]
    @workflow_node_id bigint
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        n.id                                   AS workflow_node_id,
        n.node_key,
        n.node_type,
        a.action_name,
        a.input_type_id,
        tin.name                               AS input_type_name,
        CAST(t.template_json AS nvarchar(max)) AS template_json,
        COALESCE(
            CAST(s.schema_json AS nvarchar(max)),
            wf.wf_repo_project_data_type_schema_json(a.input_type_id)
        )                                      AS input_schema_json,
        COALESCE(s.schema_id, tin.name)        AS schema_id
    FROM wf.workflow_node n
    LEFT JOIN wf.workflow_action a
           ON a.id = n.workflow_action_id
    LEFT JOIN wf.data_type tin
           ON tin.id = a.input_type_id
    LEFT JOIN wf.workflow_input_template t
           ON t.workflow_node_id = n.id
    LEFT JOIN wf.workflow_action_schema s
           ON s.workflow_action_id = a.id AND s.direction = N'input'
    WHERE n.id = @workflow_node_id;
END
GO

/*
  Single-row fallback for Platform -> Reference assets. Prefer the body carried
  by portal.sp_list_reference_assets; this proc is only used when the list row
  has an empty document_json (legacy list proc).
*/
CREATE OR ALTER   PROCEDURE [portal].[sp_get_reference_asset]
    @name nvarchar(256),
    @version nvarchar(64) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    SELECT TOP (1)
        a.id,
        a.name,
        a.version,
        a.status,
        a.asset_type,
        a.content_hash,
        a.storage_endpoint_id,
        CAST(a.document_json AS nvarchar(max)) AS document_json,
        a.created_at_utc,
        a.updated_at_utc
    FROM cfg.reference_asset a
    WHERE a.name = @name
      AND (@version IS NULL OR a.version = @version)
    ORDER BY a.id DESC;
END
GO

CREATE OR ALTER PROCEDURE [portal].[sp_get_session_customer]
    @active_scope_id int = NULL
AS
BEGIN
    /*
      Resolve portal.Customers for the session status bar.

      Priority:
        1) Active RBAC scope -> ContractScopes -> Contracts -> Customers
        2) Same scope (INSTITUTION) -> CustomerInstitutions -> Customers
        3) Customer id 1, else lowest id
    */
    SET NOCOUNT ON;

    DECLARE @customer_id   int;
    DECLARE @customer_name varchar(100);

    IF @active_scope_id IS NOT NULL AND @active_scope_id > 0
    BEGIN
        SELECT TOP (1)
            @customer_id   = c.ID,
            @customer_name = c.Name
        FROM RBAC.Scopes s
        INNER JOIN Contract.ContractScopes cs
            ON cs.ScopeID = s.ScopeID
           AND cs.Status = N'ACTIVE'
        INNER JOIN Contract.Contracts ct
            ON ct.ContractID = cs.ContractID
        INNER JOIN portal.Customers c
            ON c.ID = ct.CustomerID
        WHERE s.ScopeID = @active_scope_id
        ORDER BY cs.ActivatedAtUtc DESC;

        IF @customer_id IS NULL
        BEGIN
            SELECT TOP (1)
                @customer_id   = c.ID,
                @customer_name = c.Name
            FROM RBAC.Scopes s
            INNER JOIN portal.CustomerInstitutions ci
                ON ci.InstitutionID = s.InstitutionID
            INNER JOIN portal.Customers c
                ON c.ID = ci.CustomerID
            WHERE s.ScopeID = @active_scope_id
              AND s.ScopeType = N'INSTITUTION'
            ORDER BY c.ID;
        END
    END

    IF @customer_id IS NULL
    BEGIN
        SELECT TOP (1)
            @customer_id   = c.ID,
            @customer_name = c.Name
        FROM portal.Customers c
        ORDER BY CASE WHEN c.ID = 1 THEN 0 ELSE 1 END, c.ID;
    END

    SELECT
        @customer_id   AS customer_id,
        @customer_name AS customer_name;
END
GO

-- Platform -> Site: one site document (by id, or name + optional version).
CREATE OR ALTER PROCEDURE [portal].[sp_get_site]
    @site_id  bigint        = NULL,
    @name     nvarchar(256) = NULL,
    @version  nvarchar(64)  = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF @site_id IS NOT NULL
    BEGIN
        SELECT TOP (1)
            s.id,
            s.name,
            s.version,
            s.status,
            s.content_hash,
            s.document_json,
            s.created_at_utc,
            s.updated_at_utc
        FROM cfg.site s
        WHERE s.id = @site_id;
        RETURN;
    END

    IF NULLIF(LTRIM(RTRIM(@name)), N'') IS NULL
        THROW 50001, N'sp_get_site: provide @site_id or @name', 1;

    SELECT TOP (1)
        s.id,
        s.name,
        s.version,
        s.status,
        s.content_hash,
        s.document_json,
        s.created_at_utc,
        s.updated_at_utc
    FROM cfg.site s
    WHERE s.name = @name
      AND (@version IS NULL OR s.version = @version)
    ORDER BY
        CASE WHEN s.status = 'published' THEN 0 ELSE 1 END,
        s.id DESC;
END
GO

-- ============================================================
-- portal.sp_get_study
-- One cfg.study row + portal.project bridge fields.
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[sp_get_study]
    @study_row_id bigint = NULL,
    @name         nvarchar(256) = NULL,
    @version      nvarchar(64) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF @study_row_id IS NULL AND NULLIF(LTRIM(RTRIM(@name)), N'') IS NULL
    BEGIN
        RAISERROR('Provide @study_row_id or @name.', 16, 1);
        RETURN;
    END;

    SELECT TOP 1
        s.id AS study_row_id,
        s.name,
        s.version,
        s.status AS cfg_status,
        COALESCE(NULLIF(LTRIM(RTRIM(s.study_id)), N''), s.name) AS study_id,
        CONCAT(
            N'/work/projects/',
            COALESCE(NULLIF(LTRIM(RTRIM(s.study_id)), N''), s.name),
            N'/configs/project_',
            s.name,
            N'.json'
        ) AS project_path,
        COALESCE(p.display_name, s.name) AS display_name,
        p.archive_profile_key,
        CASE
            WHEN s.status = 'published' THEN 'ACTIVE'
            ELSE 'DISABLED'
        END AS status,
        p.project_id,
        p.customer_id,
        CONVERT(nvarchar(max), s.document_json) AS document_json,
        s.created_at_utc,
        s.updated_at_utc
    FROM cfg.study AS s
    LEFT JOIN portal.project AS p
        ON p.project_path = CONCAT(
            N'/work/projects/',
            COALESCE(NULLIF(LTRIM(RTRIM(s.study_id)), N''), s.name),
            N'/configs/project_',
            s.name,
            N'.json'
        )
    WHERE (@study_row_id IS NOT NULL AND s.id = @study_row_id)
       OR (
            @study_row_id IS NULL
            AND s.name = @name
            AND (@version IS NULL OR s.version = @version)
          )
    ORDER BY s.id DESC;
END
GO

-- ============================================================
-- portal.sp_get_workflow_graph
-- Returns the FULL definition graph of one workflow version as a single JSON
-- document, shaped exactly like the spec consumed by
-- wf.wf_repo_create_workflow_graph / portal.sp_save_workflow_graph. This lets
-- the Workflow Designer load an existing version into memory to view, clone or
-- edit, then save the result as a new version.
--
-- Result set: one row, one column [graph_json] (nvarchar(max)).
--
-- Notes:
--  * bit columns (is_active, foreach_parallel, is_default, is_required) are
--    emitted as 0/1 integers (not JSON booleans) so they round-trip cleanly
--    through the repo proc's CAST(... AS bit).
--  * node input_template is embedded as nested JSON (JSON_QUERY), omitted when
--    the node has no template.
--  * empty collections are emitted as [] (ISNULL guard) so the designer never
--    sees a missing array.
--  * collection_bindings emit JSON field "kind" (spec name) from column
--    source_kind for round-trip with WorkflowDefinitionSpec / repo INSERT.
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[sp_get_workflow_graph]
    @workflow_version_id bigint
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @root_key nvarchar(128);
    SELECT @root_key = rn.node_key
    FROM wf.workflow_version v
    LEFT JOIN wf.workflow_node rn ON rn.id = v.root_node_id
    WHERE v.id = @workflow_version_id;

    SELECT (
        SELECT
            d.id                                    AS workflow_def_id,
            d.name                                  AS name,
            d.description                           AS description,
            v.id                                    AS workflow_version_id,
            v.version_major                         AS version_major,
            v.version_minor                         AS version_minor,
            CAST(v.is_active AS int)                AS is_active,
            @root_key                               AS root_node_key,

            JSON_QUERY(ISNULL((
                SELECT
                    n.node_key,
                    n.node_type,
                    a.action_name,
                    n.repeat_count,
                    n.condition_ref_node_key,
                    n.switch_ref_node_key,
                    n.condition_var,
                    n.switch_var,
                    n.foreach_collection_var,
                    n.foreach_item_var,
                    n.foreach_index_var,
                    CAST(n.foreach_parallel AS int)             AS foreach_parallel,
                    JSON_QUERY(CAST(t.template_json AS nvarchar(max))) AS input_template
                FROM wf.workflow_node n
                LEFT JOIN wf.workflow_action a          ON a.id = n.workflow_action_id
                LEFT JOIN wf.workflow_input_template t  ON t.workflow_node_id = n.id
                WHERE n.workflow_version_id = v.id
                ORDER BY n.id
                FOR JSON PATH
            ), N'[]')) AS nodes,

            JSON_QUERY(ISNULL((
                SELECT
                    pn.node_key                     AS parent_node_key,
                    cn.node_key                     AS child_node_key,
                    e.child_order,
                    e.branch_kind,
                    e.condition_expr,
                    e.switch_case_value,
                    CAST(e.is_default AS int)       AS is_default
                FROM wf.workflow_edge e
                INNER JOIN wf.workflow_node pn ON pn.id = e.parent_node_id
                INNER JOIN wf.workflow_node cn ON cn.id = e.child_node_id
                WHERE pn.workflow_version_id = v.id
                ORDER BY pn.node_key, e.child_order
                FOR JSON PATH
            ), N'[]')) AS edges,

            JSON_QUERY(ISNULL((
                SELECT
                    n.node_key,
                    ib.target_json_path,
                    ib.source_expr,
                    CAST(ib.is_required AS int)     AS is_required
                FROM wf.workflow_input_binding ib
                INNER JOIN wf.workflow_node n ON n.id = ib.workflow_node_id
                WHERE n.workflow_version_id = v.id
                ORDER BY ib.id
                FOR JSON PATH
            ), N'[]')) AS input_bindings,

            JSON_QUERY(ISNULL((
                SELECT
                    n.node_key,
                    ob.var_name,
                    ob.source_kind,
                    ob.source_json_path
                FROM wf.variable_output_binding ob
                INNER JOIN wf.workflow_node n ON n.id = ob.workflow_node_id
                WHERE n.workflow_version_id = v.id
                ORDER BY ob.id
                FOR JSON PATH
            ), N'[]')) AS output_bindings,

            JSON_QUERY(ISNULL((
                SELECT
                    n.node_key,
                    sd.var_name,
                    sd.default_expr
                FROM wf.node_scope_default sd
                INNER JOIN wf.workflow_node n ON n.id = sd.workflow_node_id
                WHERE n.workflow_version_id = v.id
                ORDER BY sd.id
                FOR JSON PATH
            ), N'[]')) AS scope_defaults,

            JSON_QUERY(ISNULL((
                SELECT
                    cb.scope_var,
                    cb.source_kind                  AS kind,
                    cb.bind_order,
                    cb.path_var,
                    cb.base_var,
                    cb.json_path
                FROM wf.workflow_collection_binding cb
                WHERE cb.workflow_version_id = v.id
                ORDER BY cb.bind_order, cb.id
                FOR JSON PATH
            ), N'[]')) AS collection_bindings
        FROM wf.workflow_def d
        INNER JOIN wf.workflow_version v ON v.workflow_def_id = d.id
        WHERE v.id = @workflow_version_id
        FOR JSON PATH, WITHOUT_ARRAY_WRAPPER
    ) AS graph_json;
END
GO

-- ============================================================
-- portal.sp_get_workflow_instance
-- Thin portal facade over wf.wf_repo_get_workflow_instance.
-- ============================================================
CREATE OR ALTER PROCEDURE [portal].[sp_get_workflow_instance]
    @workflow_instance_id bigint
AS
BEGIN
    SET NOCOUNT ON;
    EXEC wf.wf_repo_get_workflow_instance @instance_id = @workflow_instance_id;
END
GO

/* Diseases list for Study Control Start picker. */
CREATE OR ALTER   PROCEDURE [portal].[sp_list_diseases]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT ID, Name
    FROM portal.Diseases
    ORDER BY Name;
END
GO

/* Sample names for a clinical group (Study Control Start). */
CREATE OR ALTER   PROCEDURE [portal].[sp_list_group_sample_names]
    @disease_id int,
    @group_id   int
AS
BEGIN
    SET NOCOUNT ON;

    IF @group_id IS NULL OR @group_id <= 0
    BEGIN
        SELECT CAST(NULL AS nvarchar(256)) AS SampleName WHERE 1 = 0;
        RETURN;
    END;

    IF @disease_id = 1
    BEGIN
        SELECT v.SampleName
        FROM portal.vSamplesProstateCancerExtended AS v
        INNER JOIN portal.GroupSamples AS gs ON gs.SampleID = v.ID
        WHERE gs.GroupID = @group_id
          AND NULLIF(LTRIM(RTRIM(v.SampleName)), N'') IS NOT NULL
        ORDER BY v.SampleName;
        RETURN;
    END;

    IF @disease_id = 2
    BEGIN
        SELECT v.SampleName
        FROM portal.vSamplesBreastCancerExtended AS v
        INNER JOIN portal.GroupSamples AS gs ON gs.SampleID = v.ID
        WHERE gs.GroupID = @group_id
          AND NULLIF(LTRIM(RTRIM(v.SampleName)), N'') IS NOT NULL
        ORDER BY v.SampleName;
        RETURN;
    END;

    -- Generic fallback: LabSamples.Sample when present.
    SELECT
        (
            SELECT TOP (1) ls.Sample
            FROM portal.LabSamples AS ls
            WHERE ls.SampleID = s.ID
            ORDER BY ls.ID DESC
        ) AS SampleName
    FROM portal.Samples AS s
    INNER JOIN portal.GroupSamples AS gs ON gs.SampleID = s.ID
    WHERE gs.GroupID = @group_id
      AND NULLIF(LTRIM(RTRIM((
            SELECT TOP (1) ls.Sample
            FROM portal.LabSamples AS ls
            WHERE ls.SampleID = s.ID
            ORDER BY ls.ID DESC
        ))), N'') IS NOT NULL
    ORDER BY 1;
END
GO

/* ---- expand a cohort into enrollment member rows ---- */

CREATE OR ALTER   PROCEDURE portal.sp_list_group_samples_for_enrollment
    @group_id int
AS
BEGIN
    SET NOCOUNT ON;
    IF @group_id IS NULL OR @group_id <= 0
    BEGIN
        RAISERROR(N'group_id is required', 16, 1);
        RETURN;
    END

    SELECT
        s.ID AS portal_sample_id,
        s.PatientID,
        s.CustomerID,
        s.DiseaseID,
        d.Name AS disease_name,
        ls.lab_sample_id,
        ls.processing_sample_key,
        ls.BatchID
    FROM portal.GroupSamples gs
    INNER JOIN portal.Samples s ON s.ID = gs.SampleID
    LEFT JOIN portal.Diseases d ON d.ID = s.DiseaseID
    OUTER APPLY (
        SELECT TOP (1)
            ls2.ID AS lab_sample_id,
            COALESCE(
                NULLIF(LTRIM(RTRIM(ls2.Sample)), N''),
                NULLIF(LTRIM(RTRIM(CAST(s.PatientID AS nvarchar(64)))), N'')
            ) AS processing_sample_key,
            ls2.BatchID
        FROM portal.LabSamples ls2
        WHERE ls2.SampleID = s.ID
        ORDER BY ls2.ID DESC
    ) ls
    WHERE gs.GroupID = @group_id
    ORDER BY d.Name, s.ID;
END
GO

/* Groups for a customer/disease (Study Control Start). */
CREATE OR ALTER   PROCEDURE [portal].[sp_list_groups_for_disease]
    @customer_id int,
    @disease_id  int
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        g.ID,
        g.Name,
        g.Description
    FROM portal.Groups AS g
    WHERE g.CustomerID = @customer_id
      AND (
            EXISTS (
                SELECT 1
                FROM portal.GroupSamples AS gs
                INNER JOIN portal.Samples AS s ON s.ID = gs.SampleID
                WHERE gs.GroupID = g.ID
                  AND s.DiseaseID = @disease_id
            )
            OR NOT EXISTS (
                SELECT 1
                FROM portal.GroupSamples AS gs
                WHERE gs.GroupID = g.ID
            )
          )
    ORDER BY g.Name;
END
GO

/* ---- picker: clinical cohorts available to seed cfg.study_group ---- */

CREATE OR ALTER   PROCEDURE portal.sp_list_groups_for_study_enrollment
    @customer_id int = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        g.ID          AS group_id,
        g.Name        AS group_name,
        g.Description,
        g.CustomerID,
        (
            SELECT COUNT(*)
            FROM portal.GroupSamples gs
            WHERE gs.GroupID = g.ID
        ) AS sample_count
    FROM portal.Groups g
    WHERE (
        @customer_id IS NULL
        OR g.CustomerID = @customer_id
        OR g.CustomerID IS NULL
    )
    ORDER BY g.Name;
END
GO

-- ============================================================
-- portal.sp_list_hyperparam_searches
-- Landing list for HPO Monitor (read-only). Filters optional.
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[sp_list_hyperparam_searches]
    @study_row_id BIGINT = NULL,
    @status NVARCHAR(32) = NULL,
    @top_n INT = 100
AS
BEGIN
    SET NOCOUNT ON;

    IF @top_n IS NULL OR @top_n < 1
        SET @top_n = 100;
    IF @top_n > 500
        SET @top_n = 500;

    SELECT TOP (@top_n)
        r.id AS search_id,
        r.study_row_id,
        r.display_name,
        r.status,
        COUNT(t.id) AS trial_count,
        ISNULL(SUM(CASE WHEN t.status = N'scored' THEN 1 ELSE 0 END), 0) AS scored_count,
        r.created_at_utc,
        r.created_by
    FROM cfg.hyperparameter_search_run AS r
    LEFT JOIN cfg.hyperparameter_trial AS t ON t.search_id = r.id
    WHERE (@study_row_id IS NULL OR r.study_row_id = @study_row_id)
      AND (@status IS NULL OR @status = N'' OR r.status = @status)
    GROUP BY
        r.id,
        r.study_row_id,
        r.display_name,
        r.status,
        r.created_at_utc,
        r.created_by
    ORDER BY r.created_at_utc DESC, r.id DESC;
END;
GO

-- ============================================================
-- portal.sp_list_ops_instances
-- Cross-study instance list for Home / Ops board.
-- @status_filter: NULL/'' = RUNNING+FAILED+CREATED (ops-relevant);
--                 otherwise exact match (e.g. COMPLETED).
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[sp_list_ops_instances]
    @status_filter varchar(32) = NULL,
    @top_n         int         = 100
AS
BEGIN
    SET NOCOUNT ON;

    IF @top_n IS NULL OR @top_n < 1
        SET @top_n = 100;
    IF @top_n > 500
        SET @top_n = 500;

    DECLARE @filter varchar(32) = NULLIF(LTRIM(RTRIM(@status_filter)), N'');

    SELECT TOP (@top_n)
        i.id                   AS workflow_instance_id,
        i.workflow_version_id,
        d.id                   AS workflow_def_id,
        d.name                 AS workflow_name,
        v.version_major,
        v.version_minor,
        i.status,
        i.started_at_utc,
        i.completed_at_utc,
        (
            SELECT COUNT_BIG(1)
            FROM wf.node_execution ne
            WHERE ne.workflow_instance_id = i.id
              AND ne.status = N'RUNNING'
        ) AS running_tasks,
        (
            SELECT COUNT_BIG(1)
            FROM wf.task_lease tl
            INNER JOIN wf.node_execution ne ON ne.id = tl.node_execution_id
            WHERE ne.workflow_instance_id = i.id
              AND tl.lease_expires_at_utc < SYSUTCDATETIME()
        ) AS expired_leases
    FROM wf.workflow_instance i
    INNER JOIN wf.workflow_version v ON v.id = i.workflow_version_id
    INNER JOIN wf.workflow_def d ON d.id = v.workflow_def_id
    WHERE (
            @filter IS NOT NULL AND i.status = @filter
         )
       OR (
            @filter IS NULL
            AND i.status IN (N'RUNNING', N'FAILED', N'CREATED')
          )
    ORDER BY
        CASE i.status
            WHEN N'RUNNING' THEN 0
            WHEN N'FAILED'  THEN 1
            WHEN N'CREATED' THEN 2
            ELSE 3
        END,
        COALESCE(i.started_at_utc, i.completed_at_utc) DESC,
        i.id DESC;
END
GO

-- ============================================================
-- portal.sp_list_recent_instances
-- Recent workflow instances for Study Control monitor picker.
-- ============================================================
CREATE OR ALTER PROCEDURE [portal].[sp_list_recent_instances]
    @top_n int = 50
AS
BEGIN
    SET NOCOUNT ON;

    IF @top_n IS NULL OR @top_n < 1
        SET @top_n = 50;
    IF @top_n > 500
        SET @top_n = 500;

    SELECT TOP (@top_n)
        i.id                   AS workflow_instance_id,
        i.workflow_version_id,
        d.id                   AS workflow_def_id,
        d.name                 AS workflow_name,
        v.version_major,
        v.version_minor,
        i.status,
        i.started_at_utc,
        i.completed_at_utc
    FROM wf.workflow_instance i
    INNER JOIN wf.workflow_version v ON v.id = i.workflow_version_id
    INNER JOIN wf.workflow_def d ON d.id = v.workflow_def_id
    ORDER BY COALESCE(i.started_at_utc, i.completed_at_utc) DESC, i.id DESC;
END
GO

/*
  Platform -> Reference assets: browse cfg.reference_asset (genomes, GTF, caches,
  provision recipes). Read-only for the portal; provisioning stays methyl-cfg
  provision-assets.

  The list carries document_json (CAST to nvarchar(max)) so the detail panel reads
  the body off the selected grid row. The session connection is prMSOLEDB without
  MARS; a per-click sp_get_* is a second live statement and stalls the session.
  Native sys.json is not serializable by the uniGUI grid store.
*/
CREATE OR ALTER   PROCEDURE [portal].[sp_list_reference_assets]
    @published_only bit = 0,
    @asset_type nvarchar(64) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        a.id,
        a.name,
        a.version,
        a.status,
        a.asset_type,
        a.content_hash,
        a.storage_endpoint_id,
        e.name AS storage_endpoint_name,
        CAST(a.document_json AS nvarchar(max)) AS document_json,
        a.created_at_utc,
        a.updated_at_utc
    FROM cfg.reference_asset a
    LEFT JOIN cfg.storage_endpoint e
           ON e.id = a.storage_endpoint_id
    WHERE (@published_only = 0 OR a.status = 'published')
      AND (
            @asset_type IS NULL
         OR NULLIF(LTRIM(RTRIM(@asset_type)), N'') IS NULL
         OR a.asset_type = @asset_type
          )
    ORDER BY a.asset_type, a.name, a.version;
END
GO

-- Platform -> Site: linked reference assets for a site row.
CREATE OR ALTER PROCEDURE [portal].[sp_list_site_reference_assets]
    @site_id bigint
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        v.link_id,
        v.site_id,
        v.site_name,
        v.reference_asset_id,
        v.asset_name,
        v.asset_role,
        v.storage_endpoint_id,
        v.asset_status
    FROM cfg.v_site_reference_asset v
    WHERE v.site_id = @site_id
    ORDER BY v.asset_role, v.asset_name;
END
GO

-- Platform -> Site: list cfg.site rows (no document_json body).
CREATE OR ALTER PROCEDURE [portal].[sp_list_sites]
    @published_only bit = 0
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        s.id,
        s.name,
        s.version,
        s.status,
        s.content_hash,
        s.created_at_utc,
        s.updated_at_utc
    FROM cfg.site s
    WHERE (@published_only = 0 OR s.status = 'published')
    ORDER BY s.name, s.version;
END
GO

-- ============================================================
-- portal.sp_list_stale_leases
-- Active and expired task leases for Home / Ops board alerts.
-- @expired_only = 1 → only lease_expires_at_utc < now.
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[sp_list_stale_leases]
    @expired_only bit = 1,
    @top_n        int = 200
AS
BEGIN
    SET NOCOUNT ON;

    IF @top_n IS NULL OR @top_n < 1
        SET @top_n = 200;
    IF @top_n > 1000
        SET @top_n = 1000;

    DECLARE @now datetime2(7) = SYSUTCDATETIME();

    SELECT TOP (@top_n)
        tl.node_execution_id,
        ne.workflow_instance_id,
        d.name                         AS workflow_name,
        wn.node_key,
        wa.action_name,
        ne.status                      AS node_status,
        ne.attempt_no,
        w.external_worker_key,
        c.cluster_key,
        tl.lease_expires_at_utc,
        tl.heartbeat_at_utc,
        DATEDIFF(SECOND, tl.lease_expires_at_utc, @now) AS expired_age_sec,
        CASE WHEN tl.lease_expires_at_utc < @now THEN CAST(1 AS bit) ELSE CAST(0 AS bit) END AS is_expired
    FROM wf.task_lease tl
    INNER JOIN wf.node_execution ne ON ne.id = tl.node_execution_id
    INNER JOIN wf.workflow_node wn ON wn.id = ne.workflow_node_id
    LEFT JOIN wf.workflow_action wa ON wa.id = wn.workflow_action_id
    INNER JOIN wf.workflow_instance i ON i.id = ne.workflow_instance_id
    INNER JOIN wf.workflow_version v ON v.id = i.workflow_version_id
    INNER JOIN wf.workflow_def d ON d.id = v.workflow_def_id
    INNER JOIN wf.worker w ON w.id = tl.worker_id
    INNER JOIN wf.cluster c ON c.id = w.cluster_id
    WHERE (@expired_only = 0 OR tl.lease_expires_at_utc < @now)
    ORDER BY tl.lease_expires_at_utc ASC, tl.node_execution_id ASC;
END
GO

-- ============================================================
-- portal.sp_list_storage_profiles
-- Published cfg.storage_profile names for Project Admin / Study
-- Control archive combo (phase B).
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[sp_list_storage_profiles]
    @include_non_published bit = 0
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        s.id AS storage_profile_row_id,
        s.name AS profile_name,
        s.version,
        s.status AS cfg_status,
        CASE WHEN s.status = 'published' THEN 'ACTIVE' ELSE 'DISABLED' END AS status,
        s.created_at_utc,
        s.updated_at_utc
    FROM cfg.storage_profile AS s
    WHERE (@include_non_published = 1 OR s.status = 'published')
    ORDER BY s.name, s.version;
END
GO

-- ============================================================
-- portal.sp_list_studies
-- Portal Project Admin list over cfg.study (SoT).
-- Bridges portal.project for archive_profile_key / display_name /
-- Study Control resolve until that UI cuts over.
-- project_path is the materialize convention:
--   /work/projects/{study_id|name}/configs/project_{name}.json
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[sp_list_studies]
    @include_non_published bit = 1
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        s.id AS study_row_id,
        s.name,
        s.version,
        s.status AS cfg_status,
        COALESCE(NULLIF(LTRIM(RTRIM(s.study_id)), N''), s.name) AS study_id,
        CONCAT(
            N'/work/projects/',
            COALESCE(NULLIF(LTRIM(RTRIM(s.study_id)), N''), s.name),
            N'/configs/project_',
            s.name,
            N'.json'
        ) AS project_path,
        COALESCE(p.display_name, s.name) AS display_name,
        p.archive_profile_key,
        CASE
            WHEN s.status = 'published' THEN 'ACTIVE'
            ELSE 'DISABLED'
        END AS status,
        p.project_id,
        p.customer_id,
        s.created_at_utc,
        s.updated_at_utc
    FROM cfg.study AS s
    LEFT JOIN portal.project AS p
        ON p.project_path = CONCAT(
            N'/work/projects/',
            COALESCE(NULLIF(LTRIM(RTRIM(s.study_id)), N''), s.name),
            N'/configs/project_',
            s.name,
            N'.json'
        )
    WHERE (@include_non_published = 1 OR s.status = 'published')
    ORDER BY COALESCE(p.display_name, s.name), s.name, s.version;
END
GO

-- ============================================================
-- portal.sp_list_worker_health
-- Registered workers + last_seen + active lease counts.
-- @stale_after_seconds: when set, flags is_stale when last_seen older
--                       than that many seconds (operator-chosen).
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[sp_list_worker_health]
    @stale_after_seconds int = NULL,
    @include_revoked     bit = 0
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @now datetime2(7) = SYSUTCDATETIME();

    SELECT
        c.cluster_key,
        w.id                           AS worker_id,
        w.external_worker_key,
        w.display_name,
        w.hostname,
        w.status,
        COALESCE(w.desired_state, N'ACTIVE') AS desired_state,
        w.last_seen_at_utc,
        CASE
            WHEN w.last_seen_at_utc IS NULL THEN NULL
            ELSE DATEDIFF(SECOND, w.last_seen_at_utc, @now)
        END                            AS seconds_since_seen,
        CASE
            WHEN @stale_after_seconds IS NULL THEN CAST(0 AS bit)
            WHEN w.last_seen_at_utc IS NULL THEN CAST(1 AS bit)
            WHEN DATEDIFF(SECOND, w.last_seen_at_utc, @now) > @stale_after_seconds
                THEN CAST(1 AS bit)
            ELSE CAST(0 AS bit)
        END                            AS is_stale,
        (
            SELECT COUNT_BIG(1)
            FROM wf.task_lease tl
            WHERE tl.worker_id = w.id
        )                              AS active_leases,
        (
            SELECT COUNT_BIG(1)
            FROM wf.task_lease tl
            WHERE tl.worker_id = w.id
              AND tl.lease_expires_at_utc < @now
        )                              AS expired_leases
    FROM wf.worker w
    INNER JOIN wf.cluster c ON c.id = w.cluster_id
    WHERE @include_revoked = 1 OR w.status <> N'REVOKED'
    ORDER BY
        CASE WHEN w.status = N'REGISTERED' THEN 0 ELSE 1 END,
        c.cluster_key,
        w.external_worker_key;
END
GO

-- ============================================================
-- portal.sp_list_workflow_defs
-- Lists workflow definitions with their most-recent active version, for the
-- workflow node-config authoring UI.
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[sp_list_workflow_defs]
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        d.id                                   AS workflow_def_id,
        d.name,
        d.source,
        v.id                                   AS active_version_id,
        v.version_major,
        v.version_minor
    FROM wf.workflow_def d
    OUTER APPLY (
        SELECT TOP (1) vv.id, vv.version_major, vv.version_minor
        FROM wf.workflow_version vv
        WHERE vv.workflow_def_id = d.id AND vv.is_active = 1
        ORDER BY vv.version_major DESC, vv.version_minor DESC
    ) v
    ORDER BY d.name;
END
GO

CREATE OR ALTER PROCEDURE [portal].[sp_list_workflow_nodes]
    @workflow_version_id bigint
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        n.id                                                                       AS workflow_node_id,
        n.node_key,
        n.node_type,
        a.action_name,
        a.input_type_id,
        tin.name                                                                   AS input_type_name,
        CAST(CASE WHEN t.workflow_node_id IS NOT NULL THEN 1 ELSE 0 END AS bit)     AS has_template,
        CAST(CASE
                 WHEN a.input_type_id IS NOT NULL OR si.workflow_action_id IS NOT NULL
                 THEN 1 ELSE 0
             END AS bit)                                                           AS has_input_schema
    FROM wf.workflow_node n
    LEFT JOIN wf.workflow_action a
           ON a.id = n.workflow_action_id
    LEFT JOIN wf.data_type tin
           ON tin.id = a.input_type_id
    LEFT JOIN wf.workflow_input_template t
           ON t.workflow_node_id = n.id
    LEFT JOIN wf.workflow_action_schema si
           ON si.workflow_action_id = a.id AND si.direction = N'input'
    WHERE n.workflow_version_id = @workflow_version_id
    ORDER BY n.id;
END
GO

-- ============================================================
-- portal.sp_list_workflow_versions
-- Lists the versions of a workflow definition (newest first).
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[sp_list_workflow_versions]
    @workflow_def_id bigint
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        v.id                AS workflow_version_id,
        v.version_major,
        v.version_minor,
        v.is_active,
        v.root_node_id
    FROM wf.workflow_version v
    WHERE v.workflow_def_id = @workflow_def_id
    ORDER BY v.version_major DESC, v.version_minor DESC;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_project_get
    @project_id   int          = NULL,
    @customer_id  int          = NULL,
    @project_key  nvarchar(64) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF @project_id IS NULL
       AND (NULLIF(LTRIM(RTRIM(@project_key)), N'') IS NULL OR @customer_id IS NULL)
    BEGIN
        RAISERROR('Provide @project_id or (@customer_id + @project_key).', 16, 1);
        RETURN;
    END;

    SELECT
        p.project_id,
        p.customer_id,
        p.project_key,
        p.display_name,
        p.project_path,
        p.archive_profile_key,
        p.status,
        p.created_at_utc,
        p.updated_at_utc
    FROM portal.project p
    WHERE (@project_id IS NOT NULL AND p.project_id = @project_id)
       OR (
            @project_id IS NULL
            AND p.customer_id = @customer_id
            AND p.project_key = @project_key
          );
END
GO

CREATE OR ALTER PROCEDURE portal.sp_project_list
    @customer_id      int,
    @include_disabled bit = 0
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        p.project_id,
        p.customer_id,
        p.project_key,
        p.display_name,
        p.project_path,
        p.archive_profile_key,
        p.status,
        p.created_at_utc,
        p.updated_at_utc
    FROM portal.project p
    WHERE p.customer_id = @customer_id
      AND (@include_disabled = 1 OR p.status = 'ACTIVE')
    ORDER BY p.display_name, p.project_key;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_project_resolve_archive
    @project_id   int          = NULL,
    @customer_id  int          = NULL,
    @project_key  nvarchar(64) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF @project_id IS NULL
       AND (NULLIF(LTRIM(RTRIM(@project_key)), N'') IS NULL OR @customer_id IS NULL)
    BEGIN
        RAISERROR('Provide @project_id or (@customer_id + @project_key).', 16, 1);
        RETURN;
    END;

    SELECT
        p.project_id,
        p.customer_id,
        p.project_key,
        p.display_name,
        p.project_path,
        p.archive_profile_key,
        p.status,
        rp.profile_json AS sample_storage_json
    FROM portal.project p
    INNER JOIN portal.resource_profile rp
        ON rp.profile_key = p.archive_profile_key
    WHERE rp.status = 'ACTIVE'
      AND p.status = 'ACTIVE'
      AND (
            (@project_id IS NOT NULL AND p.project_id = @project_id)
         OR (
              @project_id IS NULL
              AND p.customer_id = @customer_id
              AND p.project_key = @project_key
            )
          );
END
GO

CREATE OR ALTER PROCEDURE portal.sp_project_save
    @project_id           int           = NULL,
    @customer_id          int,
    @project_key          nvarchar(64),
    @display_name         nvarchar(128),
    @project_path         nvarchar(512),
    @archive_profile_key  nvarchar(64),
    @status               varchar(32)   = 'ACTIVE'
AS
BEGIN
    SET NOCOUNT ON;

    SET @project_key         = NULLIF(LTRIM(RTRIM(@project_key)), N'');
    SET @display_name        = NULLIF(LTRIM(RTRIM(@display_name)), N'');
    SET @project_path        = NULLIF(LTRIM(RTRIM(@project_path)), N'');
    SET @archive_profile_key = NULLIF(LTRIM(RTRIM(@archive_profile_key)), N'');
    SET @status              = NULLIF(LTRIM(RTRIM(@status)), '');

    IF @customer_id IS NULL OR @customer_id <= 0
    BEGIN
        RAISERROR('customer_id is required.', 16, 1);
        RETURN;
    END;

    IF @project_key IS NULL
    BEGIN
        RAISERROR('project_key is required.', 16, 1);
        RETURN;
    END;

    IF @display_name IS NULL
    BEGIN
        RAISERROR('display_name is required.', 16, 1);
        RETURN;
    END;

    IF @project_path IS NULL
    BEGIN
        RAISERROR('project_path is required.', 16, 1);
        RETURN;
    END;

    IF @archive_profile_key IS NULL
    BEGIN
        RAISERROR('archive_profile_key is required.', 16, 1);
        RETURN;
    END;

    IF @status IS NULL OR @status NOT IN ('ACTIVE', 'DISABLED')
    BEGIN
        RAISERROR('status must be ACTIVE or DISABLED.', 16, 1);
        RETURN;
    END;

    IF NOT EXISTS (SELECT 1 FROM portal.Customers WHERE ID = @customer_id)
    BEGIN
        RAISERROR('customer_id %d does not exist.', 16, 1, @customer_id);
        RETURN;
    END;

    IF NOT EXISTS (
        SELECT 1 FROM portal.resource_profile
        WHERE profile_key = @archive_profile_key
    )
    BEGIN
        RAISERROR('archive_profile_key "%s" does not exist.', 16, 1, @archive_profile_key);
        RETURN;
    END;

    IF EXISTS (
        SELECT 1 FROM portal.project
        WHERE customer_id = @customer_id
          AND project_key = @project_key
          AND project_id <> ISNULL(@project_id, 0)
    )
    BEGIN
        RAISERROR('project_key "%s" already exists for this customer.', 16, 1, @project_key);
        RETURN;
    END;

    IF @project_id IS NULL OR @project_id = 0
    BEGIN
        INSERT INTO portal.project (
            customer_id,
            project_key,
            display_name,
            project_path,
            archive_profile_key,
            status
        )
        VALUES (
            @customer_id,
            @project_key,
            @display_name,
            @project_path,
            @archive_profile_key,
            @status
        );
        SET @project_id = SCOPE_IDENTITY();
    END
    ELSE
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM portal.project WHERE project_id = @project_id)
        BEGIN
            RAISERROR('project_id %d does not exist.', 16, 1, @project_id);
            RETURN;
        END;

        UPDATE portal.project
        SET customer_id         = @customer_id,
            project_key         = @project_key,
            display_name        = @display_name,
            project_path        = @project_path,
            archive_profile_key = @archive_profile_key,
            status              = @status,
            updated_at_utc      = SYSUTCDATETIME()
        WHERE project_id = @project_id;
    END;

    SELECT @project_id AS project_id;
END
GO

-- Platform -> Domain programs: publish a domain_program version (status only).
-- Linking to wf.workflow_version remains cfg.cfg_repo_set_compiled_version /
-- methyl-cfg publish-program (not this thin wrapper).
CREATE OR ALTER PROCEDURE [portal].[sp_publish_domain_program]
    @name    nvarchar(256),
    @version nvarchar(64)
AS
BEGIN
    SET NOCOUNT ON;
    EXEC cfg.cfg_repo_publish
        @kind    = N'domain_program',
        @name    = @name,
        @version = @version;
END
GO

-- Platform -> Site: publish a site version.
CREATE OR ALTER PROCEDURE [portal].[sp_publish_site]
    @name    nvarchar(256),
    @version nvarchar(64)
AS
BEGIN
    SET NOCOUNT ON;
    EXEC cfg.cfg_repo_publish
        @kind    = N'site',
        @name    = @name,
        @version = @version;
END
GO

-- ============================================================
-- portal.sp_resolve_active_workflow_version
-- Resolve the active workflow_version_id for a deployed workflow by name
-- (e.g. SamplePrepPipeline, StudyValidationLifecycle).
-- ============================================================
CREATE OR ALTER PROCEDURE [portal].[sp_resolve_active_workflow_version]
    @workflow_name nvarchar(200)
AS
BEGIN
    SET NOCOUNT ON;

    IF @workflow_name IS NULL OR LTRIM(RTRIM(@workflow_name)) = N''
        THROW 50030, N'@workflow_name is required.', 1;

    DECLARE @def_id     bigint;
    DECLARE @version_id bigint;
    DECLARE @major      int;
    DECLARE @minor      int;
    DECLARE @msg        nvarchar(400);

    SELECT TOP (1)
        @def_id     = d.id,
        @version_id = v.id,
        @major      = v.version_major,
        @minor      = v.version_minor
    FROM wf.workflow_def d
    INNER JOIN wf.workflow_version v
        ON v.workflow_def_id = d.id
       AND v.is_active = 1
    WHERE d.name = @workflow_name
    ORDER BY v.version_major DESC, v.version_minor DESC;

    IF @version_id IS NULL
    BEGIN
        SET @msg = N'No active workflow version for name: ' + @workflow_name;
        THROW 50031, @msg, 1;
    END

    SELECT
        @def_id     AS workflow_def_id,
        @version_id AS workflow_version_id,
        @workflow_name AS workflow_name,
        @major      AS version_major,
        @minor      AS version_minor;
END
GO

-- ============================================================
-- portal.sp_resolve_study_archive
-- Resolve cfg.study (+ portal.project bridge) into projectPath +
-- sampleStorage JSON from cfg.storage_profile (phase B).
-- document_json is the wire-format sampleStorage for migrated profiles.
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[sp_resolve_study_archive]
    @study_row_id bigint
AS
BEGIN
    SET NOCOUNT ON;

    IF @study_row_id IS NULL OR @study_row_id <= 0
    BEGIN
        RAISERROR('study_row_id is required.', 16, 1);
        RETURN;
    END;

    SELECT
        s.id AS study_row_id,
        p.project_id,
        p.customer_id,
        s.name,
        COALESCE(NULLIF(LTRIM(RTRIM(s.study_id)), N''), s.name) AS study_id,
        CONCAT(
            N'/work/projects/',
            COALESCE(NULLIF(LTRIM(RTRIM(s.study_id)), N''), s.name),
            N'/configs/project_',
            s.name,
            N'.json'
        ) AS project_path,
        COALESCE(p.display_name, s.name) AS display_name,
        p.archive_profile_key,
        sp.id AS storage_profile_row_id,
        s.name AS project_key,
        CASE
            WHEN s.status = 'published' THEN 'ACTIVE'
            ELSE 'DISABLED'
        END AS status,
        CONVERT(nvarchar(max), sp.document_json) AS sample_storage_json,
        -- Study process defaults (Study Control context bake).
        COALESCE(
            an.name,
            NULLIF(LTRIM(RTRIM(JSON_VALUE(s.document_json, '$.regulatory.primary_analyte'))), N'')
        ) AS primary_analyte,
        COALESCE(
            pp.name,
            NULLIF(LTRIM(RTRIM(JSON_VALUE(s.document_json, '$.pipelineProfile'))), N'')
        ) AS pipeline_profile
    FROM cfg.study AS s
    INNER JOIN portal.project AS p
        ON p.project_path = CONCAT(
            N'/work/projects/',
            COALESCE(NULLIF(LTRIM(RTRIM(s.study_id)), N''), s.name),
            N'/configs/project_',
            s.name,
            N'.json'
        )
    INNER JOIN cfg.storage_profile AS sp
        ON sp.name = p.archive_profile_key
       AND sp.status = 'published'
    LEFT JOIN cfg.analyte AS an ON an.id = s.default_analyte_id
    LEFT JOIN cfg.pipeline_profile AS pp ON pp.id = s.default_pipeline_profile_id
    WHERE s.id = @study_row_id
      AND s.status = 'published'
      AND p.status = 'ACTIVE';
END
GO

-- ============================================================
-- portal.sp_save_node_template
-- Upserts a node's input template. Validation is lenient: the payload only has
-- to be well-formed JSON (ISJSON) -- placeholder tokens like ${var} are allowed
-- and schema/enum conformance is NOT enforced here (that is a design decision;
-- runtime resolution + the action schema handle semantics later).
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[sp_save_node_template]
    @workflow_node_id bigint,
    @template_json    nvarchar(max)
AS
BEGIN
    SET NOCOUNT ON;

    IF @template_json IS NULL OR LTRIM(RTRIM(@template_json)) = N''
        SET @template_json = N'{}';

    IF ISJSON(@template_json) = 0
    BEGIN
        RAISERROR('template_json is not valid JSON.', 16, 1);
        RETURN;
    END;

    IF NOT EXISTS (SELECT 1 FROM wf.workflow_node WHERE id = @workflow_node_id)
    BEGIN
        RAISERROR('workflow_node not found.', 16, 1);
        RETURN;
    END;

    IF EXISTS (SELECT 1 FROM wf.workflow_input_template WHERE workflow_node_id = @workflow_node_id)
        UPDATE wf.workflow_input_template
        SET template_json = @template_json
        WHERE workflow_node_id = @workflow_node_id;
    ELSE
        INSERT INTO wf.workflow_input_template (workflow_node_id, template_json)
        VALUES (@workflow_node_id, @template_json);
END
GO

-- ============================================================
-- portal.sp_save_workflow_graph
-- Write path for the Workflow Designer. Persists a full graph @spec as either:
--   * a NEW workflow_def + version (when $.workflow_def_id is absent), or
--   * a NEW version of an EXISTING def (when $.workflow_def_id is present) --
--     the designer's "save as new version" flow.
--
-- @spec shape matches wf.wf_repo_create_workflow_graph: name, description,
-- root_node_key, version_major/minor, is_active, nodes[], edges[],
-- input_bindings[], output_bindings[], scope_defaults[], collection_bindings[].
-- Each node references its action via $.action_name.
--
-- Result set: (workflow_def_id, workflow_version_id, root_node_id, name).
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[sp_save_workflow_graph]
    @spec nvarchar(max)
AS
BEGIN
    SET NOCOUNT ON;

    IF ISJSON(@spec) <> 1
        THROW 50021, N'@spec is not valid JSON.', 1;

    -- Validate every referenced action exists (reads $.action_name, matching the
    -- repo proc). Fails fast with a clear message before any insert.
    IF EXISTS (
        SELECT 1
        FROM OPENJSON(@spec, '$.nodes')
        WITH (action_name nvarchar(256) '$.action_name') j
        WHERE j.action_name IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM wf.workflow_action a WHERE a.action_name = j.action_name)
    )
        THROW 50020, N'Unknown action_name in workflow graph', 1;

    DECLARE @def_id bigint = TRY_CAST(JSON_VALUE(@spec, '$.workflow_def_id') AS bigint);
    DECLARE @spec_json json = CAST(@spec AS json);

    DECLARE @result TABLE (
        workflow_def_id bigint,
        workflow_version_id bigint,
        root_node_id bigint,
        name nvarchar(256)
    );

    IF @def_id IS NULL
    BEGIN
        -- Brand-new workflow: create def + first version.
        INSERT INTO @result
        EXEC wf.wf_repo_create_workflow_graph @spec = @spec_json;

        UPDATE wf.workflow_def
        SET source = N'portal'
        WHERE id = (SELECT TOP 1 workflow_def_id FROM @result);
    END
    ELSE
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM wf.workflow_def WHERE id = @def_id)
            THROW 50022, N'workflow_def_id not found.', 1;

        -- Existing workflow: append a new version to the same def.
        INSERT INTO @result
        EXEC wf.wf_repo_add_workflow_version @def_id = @def_id, @spec = @spec_json;
    END

    SELECT * FROM @result;
END
GO

-- Platform -> Site: upsert cfg.site via cfg.cfg_repo_upsert.
CREATE OR ALTER PROCEDURE [portal].[sp_upsert_site]
    @name          nvarchar(256),
    @version       nvarchar(64),
    @status        varchar(32) = 'draft',
    @document_json json
AS
BEGIN
    SET NOCOUNT ON;
    EXEC cfg.cfg_repo_upsert
        @kind          = N'site',
        @name          = @name,
        @version       = @version,
        @status        = @status,
        @document_json = @document_json;
END
GO

-- ============================================================
-- portal.sp_upsert_study
-- Upsert cfg.study (SoT) and sync portal.project bridge so
-- Study Control (sp_project_list / resolve_archive) keeps working.
--
-- UI status ACTIVE/DISABLED maps to cfg published/draft.
-- project_path is derived:
--   /work/projects/{study_id}/configs/project_{name}.json
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[sp_upsert_study]
    @study_row_id         bigint         = NULL,
    @name                 nvarchar(256),
    @study_id             nvarchar(256)  = NULL,
    @version              nvarchar(64)   = N'1',
    @display_name         nvarchar(128),
    @archive_profile_key  nvarchar(64),
    @status               varchar(32)    = 'ACTIVE',  -- ACTIVE|DISABLED (UI)
    @customer_id          int            = 1,
    @document_json        json           = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @cfg_status   varchar(32);
    DECLARE @folder       nvarchar(256);
    DECLARE @path         nvarchar(512);
    DECLARE @doc          json;
    DECLARE @existing     json;
    DECLARE @project_id   int;
    DECLARE @out_id       bigint;
    DECLARE @row_name     nvarchar(256);
    DECLARE @row_version  nvarchar(64);

    SET @name                = NULLIF(LTRIM(RTRIM(@name)), N'');
    SET @study_id            = NULLIF(LTRIM(RTRIM(@study_id)), N'');
    SET @version             = COALESCE(NULLIF(LTRIM(RTRIM(@version)), N''), N'1');
    SET @display_name        = NULLIF(LTRIM(RTRIM(@display_name)), N'');
    SET @archive_profile_key = NULLIF(LTRIM(RTRIM(@archive_profile_key)), N'');
    SET @status              = NULLIF(LTRIM(RTRIM(@status)), '');

    IF @name IS NULL
    BEGIN
        RAISERROR('name (study key / project_*.json stem) is required.', 16, 1);
        RETURN;
    END;

    IF @display_name IS NULL
    BEGIN
        RAISERROR('display_name is required.', 16, 1);
        RETURN;
    END;

    IF @archive_profile_key IS NULL
    BEGIN
        RAISERROR('archive_profile_key is required.', 16, 1);
        RETURN;
    END;

    IF @status IS NULL OR @status NOT IN ('ACTIVE', 'DISABLED')
    BEGIN
        RAISERROR('status must be ACTIVE or DISABLED.', 16, 1);
        RETURN;
    END;

    IF @customer_id IS NULL OR @customer_id <= 0
    BEGIN
        RAISERROR('customer_id is required.', 16, 1);
        RETURN;
    END;

    IF NOT EXISTS (SELECT 1 FROM portal.Customers WHERE ID = @customer_id)
    BEGIN
        RAISERROR('customer_id %d does not exist.', 16, 1, @customer_id);
        RETURN;
    END;

    IF NOT EXISTS (
        SELECT 1 FROM cfg.storage_profile
        WHERE name = @archive_profile_key
          AND status = 'published'
    )
    BEGIN
        RAISERROR('storage profile "%s" is missing or not published in cfg.storage_profile.', 16, 1, @archive_profile_key);
        RETURN;
    END;

    -- Keep portal.resource_profile mirror so portal.project FK stays valid.
    MERGE portal.resource_profile AS t
    USING (
        SELECT
            sp.name AS profile_key,
            CONVERT(nvarchar(max), sp.document_json) AS profile_json
        FROM cfg.storage_profile AS sp
        WHERE sp.name = @archive_profile_key
          AND sp.status = 'published'
    ) AS s
    ON t.profile_key = s.profile_key
    WHEN MATCHED THEN UPDATE SET
        profile_json   = s.profile_json,
        status         = 'ACTIVE',
        updated_at_utc = SYSUTCDATETIME()
    WHEN NOT MATCHED THEN INSERT (profile_key, profile_type, profile_json, status)
        VALUES (s.profile_key, N's3_object_storage', s.profile_json, 'ACTIVE');

    SET @cfg_status = CASE WHEN @status = 'ACTIVE' THEN 'published' ELSE 'draft' END;

    IF @study_row_id IS NOT NULL AND @study_row_id > 0
    BEGIN
        SELECT
            @row_name    = name,
            @row_version = version,
            @existing    = document_json,
            @folder      = COALESCE(@study_id, NULLIF(LTRIM(RTRIM(study_id)), N''), name)
        FROM cfg.study
        WHERE id = @study_row_id;

        IF @row_name IS NULL
        BEGIN
            RAISERROR('study_row_id does not exist.', 16, 1);
            RETURN;
        END;

        -- Identity is fixed by row id; rename is not supported in this SP.
        SET @name    = @row_name;
        SET @version = @row_version;
    END
    ELSE
    BEGIN
        SET @folder = COALESCE(@study_id, @name);

        SELECT @existing = document_json
        FROM cfg.study
        WHERE name = @name AND version = @version;
    END;

    SET @path = CONCAT(N'/work/projects/', @folder, N'/configs/project_', @name, N'.json');

    IF @document_json IS NOT NULL
        SET @doc = @document_json;
    ELSE IF @existing IS NOT NULL
        SET @doc = @existing;
    ELSE
        SET @doc = CAST(
            N'{"project_name":"' + REPLACE(@name, N'"', N'') +
            N'","output_base":"/work/projects/' + REPLACE(@folder, N'"', N'') +
            N'","samples_base_path":"/work/samples",' +
            N'"controls":{"label":"control","groups":[]},' +
            N'"diseases":{"label":"disease","groups":[]}}'
            AS json
        );

    DECLARE @hash nvarchar(128) = CONVERT(
        nvarchar(128),
        HASHBYTES('SHA2_256', CONVERT(nvarchar(max), @doc)),
        2
    );

    -- Inline merge (avoid cfg_repo_upsert extra result set confusing UniDAC).
    MERGE cfg.study AS t
    USING (SELECT @name AS name, @version AS version) AS s
    ON t.name = s.name AND t.version = s.version
    WHEN MATCHED THEN UPDATE SET
        status         = @cfg_status,
        content_hash   = @hash,
        document_json  = @doc,
        study_id       = @folder,
        updated_at_utc = SYSUTCDATETIME()
    WHEN NOT MATCHED THEN INSERT (name, version, status, content_hash, document_json, study_id)
        VALUES (@name, @version, @cfg_status, @hash, @doc, @folder);

    SELECT @out_id = id
    FROM cfg.study
    WHERE name = @name AND version = @version;

    SELECT @project_id = project_id
    FROM portal.project
    WHERE project_path = @path
       OR (customer_id = @customer_id AND project_key = @name);

    IF @project_id IS NULL
    BEGIN
        INSERT INTO portal.project (
            customer_id,
            project_key,
            display_name,
            project_path,
            archive_profile_key,
            status
        )
        VALUES (
            @customer_id,
            @name,
            @display_name,
            @path,
            @archive_profile_key,
            @status
        );
        SET @project_id = SCOPE_IDENTITY();
    END
    ELSE
    BEGIN
        UPDATE portal.project
        SET customer_id         = @customer_id,
            project_key         = @name,
            display_name        = @display_name,
            project_path        = @path,
            archive_profile_key = @archive_profile_key,
            status              = @status,
            updated_at_utc      = SYSUTCDATETIME()
        WHERE project_id = @project_id;
    END;

    SELECT
        @out_id     AS study_row_id,
        @project_id AS project_id,
        @name       AS name,
        @folder     AS study_id,
        @path       AS project_path,
        @cfg_status AS cfg_status,
        @status     AS status;
END
GO

-- ============================================================
-- portal.spCollectionDelete
-- Deletes a Meta.Collections row. Blocked when the collection is still
-- referenced by an active DiseaseFieldContract field, or when it still has
-- items (empty it first) to avoid orphaning data.
--
-- Usage from DataModule:
--   qry.SQL.Text := 'EXEC portal.spCollectionDelete :ID';
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[spCollectionDelete]
    @ID int
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @Name varchar(200) = (SELECT Name FROM Meta.Collections WHERE ID = @ID);

    IF @Name IS NULL
    BEGIN
        RAISERROR('Collection not found.', 16, 1);
        RETURN;
    END;

    IF EXISTS (SELECT 1 FROM portal.DiseaseFieldContract
               WHERE CollectionName = @Name AND IsActive = 1)
    BEGIN
        RAISERROR('Collection "%s" is referenced by an active field contract and cannot be deleted.', 16, 1, @Name);
        RETURN;
    END;

    IF EXISTS (SELECT 1 FROM Meta.CollectionItem WHERE CollectionID = @ID)
    BEGIN
        RAISERROR('Collection "%s" still has items; remove them before deleting.', 16, 1, @Name);
        RETURN;
    END;

    DELETE FROM Meta.Collections WHERE ID = @ID;

    SELECT @@ROWCOUNT AS Affected;
END
GO

-- ============================================================
-- portal.spCollectionItemDelete
-- Deletes a Meta.CollectionItem. Its attribute rows in
-- Meta.CollectionItemValue are removed via FK ON DELETE CASCADE.
--
-- Usage from DataModule:
--   qry.SQL.Text := 'EXEC portal.spCollectionItemDelete :ID';
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[spCollectionItemDelete]
    @ID int
AS
BEGIN
    SET NOCOUNT ON;

    DELETE FROM Meta.CollectionItem WHERE ID = @ID;

    SELECT @@ROWCOUNT AS Affected;
END
GO

-- ============================================================
-- portal.spCollectionItemList
-- Lists the items of a collection for the Admin editor, pivoting the canonical
-- attributes (code / reportedValue / aliases) the Sample Import wizard consumes.
-- Label is the item's ValueString.
--
-- Usage from DataModule:
--   qry.SQL.Text := 'EXEC portal.spCollectionItemList :CollectionID';
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[spCollectionItemList]
    @CollectionID int
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        ci.ID,
        ci.Idx,
        ci.ValueString AS Label,
        MAX(CASE WHEN civ.Name = 'code'          THEN civ.ValueString END) AS Code,
        MAX(CASE WHEN civ.Name = 'reportedValue' THEN civ.ValueString END) AS ReportedValue,
        MAX(CASE WHEN civ.Name = 'aliases'       THEN civ.ValueString END) AS Aliases
    FROM Meta.CollectionItem ci
    LEFT JOIN Meta.CollectionItemValue civ
        ON civ.CollectionItemID = ci.ID
    WHERE ci.CollectionID = @CollectionID
    GROUP BY ci.ID, ci.Idx, ci.ValueString
    ORDER BY ci.Idx, ci.ValueString;
END
GO

-- ============================================================
-- portal.spCollectionItemSave
-- Inserts (when @ID is NULL/0) or updates a Meta.CollectionItem and upserts its
-- canonical attributes (code / reportedValue / aliases) in Meta.CollectionItemValue.
-- The item value is stored as a string (ValueString = @Label); this editor
-- targets string-valued collections (the ones the Sample Import wizard reads).
-- An empty attribute removes that attribute row.
-- Returns the item ID.
--
-- Usage from DataModule:
--   qry.SQL.Text := 'EXEC portal.spCollectionItemSave :ID, :CollectionID, :Idx, :Label, :Code, :ReportedValue, :Aliases';
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[spCollectionItemSave]
    @ID            int          = NULL,
    @CollectionID  int,
    @Idx           int          = NULL,
    @Label         varchar(64),
    @Code          varchar(400) = NULL,
    @ReportedValue varchar(400) = NULL,
    @Aliases       varchar(400) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF NULLIF(LTRIM(RTRIM(@Label)), '') IS NULL
    BEGIN
        RAISERROR('Item Label (ValueString) is required.', 16, 1);
        RETURN;
    END;

    IF @ID IS NULL OR @ID = 0
    BEGIN
        INSERT INTO Meta.CollectionItem (CollectionID, Idx, ValueString)
        VALUES (@CollectionID, @Idx, @Label);
        SET @ID = SCOPE_IDENTITY();
    END
    ELSE
    BEGIN
        UPDATE Meta.CollectionItem
        SET Idx         = @Idx,
            ValueString = @Label,
            ValueNumber = NULL,
            ValueObjectID = NULL
        WHERE ID = @ID;
    END;

    -- Upsert / clear the canonical attributes.
    DECLARE @attrs TABLE (Name varchar(64), Val varchar(400));
    INSERT INTO @attrs (Name, Val) VALUES
        ('code', @Code), ('reportedValue', @ReportedValue), ('aliases', @Aliases);

    DELETE civ
    FROM Meta.CollectionItemValue civ
    INNER JOIN @attrs a ON a.Name = civ.Name
    WHERE civ.CollectionItemID = @ID
      AND (a.Val IS NULL OR LTRIM(RTRIM(a.Val)) = '');

    MERGE Meta.CollectionItemValue AS t
    USING (SELECT Name, Val FROM @attrs WHERE Val IS NOT NULL AND LTRIM(RTRIM(Val)) <> '') AS s
        ON t.CollectionItemID = @ID AND t.Name = s.Name
    WHEN MATCHED THEN
        UPDATE SET ValueType = 'S', ValueString = s.Val,
                   ValueNumber = NULL, ValueDate = NULL, ValueBit = NULL
    WHEN NOT MATCHED THEN
        INSERT (CollectionItemID, Name, ValueType, ValueString)
        VALUES (@ID, s.Name, 'S', s.Val);

    SELECT @ID AS ID;
END
GO

-- ============================================================
-- portal.spCollectionList
-- Lists Meta.Collections for the Admin editor, with the item count.
--
-- Usage from DataModule:
--   qry.SQL.Text := 'EXEC portal.spCollectionList';
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[spCollectionList]
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        c.ID,
        c.Name,
        c.Type,
        c.ItemClassID,
        c.ValueType,
        (SELECT COUNT(*) FROM Meta.CollectionItem ci WHERE ci.CollectionID = c.ID) AS ItemCount
    FROM Meta.Collections c
    ORDER BY c.Name;
END
GO

-- ============================================================
-- portal.spCollectionSave
-- Inserts (when @ID is NULL/0) or updates a Meta.Collections row for the Admin
-- editor. Name must be unique (the Sample Import contract references collections
-- by Name). Type and ValueType domains are enforced by the table CHECKs; the UI
-- should feed them via combos.
--   Type      : 'T' (table) | 'L' (list) | 'S' (set)
--   ValueType : 'O' (object) | 'N' (number) | 'S' (string)
-- Returns the row ID.
--
-- Usage from DataModule:
--   qry.SQL.Text := 'EXEC portal.spCollectionSave :ID, :Name, :Type, :ValueType, :ItemClassID';
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[spCollectionSave]
    @ID          int          = NULL,
    @Name        varchar(200),
    @Type        char(1)      = 'L',
    @ValueType   char(1)      = 'S',
    @ItemClassID int          = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF NULLIF(LTRIM(RTRIM(@Name)), '') IS NULL
    BEGIN
        RAISERROR('Collection Name is required.', 16, 1);
        RETURN;
    END;

    IF EXISTS (SELECT 1 FROM Meta.Collections
               WHERE Name = @Name AND ID <> ISNULL(@ID, 0))
    BEGIN
        RAISERROR('A collection named "%s" already exists.', 16, 1, @Name);
        RETURN;
    END;

    IF @ID IS NULL OR @ID = 0
    BEGIN
        INSERT INTO Meta.Collections (Name, Type, ItemClassID, ValueType)
        VALUES (@Name, @Type, @ItemClassID, @ValueType);
        SET @ID = SCOPE_IDENTITY();
    END
    ELSE
    BEGIN
        UPDATE Meta.Collections
        SET Name        = @Name,
            Type        = @Type,
            ItemClassID = @ItemClassID,
            ValueType   = @ValueType
        WHERE ID = @ID;
    END;

    SELECT @ID AS ID;
END
GO

-- ============================================================
-- portal.spDiseaseFieldContractDelete
-- Soft-deletes a field contract row (IsActive = 0). Soft delete preserves
-- history and frees the FieldName from the filtered unique index so it can be
-- re-created later. Returns the affected row count.
--
-- Usage from DataModule:
--   qry.SQL.Text := 'EXEC portal.spDiseaseFieldContractDelete :ID';
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[spDiseaseFieldContractDelete]
    @ID int
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE portal.DiseaseFieldContract
    SET IsActive  = 0,
        UpdatedAt = SYSDATETIME()
    WHERE ID = @ID
      AND IsActive = 1;

    SELECT @@ROWCOUNT AS Affected;
END
GO

-- ============================================================
-- portal.spDiseaseFieldContractGetTargetColumns
-- INFORMATION_SCHEMA assistance for the Admin editor: lists the columns of the
-- physical table that backs a given TargetEntity, with a suggested contract
-- DataType for each. The table is resolved as:
--   PATIENT         -> portal.Patients
--   SAMPLE          -> portal.Samples
--   SAMPLE_SUBTYPE  -> portal.DiseaseDataSource.SubtypeTable (active row of the disease)
--
-- Usage from DataModule:
--   qry.SQL.Text := 'EXEC portal.spDiseaseFieldContractGetTargetColumns :DiseaseID, :TargetEntity';
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[spDiseaseFieldContractGetTargetColumns]
    @DiseaseID    int,
    @TargetEntity varchar(20)
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @FullTable sysname =
        CASE @TargetEntity
            WHEN 'PATIENT' THEN 'portal.Patients'
            WHEN 'SAMPLE'  THEN 'portal.Samples'
            WHEN 'SAMPLE_SUBTYPE' THEN
                (SELECT TOP (1) SubtypeTable FROM portal.DiseaseDataSource
                 WHERE DiseaseID = @DiseaseID AND IsActive = 1)
        END;

    IF @FullTable IS NULL
        RETURN;  -- unknown entity or no active data source: empty result set

    DECLARE @Schema sysname = PARSENAME(@FullTable, 2);
    DECLARE @Table  sysname = PARSENAME(@FullTable, 1);
    IF @Schema IS NULL SET @Schema = 'portal';

    SELECT
        c.COLUMN_NAME                AS ColumnName,
        c.DATA_TYPE                  AS SqlType,
        c.IS_NULLABLE                AS IsNullable,
        c.CHARACTER_MAXIMUM_LENGTH   AS MaxLength,
        CASE
            WHEN c.DATA_TYPE IN ('int','bigint','smallint','tinyint')                THEN 'INT'
            WHEN c.DATA_TYPE IN ('decimal','numeric','float','real','money','smallmoney') THEN 'FLOAT'
            WHEN c.DATA_TYPE = 'bit'                                                  THEN 'BOOL'
            WHEN c.DATA_TYPE IN ('date','datetime','datetime2','smalldatetime','datetimeoffset') THEN 'DATE'
            WHEN c.DATA_TYPE = 'uniqueidentifier'                                     THEN 'GUID'
            ELSE 'STRING'
        END                          AS SuggestedDataType
    FROM INFORMATION_SCHEMA.COLUMNS c
    WHERE c.TABLE_SCHEMA = @Schema
      AND c.TABLE_NAME   = @Table
    ORDER BY c.ORDINAL_POSITION;
END
GO

-- ============================================================
-- portal.spDiseaseFieldContractImportFromTarget
-- Assisted bulk-add for the Admin editor: returns the columns of the physical
-- table backing @TargetEntity that are NOT yet part of the disease's active
-- contract (matched by TargetColumn, falling back to FieldName, within the same
-- TargetEntity), together with a suggested DataType and caption. The UI lets the
-- admin pick which ones to create via spDiseaseFieldContractSave.
--
-- Table resolution is identical to spDiseaseFieldContractGetTargetColumns.
--
-- Usage from DataModule:
--   qry.SQL.Text := 'EXEC portal.spDiseaseFieldContractImportFromTarget :DiseaseID, :TargetEntity';
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[spDiseaseFieldContractImportFromTarget]
    @DiseaseID    int,
    @TargetEntity varchar(20)
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @FullTable sysname =
        CASE @TargetEntity
            WHEN 'PATIENT' THEN 'portal.Patients'
            WHEN 'SAMPLE'  THEN 'portal.Samples'
            WHEN 'SAMPLE_SUBTYPE' THEN
                (SELECT TOP (1) SubtypeTable FROM portal.DiseaseDataSource
                 WHERE DiseaseID = @DiseaseID AND IsActive = 1)
        END;

    IF @FullTable IS NULL
        RETURN;

    DECLARE @Schema sysname = PARSENAME(@FullTable, 2);
    DECLARE @Table  sysname = PARSENAME(@FullTable, 1);
    IF @Schema IS NULL SET @Schema = 'portal';

    SELECT
        c.COLUMN_NAME                AS ColumnName,
        c.COLUMN_NAME                AS SuggestedCaption,
        c.DATA_TYPE                  AS SqlType,
        c.IS_NULLABLE                AS IsNullable,
        CASE
            WHEN c.DATA_TYPE IN ('int','bigint','smallint','tinyint')                THEN 'INT'
            WHEN c.DATA_TYPE IN ('decimal','numeric','float','real','money','smallmoney') THEN 'FLOAT'
            WHEN c.DATA_TYPE = 'bit'                                                  THEN 'BOOL'
            WHEN c.DATA_TYPE IN ('date','datetime','datetime2','smalldatetime','datetimeoffset') THEN 'DATE'
            WHEN c.DATA_TYPE = 'uniqueidentifier'                                     THEN 'GUID'
            ELSE 'STRING'
        END                          AS SuggestedDataType
    FROM INFORMATION_SCHEMA.COLUMNS c
    WHERE c.TABLE_SCHEMA = @Schema
      AND c.TABLE_NAME   = @Table
      AND NOT EXISTS (
            SELECT 1 FROM portal.DiseaseFieldContract f
            WHERE f.DiseaseID    = @DiseaseID
              AND f.IsActive     = 1
              AND f.TargetEntity = @TargetEntity
              AND ISNULL(f.TargetColumn, f.FieldName) = c.COLUMN_NAME)
    ORDER BY c.ORDINAL_POSITION;
END
GO

-- ============================================================
-- portal.spDiseaseFieldContractList
-- Returns the field contract rows for a disease, for the Admin editor.
-- By default only active rows; pass @IncludeInactive = 1 to see soft-deleted
-- ones too.
--
-- Usage from DataModule:
--   qry.SQL.Text := 'EXEC portal.spDiseaseFieldContractList :DiseaseID, :IncludeInactive';
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[spDiseaseFieldContractList]
    @DiseaseID       int,
    @IncludeInactive bit = 0
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        c.ID,
        c.DiseaseID,
        c.FieldName,
        c.FieldCaption,
        c.DataType,
        c.IsBaseField,
        c.DisplayOrder,
        c.ColumnWidth,
        c.IsVisible,
        c.IsFilterable,
        c.FilterOperatorDefault,
        c.FilterEditorKind,
        c.IsSortable,
        c.IsEditable,
        c.IsRequired,
        c.ValidationJson,
        c.LookupQuery,
        c.TargetEntity,
        c.TargetColumn,
        c.CollectionName,
        c.ValueStoreMode,
        c.MergeStrategy,
        c.IsActive,
        c.CreatedAt,
        c.UpdatedAt
    FROM portal.DiseaseFieldContract c
    WHERE c.DiseaseID = @DiseaseID
      AND (@IncludeInactive = 1 OR c.IsActive = 1)
    ORDER BY c.DisplayOrder, c.FieldName;
END
GO

-- ============================================================
-- portal.spDiseaseFieldContractSave
-- Inserts (when @ID is NULL/0) or updates a field contract row for the Admin
-- editor. Validates the cross-field rules the CHECK constraints cannot express:
--   * FieldName must be unique among ACTIVE rows of the disease.
--   * CollectionName (when set) must exist in Meta.Collections.
--   * ValueStoreMode is required when a CollectionName is set.
-- Domain values (DataType, TargetEntity, ValueStoreMode, MergeStrategy,
-- FilterOperatorDefault, FilterEditorKind) are still guarded by the table CHECK
-- constraints; the UI should feed them via combos.
-- Returns the row ID.
--
-- Usage from DataModule:
--   qry.SQL.Text := 'EXEC portal.spDiseaseFieldContractSave :ID, :DiseaseID, ...';
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[spDiseaseFieldContractSave]
    @ID                    int            = NULL,
    @DiseaseID             int,
    @FieldName             sysname,
    @FieldCaption          nvarchar(128),
    @DataType              varchar(20),
    @IsBaseField           bit            = 0,
    @DisplayOrder          int            = 0,
    @ColumnWidth           int            = 120,
    @IsVisible             bit            = 1,
    @IsFilterable          bit            = 1,
    @FilterOperatorDefault varchar(20)    = 'AUTO',
    @FilterEditorKind      varchar(20)    = 'TEXT',
    @IsSortable            bit            = 1,
    @IsEditable            bit            = 0,
    @IsRequired            bit            = 0,
    @ValidationJson        nvarchar(max)  = NULL,
    @LookupQuery           nvarchar(max)  = NULL,
    @TargetEntity          varchar(20)    = 'SAMPLE',
    @TargetColumn          sysname        = NULL,
    @CollectionName        varchar(200)   = NULL,
    @ValueStoreMode        varchar(20)    = NULL,
    @MergeStrategy         varchar(20)    = NULL,
    @IsActive              bit            = 1
AS
BEGIN
    SET NOCOUNT ON;

    -- Normalize blank strings to NULL for the optional columns.
    IF NULLIF(LTRIM(RTRIM(@TargetColumn)),   '') IS NULL SET @TargetColumn   = NULL;
    IF NULLIF(LTRIM(RTRIM(@CollectionName)), '') IS NULL SET @CollectionName = NULL;
    IF NULLIF(LTRIM(RTRIM(@ValueStoreMode)), '') IS NULL SET @ValueStoreMode = NULL;
    IF NULLIF(LTRIM(RTRIM(@MergeStrategy)),  '') IS NULL SET @MergeStrategy  = NULL;

    IF @CollectionName IS NOT NULL
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM Meta.Collections WHERE Name = @CollectionName)
        BEGIN
            RAISERROR('Collection "%s" does not exist in Meta.Collections.', 16, 1, @CollectionName);
            RETURN;
        END;
        IF @ValueStoreMode IS NULL
        BEGIN
            RAISERROR('ValueStoreMode is required when a CollectionName is set.', 16, 1);
            RETURN;
        END;
    END;

    -- Unique FieldName among active rows of this disease (matches the filtered
    -- unique index; checked here to give a friendly error).
    IF @IsActive = 1 AND EXISTS (
        SELECT 1 FROM portal.DiseaseFieldContract
        WHERE DiseaseID = @DiseaseID
          AND FieldName = @FieldName
          AND IsActive = 1
          AND ID <> ISNULL(@ID, 0))
    BEGIN
        RAISERROR('Field "%s" already exists for this disease.', 16, 1, @FieldName);
        RETURN;
    END;

    IF @ID IS NULL OR @ID = 0
    BEGIN
        INSERT INTO portal.DiseaseFieldContract
            (DiseaseID, FieldName, FieldCaption, DataType, IsBaseField, DisplayOrder, ColumnWidth,
             IsVisible, IsFilterable, FilterOperatorDefault, FilterEditorKind, IsSortable, IsEditable, IsRequired,
             ValidationJson, LookupQuery, TargetEntity, TargetColumn, CollectionName, ValueStoreMode, MergeStrategy,
             IsActive)
        VALUES
            (@DiseaseID, @FieldName, @FieldCaption, @DataType, @IsBaseField, @DisplayOrder, @ColumnWidth,
             @IsVisible, @IsFilterable, @FilterOperatorDefault, @FilterEditorKind, @IsSortable, @IsEditable, @IsRequired,
             @ValidationJson, @LookupQuery, @TargetEntity, @TargetColumn, @CollectionName, @ValueStoreMode, @MergeStrategy,
             @IsActive);

        SET @ID = SCOPE_IDENTITY();
    END
    ELSE
    BEGIN
        UPDATE portal.DiseaseFieldContract
        SET DiseaseID             = @DiseaseID,
            FieldName             = @FieldName,
            FieldCaption          = @FieldCaption,
            DataType              = @DataType,
            IsBaseField           = @IsBaseField,
            DisplayOrder          = @DisplayOrder,
            ColumnWidth           = @ColumnWidth,
            IsVisible             = @IsVisible,
            IsFilterable          = @IsFilterable,
            FilterOperatorDefault = @FilterOperatorDefault,
            FilterEditorKind      = @FilterEditorKind,
            IsSortable            = @IsSortable,
            IsEditable            = @IsEditable,
            IsRequired            = @IsRequired,
            ValidationJson        = @ValidationJson,
            LookupQuery           = @LookupQuery,
            TargetEntity          = @TargetEntity,
            TargetColumn          = @TargetColumn,
            CollectionName        = @CollectionName,
            ValueStoreMode        = @ValueStoreMode,
            MergeStrategy         = @MergeStrategy,
            IsActive              = @IsActive,
            UpdatedAt             = SYSDATETIME()
        WHERE ID = @ID;
    END;

    SELECT @ID AS ID;
END
GO

-- ============================================================
-- portal.spGetCollectionItemsForMapping
-- Returns the canonical items of a collection for the value-mapping step of
-- the Sample Import wizard (combo source). Exposes the canonical label, the
-- 'code' and 'reportedValue' attributes, and the alias list so the UI can
-- show what an unresolved raw value should be mapped to.
--
-- Usage from DataModule:
--   qry.SQL.Text := 'EXEC portal.spGetCollectionItemsForMapping :CollectionName';
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[spGetCollectionItemsForMapping]
    @CollectionName varchar(200)
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        ci.ID                                                       AS CollectionItemID,
        ci.Idx,
        ci.ValueString                                              AS Label,
        MAX(CASE WHEN civ.Name = 'code'          THEN civ.ValueString END) AS Code,
        MAX(CASE WHEN civ.Name = 'reportedValue' THEN civ.ValueString END) AS ReportedValue,
        MAX(CASE WHEN civ.Name = 'aliases'       THEN civ.ValueString END) AS Aliases
    FROM Meta.Collections c
    INNER JOIN Meta.CollectionItem ci
        ON ci.CollectionID = c.ID
    LEFT JOIN Meta.CollectionItemValue civ
        ON civ.CollectionItemID = ci.ID
    WHERE c.Name = @CollectionName
    GROUP BY ci.ID, ci.Idx, ci.ValueString
    ORDER BY ci.Idx, ci.ValueString;
END
GO

-- ============================================================
-- portal.spGetImportFieldsForDisease
-- Returns the importable field set for a disease, driven entirely by
-- portal.DiseaseFieldContract (the single source of truth). Consumed by the
-- Sample Import wizard (column mapping + value mapping) and by validation.
--
-- Usage from DataModule:
--   qry.SQL.Text := 'EXEC portal.spGetImportFieldsForDisease :DiseaseID';
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[spGetImportFieldsForDisease]
    @DiseaseID int
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        c.ID                AS FieldContractID,
        c.FieldName,
        c.FieldCaption,
        c.DataType,
        c.IsBaseField,
        c.IsRequired,
        c.DisplayOrder,
        c.TargetEntity,
        ISNULL(c.TargetColumn, c.FieldName) AS TargetColumn,
        c.CollectionName,
        c.ValueStoreMode,
        c.MergeStrategy,
        c.ValidationJson,
        CAST(CASE WHEN c.CollectionName IS NULL THEN 0 ELSE 1 END AS bit) AS IsCollectionBacked
    FROM portal.DiseaseFieldContract c
    WHERE c.DiseaseID = @DiseaseID
      AND c.IsActive = 1
    ORDER BY c.DisplayOrder, c.FieldName;
END
GO

-- ============================================================
-- portal.spSampleImportCommit
-- Transactional, mode-aware commit of a validated Sample Import batch.
--
-- Per VALID row:
--   1) Match the patient by (InstitutionID, ExternalID); create if absent.
--      Existing patient demographics are filled only when empty (Name kept).
--   2) Resolve the sample by natural key (CustomerID, SampleName) and apply
--      @Mode:
--        INSERT  -> insert new, skip existing
--        UPDATE  -> update existing, skip new
--        UPSERT  -> insert new + update existing (default field PREFER_INCOMING)
--        MERGE   -> insert new + update existing (default field FILL_IF_EMPTY)
--      Per-field behaviour is overridden by DiseaseFieldContract.MergeStrategy.
--   3) On insert, always insert the disease subtype row.
--   4) Unmapped columns flagged in MappingJson are stored as Samples.Extras JSON.
--   5) Field-level conflicts are recorded in SampleImportRow.ConflictsJson.
--
-- @Mode is optional; when NULL the batch's stored Mode is used.
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[spSampleImportCommit]
    @BatchID int,
    @Mode    varchar(20) = NULL,
    @ValidOnly bit = 1
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    DECLARE @DiseaseID int, @CustomerID int, @InstitutionID int,
            @MappingJson nvarchar(max), @SubtypeTable sysname;

    SELECT @DiseaseID = DiseaseID, @CustomerID = CustomerID, @InstitutionID = InstitutionID,
           @MappingJson = MappingJson, @Mode = COALESCE(@Mode, [Mode])
    FROM portal.SampleImportBatch WHERE ID = @BatchID;

    IF @DiseaseID IS NULL
    BEGIN
        RAISERROR('Batch %d not found.', 16, 1, @BatchID);
        RETURN;
    END;

    SELECT @SubtypeTable = SubtypeTable
    FROM portal.DiseaseDataSource
    WHERE DiseaseID = @DiseaseID AND IsActive = 1;

    -- ---- Field metadata + generated SQL fragments --------------------------
    -- IncText: the raw incoming text for a field; CastExpr: typed value;
    -- SetFrag: UPDATE assignment honouring the effective merge strategy.
    IF OBJECT_ID('tempdb..#fld') IS NOT NULL DROP TABLE #fld;
    SELECT
        c.FieldName COLLATE DATABASE_DEFAULT AS FieldName,
        c.TargetEntity,
        ISNULL(c.TargetColumn, c.FieldName) AS TargetColumn,
        c.DataType,
        CASE WHEN c.TargetEntity = 'PATIENT' THEN 'FILL_IF_EMPTY'
             ELSE COALESCE(c.MergeStrategy, CASE WHEN @Mode = 'MERGE' THEN 'FILL_IF_EMPTY' ELSE 'PREFER_INCOMING' END)
        END AS EffStrategy,
        x.IncText,
        CASE c.DataType
            WHEN 'INT'   THEN 'TRY_CAST(' + x.IncText + ' AS int)'
            WHEN 'FLOAT' THEN 'TRY_CAST(' + x.IncText + ' AS float)'
            WHEN 'DATE'  THEN 'TRY_CONVERT(date,' + x.IncText + ')'
            WHEN 'GUID'  THEN 'TRY_CAST(' + x.IncText + ' AS uniqueidentifier)'
            WHEN 'BOOL'  THEN 'CASE WHEN LOWER(' + x.IncText + ') IN (''1'',''true'',''yes'') THEN 1 WHEN LOWER(' + x.IncText + ') IN (''0'',''false'',''no'') THEN 0 ELSE NULL END'
            ELSE x.IncText
        END AS CastExpr,
        '(' + x.IncText + ' IS NOT NULL AND LTRIM(RTRIM(' + x.IncText + ')) <> '''')' AS IncNotEmpty,
        CASE WHEN c.DataType IN ('STRING','GUID')
             THEN '([' + ISNULL(c.TargetColumn, c.FieldName) + '] IS NULL OR [' + ISNULL(c.TargetColumn, c.FieldName) + '] = '''')'
             ELSE '([' + ISNULL(c.TargetColumn, c.FieldName) + '] IS NULL)'
        END AS ExistingEmpty
    INTO #fld
    FROM portal.DiseaseFieldContract c
    CROSS APPLY (SELECT 'JSON_VALUE(@cj,''$."' + c.FieldName + '"'')' AS IncText) x
    WHERE c.DiseaseID = @DiseaseID AND c.IsActive = 1;

    -- ---- Build the per-entity dynamic statements (generated once) -----------
    DECLARE @insSampleCols nvarchar(max), @insSampleVals nvarchar(max),
            @insSubCols    nvarchar(max), @insSubVals    nvarchar(max),
            @insPatCols    nvarchar(max), @insPatVals    nvarchar(max),
            @updSampleSet  nvarchar(max), @updSubSet      nvarchar(max),
            @updPatSet     nvarchar(max);

    SELECT @insSampleCols = STRING_AGG('[' + TargetColumn + ']', ', '),
           @insSampleVals = STRING_AGG(CastExpr, ', ')
    FROM #fld WHERE TargetEntity = 'SAMPLE' AND TargetColumn <> 'SampleName';

    SELECT @insSubCols = STRING_AGG('[' + TargetColumn + ']', ', '),
           @insSubVals = STRING_AGG(CastExpr, ', ')
    FROM #fld WHERE TargetEntity = 'SAMPLE_SUBTYPE';

    -- Patient insert: Name (NOT NULL) falls back to ExternalID when empty.
    SELECT @insPatCols = STRING_AGG('[' + TargetColumn + ']', ', '),
           @insPatVals = STRING_AGG(
                CASE WHEN TargetColumn = 'Name'
                     THEN 'ISNULL(NULLIF(' + CastExpr + ','''')' + ', JSON_VALUE(@cj,''$."PatientExternalID"''))'
                     ELSE CastExpr END, ', ')
    FROM #fld WHERE TargetEntity = 'PATIENT';

    SELECT @updSampleSet = STRING_AGG(
        '[' + TargetColumn + '] = ' +
        CASE WHEN EffStrategy = 'PREFER_INCOMING'
             THEN 'CASE WHEN ' + IncNotEmpty + ' THEN ' + CastExpr + ' ELSE [' + TargetColumn + '] END'
             ELSE 'CASE WHEN ' + ExistingEmpty + ' AND ' + IncNotEmpty + ' THEN ' + CastExpr + ' ELSE [' + TargetColumn + '] END'
        END, ', ')
    FROM #fld WHERE TargetEntity = 'SAMPLE' AND TargetColumn <> 'SampleName';

    SELECT @updSubSet = STRING_AGG(
        '[' + TargetColumn + '] = ' +
        CASE WHEN EffStrategy = 'PREFER_INCOMING'
             THEN 'CASE WHEN ' + IncNotEmpty + ' THEN ' + CastExpr + ' ELSE [' + TargetColumn + '] END'
             ELSE 'CASE WHEN ' + ExistingEmpty + ' AND ' + IncNotEmpty + ' THEN ' + CastExpr + ' ELSE [' + TargetColumn + '] END'
        END, ', ')
    FROM #fld WHERE TargetEntity = 'SAMPLE_SUBTYPE';

    -- Patient update: always fill-empty (Name protected by the same rule).
    SELECT @updPatSet = STRING_AGG(
        '[' + TargetColumn + '] = CASE WHEN ' + ExistingEmpty + ' AND ' + IncNotEmpty + ' THEN ' + CastExpr + ' ELSE [' + TargetColumn + '] END', ', ')
    FROM #fld WHERE TargetEntity = 'PATIENT' AND TargetColumn <> 'ExternalID';

    -- Existing-snapshot SELECT (aliases each target column AS FieldName) for
    -- conflict detection; pulls from Samples + subtype + Patients.
    DECLARE @snapCols nvarchar(max);
    SELECT @snapCols = STRING_AGG(
        CASE TargetEntity WHEN 'PATIENT' THEN 'p.[' WHEN 'SAMPLE_SUBTYPE' THEN 'st.[' ELSE 's.[' END
        + TargetColumn + '] AS [' + FieldName + ']', ', ')
    FROM #fld;

    -- Extras column list (unmapped columns flagged for import).
    IF OBJECT_ID('tempdb..#extra') IS NOT NULL DROP TABLE #extra;
    SELECT m.csv
    INTO #extra
    FROM OPENJSON(@MappingJson, '$.columns')
    WITH (csv nvarchar(200) '$.csv', toExtras bit '$.toExtras') m
    WHERE m.toExtras = 1 AND m.csv IS NOT NULL;

    -- Prepared dynamic statements --------------------------------------------
    DECLARE @sqlInsPat nvarchar(max) =
        N'INSERT INTO portal.Patients (InstitutionID' + CASE WHEN @insPatCols IS NULL THEN N'' ELSE N', ' + @insPatCols END + N') ' +
        N'VALUES (@InstitutionID' + CASE WHEN @insPatVals IS NULL THEN N'' ELSE N', ' + @insPatVals END + N'); SET @OutID = SCOPE_IDENTITY();';

    DECLARE @sqlUpdPat nvarchar(max) =
        CASE WHEN @updPatSet IS NULL THEN NULL
             ELSE N'UPDATE portal.Patients SET ' + @updPatSet + N' WHERE ID = @PatientID;' END;

    DECLARE @sqlInsSample nvarchar(max) =
        N'INSERT INTO portal.Samples (PatientID, CustomerID, SampleName, DiseaseID, Extras' +
        CASE WHEN @insSampleCols IS NULL THEN N'' ELSE N', ' + @insSampleCols END + N') ' +
        N'VALUES (@PatientID, @CustomerID, JSON_VALUE(@cj,''$."SampleName"''), @DiseaseID, @Extras' +
        CASE WHEN @insSampleVals IS NULL THEN N'' ELSE N', ' + @insSampleVals END + N'); SET @OutID = SCOPE_IDENTITY();';

    DECLARE @sqlInsSub nvarchar(max) =
        N'INSERT INTO ' + @SubtypeTable + N' (ID' + CASE WHEN @insSubCols IS NULL THEN N'' ELSE N', ' + @insSubCols END + N') ' +
        N'VALUES (@SampleID' + CASE WHEN @insSubVals IS NULL THEN N'' ELSE N', ' + @insSubVals END + N');';

    DECLARE @sqlUpdSample nvarchar(max) =
        CASE WHEN @updSampleSet IS NULL THEN NULL
             ELSE N'UPDATE portal.Samples SET ' + @updSampleSet + N' WHERE ID = @SampleID;' END;

    DECLARE @sqlUpdSub nvarchar(max) =
        CASE WHEN @updSubSet IS NULL THEN NULL
             ELSE N'UPDATE ' + @SubtypeTable + N' SET ' + @updSubSet + N' WHERE ID = @SampleID;' END;

    DECLARE @sqlSnap nvarchar(max) =
        N'SET @OutJson = (SELECT ' + @snapCols + N' FROM portal.Samples s ' +
        N'LEFT JOIN ' + @SubtypeTable + N' st ON st.ID = s.ID ' +
        N'LEFT JOIN portal.Patients p ON p.ID = s.PatientID ' +
        N'WHERE s.ID = @SampleID FOR JSON PATH, WITHOUT_ARRAY_WRAPPER);';

    DECLARE @sqlEnsureSub nvarchar(max) =
        N'IF NOT EXISTS (SELECT 1 FROM ' + @SubtypeTable + N' WHERE ID = @SampleID) ' +
        N'INSERT INTO ' + @SubtypeTable + N' (ID) VALUES (@SampleID);';

    -- ---- Iterate valid rows -------------------------------------------------
    DECLARE @RowID int, @cj nvarchar(max), @raw nvarchar(max),
            @PatientID int, @SampleID int, @Extras nvarchar(max),
            @existJson nvarchar(max), @conflicts nvarchar(max), @action varchar(20),
            @extId nvarchar(64), @participant nvarchar(128);

    DECLARE row_cur CURSOR LOCAL FAST_FORWARD FOR
        SELECT ID, CanonicalJson, RawJson
        FROM portal.SampleImportRow
        WHERE BatchID = @BatchID
          AND (@ValidOnly = 0 OR [Status] = 'VALID');

    BEGIN TRY
        BEGIN TRAN;

        UPDATE portal.SampleImportBatch SET [Status] = 'COMMITTING', UpdatedAt = SYSDATETIME() WHERE ID = @BatchID;

        OPEN row_cur;
        FETCH NEXT FROM row_cur INTO @RowID, @cj, @raw;
        WHILE @@FETCH_STATUS = 0
        BEGIN
            SET @PatientID = NULL; SET @SampleID = NULL; SET @action = NULL;
            SET @conflicts = NULL; SET @existJson = NULL; SET @Extras = NULL;

            SET @extId = JSON_VALUE(@cj, '$."PatientExternalID"');
            SET @participant = JSON_VALUE(@cj, '$."SampleName"');

            -- Build Extras JSON from flagged unmapped columns (no dynamic paths).
            SELECT @Extras = N'{' + ISNULL(STRING_AGG(
                        '"' + STRING_ESCAPE(rj.[key], 'json') + '":' +
                        CASE WHEN rj.[value] IS NULL THEN 'null'
                             ELSE '"' + STRING_ESCAPE(rj.[value], 'json') + '"' END, ',') , '') + N'}'
            FROM OPENJSON(@raw) rj
            INNER JOIN #extra e ON e.csv = rj.[key] COLLATE DATABASE_DEFAULT;
            IF @Extras = N'{}' SET @Extras = NULL;

            -- Patient: match or create.
            SELECT TOP (1) @PatientID = ID FROM portal.Patients
            WHERE InstitutionID = @InstitutionID AND ExternalID = @extId
            ORDER BY ID;

            IF @PatientID IS NULL
            BEGIN
                EXEC sp_executesql @sqlInsPat,
                    N'@cj nvarchar(max), @InstitutionID int, @OutID int OUTPUT',
                    @cj = @cj, @InstitutionID = @InstitutionID, @OutID = @PatientID OUTPUT;
            END
            ELSE IF @sqlUpdPat IS NOT NULL
            BEGIN
                EXEC sp_executesql @sqlUpdPat,
                    N'@cj nvarchar(max), @PatientID int',
                    @cj = @cj, @PatientID = @PatientID;
            END

            -- Sample: resolve by natural key.
            SELECT TOP (1) @SampleID = ID FROM portal.Samples
            WHERE CustomerID = @CustomerID AND SampleName = @participant
            ORDER BY ID;

            IF @SampleID IS NULL
            BEGIN
                -- New sample
                IF @Mode = 'UPDATE'
                BEGIN
                    SET @action = 'SKIPPED';
                END
                ELSE
                BEGIN
                    EXEC sp_executesql @sqlInsSample,
                        N'@cj nvarchar(max), @PatientID int, @CustomerID int, @DiseaseID int, @Extras nvarchar(max), @OutID int OUTPUT',
                        @cj = @cj, @PatientID = @PatientID, @CustomerID = @CustomerID, @DiseaseID = @DiseaseID, @Extras = @Extras, @OutID = @SampleID OUTPUT;

                    EXEC sp_executesql @sqlInsSub,
                        N'@cj nvarchar(max), @SampleID int',
                        @cj = @cj, @SampleID = @SampleID;

                    SET @action = 'INSERTED';
                END
            END
            ELSE
            BEGIN
                -- Existing sample
                IF @Mode = 'INSERT'
                BEGIN
                    SET @action = 'SKIPPED';
                END
                ELSE
                BEGIN
                    -- Snapshot existing values for conflict detection.
                    EXEC sp_executesql @sqlSnap,
                        N'@SampleID int, @OutJson nvarchar(max) OUTPUT',
                        @SampleID = @SampleID, @OutJson = @existJson OUTPUT;

                    SELECT @conflicts = (
                        SELECT f.FieldName AS [field],
                               ev.[value]  AS [existing],
                               iv.[value]  AS [incoming],
                               CASE WHEN f.EffStrategy = 'PREFER_INCOMING' THEN 'overwritten' ELSE 'kept' END AS [action]
                        FROM #fld f
                        INNER JOIN OPENJSON(@existJson) ev ON ev.[key] COLLATE DATABASE_DEFAULT = f.FieldName
                        INNER JOIN OPENJSON(@cj)        iv ON iv.[key] COLLATE DATABASE_DEFAULT = f.FieldName
                        WHERE ev.[value] IS NOT NULL AND LTRIM(RTRIM(ev.[value])) <> ''
                          AND iv.[value] IS NOT NULL AND LTRIM(RTRIM(iv.[value])) <> ''
                          AND UPPER(LTRIM(RTRIM(ev.[value]))) <> UPPER(LTRIM(RTRIM(iv.[value])))
                        FOR JSON PATH);

                    IF @sqlUpdSample IS NOT NULL
                        EXEC sp_executesql @sqlUpdSample,
                            N'@cj nvarchar(max), @SampleID int', @cj = @cj, @SampleID = @SampleID;

                    -- Ensure the subtype row exists, then update it.
                    EXEC sp_executesql @sqlEnsureSub, N'@SampleID int', @SampleID = @SampleID;

                    IF @sqlUpdSub IS NOT NULL
                        EXEC sp_executesql @sqlUpdSub,
                            N'@cj nvarchar(max), @SampleID int', @cj = @cj, @SampleID = @SampleID;

                    SET @action = CASE WHEN @Mode = 'MERGE' THEN 'MERGED' ELSE 'UPDATED' END;
                END
            END

            UPDATE portal.SampleImportRow
                SET [Status] = CASE WHEN @action = 'SKIPPED' THEN 'SKIPPED' ELSE 'COMMITTED' END,
                    [Action] = @action,
                    ConflictsJson = @conflicts,
                    CreatedPatientID = @PatientID,
                    CreatedSampleID = @SampleID
            WHERE ID = @RowID;

            FETCH NEXT FROM row_cur INTO @RowID, @cj, @raw;
        END
        CLOSE row_cur;
        DEALLOCATE row_cur;

        UPDATE portal.SampleImportBatch SET [Status] = 'COMMITTED', UpdatedAt = SYSDATETIME() WHERE ID = @BatchID;

        COMMIT;
    END TRY
    BEGIN CATCH
        IF CURSOR_STATUS('local','row_cur') >= 0 BEGIN CLOSE row_cur; DEALLOCATE row_cur; END
        IF XACT_STATE() <> 0 ROLLBACK;
        UPDATE portal.SampleImportBatch SET [Status] = 'FAILED', UpdatedAt = SYSDATETIME() WHERE ID = @BatchID;
        THROW;
    END CATCH;

    -- Summary
    SELECT
        SUM(CASE WHEN [Action] = 'INSERTED' THEN 1 ELSE 0 END) AS Inserted,
        SUM(CASE WHEN [Action] = 'UPDATED'  THEN 1 ELSE 0 END) AS Updated,
        SUM(CASE WHEN [Action] = 'MERGED'   THEN 1 ELSE 0 END) AS Merged,
        SUM(CASE WHEN [Action] = 'SKIPPED'  THEN 1 ELSE 0 END) AS Skipped
    FROM portal.SampleImportRow WHERE BatchID = @BatchID;
END
GO

-- ============================================================
-- portal.spSampleImportCreateBatch
-- Creates a Sample Import batch header and returns its ID. The disease,
-- institution and customer scope the import; FileHash is used later for
-- re-import detection; MappingJson stores the column/value mapping.
--
-- Usage:
--   EXEC portal.spSampleImportCreateBatch
--        @DiseaseID=1, @CustomerID=10, @InstitutionID=5,
--        @CreatedBy=42, @FileName=N'samples.csv', @FileHash=0x...,
--        @Mode='INSERT', @MappingJson=N'{...}', @BatchID=@id OUTPUT;
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[spSampleImportCreateBatch]
    @DiseaseID      int,
    @CustomerID     int,
    @InstitutionID  int,
    @CreatedBy      int            = NULL,
    @FileName       nvarchar(260)  = NULL,
    @FileHash       varbinary(32)  = NULL,
    @Mode           varchar(20)    = 'INSERT',
    @MappingJson    nvarchar(max)  = NULL,
    @BatchID        int            OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS (SELECT 1 FROM portal.CustomerInstitutions
                   WHERE CustomerID = @CustomerID AND InstitutionID = @InstitutionID)
    BEGIN
        RAISERROR('Institution %d is not associated with customer %d.', 16, 1, @InstitutionID, @CustomerID);
        RETURN;
    END;

    INSERT INTO portal.SampleImportBatch
        (DiseaseID, CustomerID, InstitutionID, CreatedBy, [FileName], FileHash, [Status], [Mode], MappingJson)
    VALUES
        (@DiseaseID, @CustomerID, @InstitutionID, @CreatedBy, @FileName, @FileHash, 'STAGED', @Mode, @MappingJson);

    SET @BatchID = SCOPE_IDENTITY();

    SELECT @BatchID AS BatchID;
END
GO

-- ============================================================
-- portal.spSampleImportStageRows
-- Bulk-loads parsed CSV rows into portal.SampleImportRow for a batch.
-- @RowsJson is an array produced by the wizard, where each element carries
-- the original row (raw) and the normalized/canonical row (canonical):
--
--   [
--     { "rowNo": 1,
--       "raw":       { "MRN": "A-100", "Gender": "male", ... },
--       "canonical": { "PatientExternalID": "A-100", "Sex": "M", ... } },
--     ...
--   ]
--
-- Normalization (raw value -> canonical value, e.g. via Meta.Collections) is
-- performed by the wizard using portal.spGetCollectionItemsForMapping, which
-- reads the same Meta authority as Meta.fnResolveCollectionItem. T-SQL remains
-- the single VALIDATION layer (see portal.spSampleImportValidate).
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[spSampleImportStageRows]
    @BatchID   int,
    @RowsJson  nvarchar(max)
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS (SELECT 1 FROM portal.SampleImportBatch WHERE ID = @BatchID)
    BEGIN
        RAISERROR('Batch %d not found.', 16, 1, @BatchID);
        RETURN;
    END;

    IF ISJSON(@RowsJson) <> 1
    BEGIN
        RAISERROR('@RowsJson is not valid JSON.', 16, 1);
        RETURN;
    END;

    INSERT INTO portal.SampleImportRow (BatchID, RowNo, RawJson, CanonicalJson, [Status])
    SELECT
        @BatchID,
        j.RowNo,
        j.RawJson,
        j.CanonicalJson,
        'STAGED'
    FROM OPENJSON(@RowsJson)
    WITH (
        RowNo          int            '$.rowNo',
        RawJson        nvarchar(max)  '$.raw'        AS JSON,
        CanonicalJson  nvarchar(max)  '$.canonical'  AS JSON
    ) j
    WHERE NOT EXISTS (
        SELECT 1 FROM portal.SampleImportRow r
        WHERE r.BatchID = @BatchID AND r.RowNo = j.RowNo
    );

    UPDATE b
        SET [RowCount] = (SELECT COUNT(*) FROM portal.SampleImportRow r WHERE r.BatchID = @BatchID),
            UpdatedAt  = SYSDATETIME()
    FROM portal.SampleImportBatch b
    WHERE b.ID = @BatchID;

    SELECT [RowCount] FROM portal.SampleImportBatch WHERE ID = @BatchID;
END
GO

-- ============================================================
-- portal.spSampleImportValidate
-- THE single validation layer for the Sample Import wizard. Validates every
-- staged row's CanonicalJson against portal.DiseaseFieldContract using OPENJSON
-- (type / required / enum / min / max) and runs referential checks
-- (duplicate SampleName in-file). It also returns re-import signals:
-- whether the same file was already committed, and how many rows collide with
-- existing samples on the natural key (CustomerID, SampleName).
--
-- Writes per-row ErrorsJson + Status into portal.SampleImportRow and sets the
-- batch Status to 'VALIDATED'.
--
-- Result set: one row -> (DuplicateFile bit, CollisionCount int,
--                         ValidRows int, InvalidRows int).
-- ============================================================
CREATE OR ALTER   PROCEDURE [portal].[spSampleImportValidate]
    @BatchID int
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @DiseaseID int, @CustomerID int, @InstitutionID int, @FileHash varbinary(32);

    SELECT @DiseaseID = DiseaseID, @CustomerID = CustomerID,
           @InstitutionID = InstitutionID, @FileHash = FileHash
    FROM portal.SampleImportBatch WHERE ID = @BatchID;

    IF @DiseaseID IS NULL
    BEGIN
        RAISERROR('Batch %d not found.', 16, 1, @BatchID);
        RETURN;
    END;

    -- ---- Contract field metadata for this disease --------------------------
    IF OBJECT_ID('tempdb..#fields') IS NOT NULL DROP TABLE #fields;
    SELECT
        c.FieldName COLLATE DATABASE_DEFAULT AS FieldName,
        c.DataType,
        c.IsRequired,
        c.CollectionName,
        c.ValueStoreMode,
        TRY_CAST(JSON_VALUE(c.ValidationJson, '$.min') AS float) AS MinNum,
        TRY_CAST(JSON_VALUE(c.ValidationJson, '$.max') AS float) AS MaxNum
    INTO #fields
    FROM portal.DiseaseFieldContract c
    WHERE c.DiseaseID = @DiseaseID AND c.IsActive = 1;

    -- ---- Allowed canonical values for collection-backed fields -------------
    IF OBJECT_ID('tempdb..#allowed') IS NOT NULL DROP TABLE #allowed;
    CREATE TABLE #allowed (
        FieldName  nvarchar(128) COLLATE DATABASE_DEFAULT,
        AllowedVal nvarchar(200) COLLATE DATABASE_DEFAULT);

    -- CODE store mode -> the 'code' attribute
    INSERT INTO #allowed (FieldName, AllowedVal)
    SELECT f.FieldName, civ.ValueString
    FROM #fields f
    INNER JOIN Meta.Collections col ON col.Name = f.CollectionName
    INNER JOIN Meta.CollectionItem ci ON ci.CollectionID = col.ID
    INNER JOIN Meta.CollectionItemValue civ ON civ.CollectionItemID = ci.ID AND civ.Name = 'code'
    WHERE f.CollectionName IS NOT NULL AND f.ValueStoreMode = 'CODE' AND civ.ValueString IS NOT NULL;

    -- LABEL store mode -> the canonical label (ValueString)
    INSERT INTO #allowed (FieldName, AllowedVal)
    SELECT f.FieldName, ci.ValueString
    FROM #fields f
    INNER JOIN Meta.Collections col ON col.Name = f.CollectionName
    INNER JOIN Meta.CollectionItem ci ON ci.CollectionID = col.ID
    WHERE f.CollectionName IS NOT NULL AND f.ValueStoreMode = 'LABEL' AND ci.ValueString IS NOT NULL;

    -- REPORTED store mode -> the 'reportedValue' attribute
    INSERT INTO #allowed (FieldName, AllowedVal)
    SELECT f.FieldName, civ.ValueString
    FROM #fields f
    INNER JOIN Meta.Collections col ON col.Name = f.CollectionName
    INNER JOIN Meta.CollectionItem ci ON ci.CollectionID = col.ID
    INNER JOIN Meta.CollectionItemValue civ ON civ.CollectionItemID = ci.ID AND civ.Name = 'reportedValue'
    WHERE f.CollectionName IS NOT NULL AND f.ValueStoreMode = 'REPORTED' AND civ.ValueString IS NOT NULL;

    -- ---- Flatten canonical rows into (RowID, FieldName, Val) ----------------
    IF OBJECT_ID('tempdb..#rowvals') IS NOT NULL DROP TABLE #rowvals;
    SELECT
        r.ID                                  AS RowID,
        CAST(oj.[key] AS nvarchar(128)) COLLATE DATABASE_DEFAULT AS FieldName,
        oj.[value] COLLATE DATABASE_DEFAULT   AS Val
    INTO #rowvals
    FROM portal.SampleImportRow r
    CROSS APPLY OPENJSON(r.CanonicalJson) oj
    WHERE r.BatchID = @BatchID;

    CREATE INDEX IX_rowvals ON #rowvals (FieldName, RowID);

    -- ---- Collect errors -----------------------------------------------------
    IF OBJECT_ID('tempdb..#errors') IS NOT NULL DROP TABLE #errors;
    CREATE TABLE #errors (RowID int, FieldName sysname, Code varchar(30), Msg nvarchar(400));

    -- 1) Required missing/empty
    INSERT INTO #errors (RowID, FieldName, Code, Msg)
    SELECT r.ID, f.FieldName, 'REQUIRED', N'Required value is missing.'
    FROM portal.SampleImportRow r
    CROSS JOIN #fields f
    WHERE r.BatchID = @BatchID AND f.IsRequired = 1
      AND NOT EXISTS (
        SELECT 1 FROM #rowvals v
        WHERE v.RowID = r.ID AND v.FieldName = f.FieldName
          AND v.Val IS NOT NULL AND LTRIM(RTRIM(v.Val)) <> '');

    -- 2) Type errors (only when value is present and non-empty)
    INSERT INTO #errors (RowID, FieldName, Code, Msg)
    SELECT v.RowID, v.FieldName, 'TYPE',
           N'Value ''' + LEFT(v.Val, 100) + N''' is not a valid ' + f.DataType + N'.'
    FROM #rowvals v
    INNER JOIN #fields f ON f.FieldName = v.FieldName
    WHERE v.Val IS NOT NULL AND LTRIM(RTRIM(v.Val)) <> ''
      AND (
            (f.DataType = 'INT'   AND TRY_CAST(v.Val AS int) IS NULL)
         OR (f.DataType = 'FLOAT' AND TRY_CAST(v.Val AS float) IS NULL)
         OR (f.DataType = 'DATE'  AND TRY_CONVERT(date, v.Val) IS NULL)
         OR (f.DataType = 'GUID'  AND TRY_CAST(v.Val AS uniqueidentifier) IS NULL)
         OR (f.DataType = 'BOOL'  AND LOWER(LTRIM(RTRIM(v.Val))) NOT IN ('0','1','true','false','yes','no'))
      );

    -- 3) Enum / collection membership
    INSERT INTO #errors (RowID, FieldName, Code, Msg)
    SELECT v.RowID, v.FieldName, 'ENUM',
           N'Value ''' + LEFT(v.Val, 100) + N''' is not an allowed value for ' + f.CollectionName + N'.'
    FROM #rowvals v
    INNER JOIN #fields f ON f.FieldName = v.FieldName
    WHERE v.Val IS NOT NULL AND LTRIM(RTRIM(v.Val)) <> ''
      AND f.CollectionName IS NOT NULL
      AND EXISTS (SELECT 1 FROM #allowed a WHERE a.FieldName = f.FieldName)
      AND NOT EXISTS (
        SELECT 1 FROM #allowed a
        WHERE a.FieldName = f.FieldName
          AND UPPER(a.AllowedVal) = UPPER(LTRIM(RTRIM(v.Val))));

    -- 4) Range (min/max) for numeric fields
    INSERT INTO #errors (RowID, FieldName, Code, Msg)
    SELECT v.RowID, v.FieldName, 'RANGE',
           N'Value ''' + LEFT(v.Val, 100) + N''' is out of range.'
    FROM #rowvals v
    INNER JOIN #fields f ON f.FieldName = v.FieldName
    WHERE v.Val IS NOT NULL AND LTRIM(RTRIM(v.Val)) <> ''
      AND f.DataType IN ('INT','FLOAT')
      AND TRY_CAST(v.Val AS float) IS NOT NULL
      AND ( (f.MinNum IS NOT NULL AND TRY_CAST(v.Val AS float) < f.MinNum)
         OR (f.MaxNum IS NOT NULL AND TRY_CAST(v.Val AS float) > f.MaxNum) );

    -- 5) Duplicate SampleName within the file
    INSERT INTO #errors (RowID, FieldName, Code, Msg)
    SELECT v.RowID, 'SampleName', 'DUP_IN_FILE',
           N'SampleName ''' + LEFT(v.Val, 100) + N''' appears more than once in the file.'
    FROM #rowvals v
    WHERE v.FieldName = 'SampleName'
      AND v.Val IS NOT NULL AND LTRIM(RTRIM(v.Val)) <> ''
      AND EXISTS (
        SELECT 1 FROM #rowvals v2
        WHERE v2.FieldName = 'SampleName' AND v2.RowID <> v.RowID
          AND UPPER(LTRIM(RTRIM(v2.Val))) = UPPER(LTRIM(RTRIM(v.Val))));

    -- ---- Persist per-row results -------------------------------------------
    UPDATE r
        SET ErrorsJson = e.ErrorsJson,
            [Status]   = CASE WHEN e.ErrorsJson IS NULL THEN 'VALID' ELSE 'INVALID' END
    FROM portal.SampleImportRow r
    OUTER APPLY (
        SELECT (
            SELECT err.FieldName AS [field], err.Code AS [code], err.Msg AS [message]
            FROM #errors err
            WHERE err.RowID = r.ID
            FOR JSON PATH
        ) AS ErrorsJson
    ) e
    WHERE r.BatchID = @BatchID;

    UPDATE portal.SampleImportBatch
        SET [Status] = 'VALIDATED', UpdatedAt = SYSDATETIME()
    WHERE ID = @BatchID;

    -- ---- Re-import signals --------------------------------------------------
    DECLARE @DuplicateFile bit = CASE WHEN @FileHash IS NOT NULL AND EXISTS (
            SELECT 1 FROM portal.SampleImportBatch b
            WHERE b.ID <> @BatchID AND b.[Status] = 'COMMITTED'
              AND b.CustomerID = @CustomerID AND b.DiseaseID = @DiseaseID
              AND b.FileHash = @FileHash) THEN 1 ELSE 0 END;

    DECLARE @CollisionCount int = (
        SELECT COUNT(DISTINCT v.RowID)
        FROM #rowvals v
        WHERE v.FieldName = 'SampleName'
          AND v.Val IS NOT NULL AND LTRIM(RTRIM(v.Val)) <> ''
          AND EXISTS (
            SELECT 1 FROM portal.Samples s
            WHERE s.CustomerID = @CustomerID
              AND UPPER(LTRIM(RTRIM(s.SampleName))) = UPPER(LTRIM(RTRIM(v.Val)))));

    SELECT
        @DuplicateFile AS DuplicateFile,
        @CollisionCount AS CollisionCount,
        (SELECT COUNT(*) FROM portal.SampleImportRow WHERE BatchID = @BatchID AND [Status] = 'VALID')   AS ValidRows,
        (SELECT COUNT(*) FROM portal.SampleImportRow WHERE BatchID = @BatchID AND [Status] = 'INVALID') AS InvalidRows;
END
GO

