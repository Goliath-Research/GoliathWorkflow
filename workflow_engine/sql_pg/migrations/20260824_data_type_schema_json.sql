-- Bindable JSON Schema on wf.data_type (SchemaPropertyGrid).
-- Canonical functions live in wf_data_type.sql; this migration is the live
-- ALTER for databases that already have the table. Safe to re-run.

ALTER TABLE wf.data_type
  ADD COLUMN IF NOT EXISTS schema_json jsonb NULL;

DO $ck$
BEGIN
  ALTER TABLE wf.data_type
    ADD CONSTRAINT ck_wf_data_type_element_kind
    CHECK (element_type_id IS NULL OR kind = 'array');
EXCEPTION
  WHEN duplicate_object THEN NULL;
END
$ck$;
