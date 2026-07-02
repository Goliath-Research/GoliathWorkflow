/*
  Register split-detector workflow actions (run once per wf database).

  **Prefer full catalog seed for distributed workers:**
    source .venv/bin/activate
    methyl-export-task-schemas
    methyl-export-action-catalog
    python workflow_engine/sql_mssql/seed_action_catalog.py

  This script upserts four actions only (legacy lightweight path).
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

MERGE wf.workflow_action AS t
USING (VALUES
  (N'pipeline.dmp_select', N'methyl-dmp-select'),
  (N'pipeline.gene_select', N'methyl-gene-select'),
  (N'pipeline.gene_feature_select', N'methyl-gene-feature-select'),
  (N'validation.biomarker_filter', N'validation.biomarker-filter')
) AS s(action_name, capability)
ON t.action_name = s.action_name
WHEN NOT MATCHED THEN
  INSERT (action_name, capability, payload_schema_ref)
  VALUES (s.action_name, s.capability, s.action_name)
WHEN MATCHED THEN
  UPDATE SET capability = s.capability;
GO

PRINT N'Upserted split-detector actions: pipeline.dmp_select, pipeline.gene_select, pipeline.gene_feature_select, validation.biomarker_filter';
GO
