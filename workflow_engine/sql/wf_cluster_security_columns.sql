/*
  Add cluster security columns for gateway tiered auth (mixed worker topology).
  Deploy after wf_worker_api_contract.sql (Azure SQL wf schema).
*/

IF COL_LENGTH('wf.cluster', 'allowed_source_cidrs') IS NULL
BEGIN
    ALTER TABLE wf.cluster ADD allowed_source_cidrs nvarchar(max) NULL;
END
GO

IF COL_LENGTH('wf.cluster', 'entra_client_id') IS NULL
BEGIN
    ALTER TABLE wf.cluster ADD entra_client_id nvarchar(64) NULL;
END
GO

IF COL_LENGTH('wf.cluster', 'arc_resource_id') IS NULL
BEGIN
    ALTER TABLE wf.cluster ADD arc_resource_id nvarchar(256) NULL;
END
GO
