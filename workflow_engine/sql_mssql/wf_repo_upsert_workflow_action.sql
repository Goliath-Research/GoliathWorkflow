/*
  Azure SQL: bootstrap upsert for wf.workflow_action (name / capability / schema ref).

  SUPERSEDED for full catalog seed: deploy ``wf_action_dispatch_metadata.sql`` after
  this file. That script adds execution_mode / cli_tool / in_process_handler / argv_map
  and replaces this procedure with the 7-parameter version used by
  ``seed_action_catalog.py`` and the admin gateway.

  Kept as a bootstrap so databases without dispatch columns can still upsert names.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'wf.workflow_action', N'U') IS NULL
BEGIN
    RAISERROR(N'Prerequisite missing: base wf schema not deployed.', 16, 1);
    RETURN;
END
GO

CREATE OR ALTER PROCEDURE wf.wf_repo_upsert_workflow_action
    @action_name NVARCHAR(256),
    @capability NVARCHAR(128) = NULL,
    @payload_schema_ref NVARCHAR(512) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    IF @action_name IS NULL OR LTRIM(RTRIM(@action_name)) = N''
        RETURN;

    IF EXISTS (SELECT 1 FROM wf.workflow_action WHERE action_name = @action_name)
        UPDATE wf.workflow_action
        SET capability = @capability,
            payload_schema_ref = COALESCE(@payload_schema_ref, payload_schema_ref)
        WHERE action_name = @action_name;
    ELSE
        INSERT INTO wf.workflow_action (action_name, capability, payload_schema_ref)
        VALUES (@action_name, @capability, @payload_schema_ref);
END;
GO
