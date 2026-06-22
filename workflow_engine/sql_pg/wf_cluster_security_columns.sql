/*
  Cluster security columns for gateway IP binding and optional Entra SP mapping.
  Prerequisites: 00_schema.sql
*/

ALTER TABLE wf.cluster
  ADD COLUMN IF NOT EXISTS allowed_source_cidrs jsonb NULL,
  ADD COLUMN IF NOT EXISTS entra_client_id text NULL;
