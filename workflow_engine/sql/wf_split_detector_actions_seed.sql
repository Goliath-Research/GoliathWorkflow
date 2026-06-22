/*
  Register split-detector workflow actions (run once per wf database).

  Prerequisites: wf schema deployed (MethylPipeline_*.sql or sql_pg deploy).

  After deploying updated workers/packages, also run:
    methyl-export-action-catalog
    python workflow_engine/sql/seed_action_catalog.py --regenerate-catalog
  (PostgreSQL full catalog) OR:
    psql ... -f workflow_engine/sql_pg/wf_split_detector_actions_seed.sql
  (PostgreSQL four-action seed) OR execute the MERGE below on Azure SQL.
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
