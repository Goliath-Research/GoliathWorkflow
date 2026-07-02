/*
  Add Arc machine resource binding for worker cluster attestation.
  Deploy after wf_cluster_security_columns.sql (Azure SQL wf schema).
*/

IF COL_LENGTH('wf.cluster', 'arc_resource_id') IS NULL
BEGIN
    ALTER TABLE wf.cluster ADD arc_resource_id nvarchar(256) NULL;
END
GO
