/*
  Azure SQL: create a workflow definition graph from a JSON spec.
  Returns a single-row result set with workflow_def_id, workflow_version_id, root_node_id, name.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'wf.workflow_def', N'U') IS NULL
BEGIN
    RAISERROR(N'Prerequisite missing: base wf schema not deployed.', 16, 1);
    RETURN;
END
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_create_workflow_graph
    @spec json
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @def_id BIGINT;
    DECLARE @ver_id BIGINT;
    DECLARE @root_node_id BIGINT;
    DECLARE @name NVARCHAR(256) = JSON_VALUE(@spec, '$.name');
    DECLARE @root_key NVARCHAR(256) = JSON_VALUE(@spec, '$.root_node_key');

    IF @name IS NULL OR LTRIM(RTRIM(@name)) = N''
        THROW 50010, N'workflow spec missing name', 1;
    IF @root_key IS NULL OR LTRIM(RTRIM(@root_key)) = N''
        THROW 50011, N'workflow spec missing root_node_key', 1;

    INSERT INTO wf.workflow_def (name, description)
    VALUES (@name, JSON_VALUE(@spec, '$.description'));
    SET @def_id = SCOPE_IDENTITY();

    INSERT INTO wf.workflow_version (workflow_def_id, version_major, version_minor, is_active)
    VALUES (
        @def_id,
        COALESCE(CAST(JSON_VALUE(@spec, '$.version_major') AS INT), 1),
        COALESCE(CAST(JSON_VALUE(@spec, '$.version_minor') AS INT), 0),
        COALESCE(CAST(JSON_VALUE(@spec, '$.is_active') AS BIT), 1)
    );
    SET @ver_id = SCOPE_IDENTITY();

    DECLARE @nodes TABLE (
        ord INT IDENTITY(1,1),
        node_key NVARCHAR(256),
        node_type NVARCHAR(32),
        action_name NVARCHAR(256),
        repeat_count INT,
        condition_ref_node_key NVARCHAR(256),
        switch_ref_node_key NVARCHAR(256),
        condition_var NVARCHAR(256),
        switch_var NVARCHAR(256),
        foreach_collection_var NVARCHAR(256),
        foreach_item_var NVARCHAR(256),
        foreach_index_var NVARCHAR(256),
        foreach_parallel BIT,
        input_template json,
        node_id BIGINT NULL
    );

    INSERT INTO @nodes (
        node_key, node_type, action_name, repeat_count,
        condition_ref_node_key, switch_ref_node_key, condition_var, switch_var,
        foreach_collection_var, foreach_item_var, foreach_index_var, foreach_parallel,
        input_template
    )
    SELECT
        JSON_VALUE(n.value, '$.node_key'),
        JSON_VALUE(n.value, '$.node_type'),
        JSON_VALUE(n.value, '$.action_name'),
        TRY_CAST(JSON_VALUE(n.value, '$.repeat_count') AS INT),
        JSON_VALUE(n.value, '$.condition_ref_node_key'),
        JSON_VALUE(n.value, '$.switch_ref_node_key'),
        JSON_VALUE(n.value, '$.condition_var'),
        JSON_VALUE(n.value, '$.switch_var'),
        JSON_VALUE(n.value, '$.foreach_collection_var'),
        JSON_VALUE(n.value, '$.foreach_item_var'),
        JSON_VALUE(n.value, '$.foreach_index_var'),
        COALESCE(TRY_CAST(JSON_VALUE(n.value, '$.foreach_parallel') AS BIT), 0),
        JSON_QUERY(n.value, '$.input_template')
    FROM OPENJSON(@spec, '$.nodes') n;

    DECLARE @nk NVARCHAR(256), @nt NVARCHAR(32), @an NVARCHAR(256);
    DECLARE @rc INT, @crnk NVARCHAR(256), @srnk NVARCHAR(256);
    DECLARE @cv NVARCHAR(256), @sv NVARCHAR(256);
    DECLARE @fcv NVARCHAR(256), @fiv NVARCHAR(256), @fidx NVARCHAR(256);
    DECLARE @fp BIT, @it json, @nid BIGINT, @aid BIGINT;

    DECLARE node_cur CURSOR LOCAL FAST_FORWARD FOR
        SELECT node_key, node_type, action_name, repeat_count,
               condition_ref_node_key, switch_ref_node_key, condition_var, switch_var,
               foreach_collection_var, foreach_item_var, foreach_index_var, foreach_parallel,
               input_template
        FROM @nodes ORDER BY ord;

    OPEN node_cur;
    FETCH NEXT FROM node_cur INTO @nk, @nt, @an, @rc, @crnk, @srnk, @cv, @sv, @fcv, @fiv, @fidx, @fp, @it;

    WHILE @@FETCH_STATUS = 0
    BEGIN
        SET @aid = NULL;
        IF @an IS NOT NULL AND LTRIM(RTRIM(@an)) <> N''
        BEGIN
            SELECT @aid = id FROM wf.workflow_action WHERE action_name = @an;
            IF @aid IS NULL
                THROW 50012, N'unknown action_name in workflow spec', 1;
        END

        INSERT INTO wf.workflow_node (
            workflow_version_id, node_type, node_key, workflow_action_id,
            repeat_count, condition_ref_node_key, switch_ref_node_key,
            condition_var, switch_var,
            foreach_collection_var, foreach_item_var, foreach_index_var, foreach_parallel
        )
        VALUES (@ver_id, @nt, @nk, @aid, @rc, @crnk, @srnk, @cv, @sv, @fcv, @fiv, @fidx, @fp);
        SET @nid = SCOPE_IDENTITY();

        UPDATE @nodes SET node_id = @nid WHERE node_key = @nk;

        IF @it IS NOT NULL
            INSERT INTO wf.workflow_input_template (workflow_node_id, template_json)
            VALUES (@nid, @it);

        FETCH NEXT FROM node_cur INTO @nk, @nt, @an, @rc, @crnk, @srnk, @cv, @sv, @fcv, @fiv, @fidx, @fp, @it;
    END
    CLOSE node_cur;
    DEALLOCATE node_cur;

    INSERT INTO wf.workflow_edge (parent_node_id, child_node_id, child_order, branch_kind, condition_expr, switch_case_value, is_default)
    SELECT
        pn.node_id,
        cn.node_id,
        COALESCE(CAST(JSON_VALUE(e.value, '$.child_order') AS INT), 0),
        JSON_VALUE(e.value, '$.branch_kind'),
        JSON_VALUE(e.value, '$.condition_expr'),
        TRY_CAST(JSON_VALUE(e.value, '$.switch_case_value') AS INT),
        COALESCE(CAST(JSON_VALUE(e.value, '$.is_default') AS BIT), 0)
    FROM OPENJSON(@spec, '$.edges') e
    INNER JOIN @nodes pn ON pn.node_key = JSON_VALUE(e.value, '$.parent_node_key')
    INNER JOIN @nodes cn ON cn.node_key = JSON_VALUE(e.value, '$.child_node_key');

    INSERT INTO wf.workflow_input_binding (workflow_node_id, target_json_path, source_expr, is_required)
    SELECT
        n.node_id,
        JSON_VALUE(b.value, '$.target_json_path'),
        JSON_VALUE(b.value, '$.source_expr'),
        COALESCE(CAST(JSON_VALUE(b.value, '$.is_required') AS BIT), 0)
    FROM OPENJSON(@spec, '$.input_bindings') b
    INNER JOIN @nodes n ON n.node_key = JSON_VALUE(b.value, '$.node_key');

    INSERT INTO wf.variable_output_binding (workflow_node_id, var_name, source_kind, source_json_path)
    SELECT
        n.node_id,
        JSON_VALUE(b.value, '$.var_name'),
        JSON_VALUE(b.value, '$.source_kind'),
        JSON_VALUE(b.value, '$.source_json_path')
    FROM OPENJSON(@spec, '$.output_bindings') b
    INNER JOIN @nodes n ON n.node_key = JSON_VALUE(b.value, '$.node_key');

    INSERT INTO wf.node_scope_default (workflow_node_id, var_name, default_expr)
    SELECT
        n.node_id,
        JSON_VALUE(b.value, '$.var_name'),
        JSON_VALUE(b.value, '$.default_expr')
    FROM OPENJSON(@spec, '$.scope_defaults') b
    INNER JOIN @nodes n ON n.node_key = JSON_VALUE(b.value, '$.node_key');

    SELECT @root_node_id = node_id FROM @nodes WHERE node_key = @root_key;
    IF @root_node_id IS NULL
        THROW 50013, N'root_node_key not found among nodes', 1;

    UPDATE wf.workflow_version SET root_node_id = @root_node_id WHERE id = @ver_id;

    SELECT
        @def_id AS workflow_def_id,
        @ver_id AS workflow_version_id,
        @root_node_id AS root_node_id,
        @name AS name;
END;
GO
