-- Widen cfg.site_reference_asset.asset_role for plant / deconvolution atlases.
-- Safe to re-run: drops and recreates the CHECK constraint.

ALTER TABLE cfg.site_reference_asset
  DROP CONSTRAINT IF EXISTS ck_cfg_sra_role;

ALTER TABLE cfg.site_reference_asset
  ADD CONSTRAINT ck_cfg_sra_role CHECK (asset_role IN (
    'reference_genome', 'annotation_gtf', 'pangenome_bundle',
    'mapper_cache',
    'houseman_seed_basis', 'hitimed_hierarchy_basis',
    'other'
  ));
