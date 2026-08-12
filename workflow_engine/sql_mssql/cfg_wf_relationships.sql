/*
  cfg ↔ wf relationships (additive; safe to re-run).
  Bridges configuration registry to the workflow engine without putting science
  config tables inside wf.
*/

/* --- domain_program → wf.workflow_def / wf.workflow_version --- */
IF COL_LENGTH(N'cfg.domain_program', N'workflow_def_id') IS NULL
BEGIN
    ALTER TABLE cfg.domain_program ADD workflow_def_id bigint NULL;
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_cfg_dp_workflow_def'
)
BEGIN
    ALTER TABLE cfg.domain_program
      ADD CONSTRAINT FK_cfg_dp_workflow_def
      FOREIGN KEY (workflow_def_id) REFERENCES wf.workflow_def (id);
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_cfg_dp_compiled_version'
)
BEGIN
    ALTER TABLE cfg.domain_program
      ADD CONSTRAINT FK_cfg_dp_compiled_version
      FOREIGN KEY (compiled_workflow_version_id) REFERENCES wf.workflow_version (id);
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'IX_cfg_dp_compiled_version' AND object_id = OBJECT_ID(N'cfg.domain_program')
)
BEGIN
    CREATE INDEX IX_cfg_dp_compiled_version ON cfg.domain_program (compiled_workflow_version_id);
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'IX_cfg_dp_workflow_def' AND object_id = OBJECT_ID(N'cfg.domain_program')
)
BEGIN
    CREATE INDEX IX_cfg_dp_workflow_def ON cfg.domain_program (workflow_def_id);
END
GO

/* --- action_definition → wf.workflow_action --- */
IF COL_LENGTH(N'cfg.action_definition', N'workflow_action_id') IS NULL
BEGIN
    ALTER TABLE cfg.action_definition ADD workflow_action_id bigint NULL;
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_cfg_ad_workflow_action'
)
BEGIN
    ALTER TABLE cfg.action_definition
      ADD CONSTRAINT FK_cfg_ad_workflow_action
      FOREIGN KEY (workflow_action_id) REFERENCES wf.workflow_action (id);
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'IX_cfg_ad_workflow_action' AND object_id = OBJECT_ID(N'cfg.action_definition')
)
BEGIN
    CREATE INDEX IX_cfg_ad_workflow_action ON cfg.action_definition (workflow_action_id);
END
GO

/* One published cfg action maps to at most one wf.workflow_action */
IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'UQ_cfg_ad_workflow_action' AND object_id = OBJECT_ID(N'cfg.action_definition')
)
BEGIN
    CREATE UNIQUE INDEX UQ_cfg_ad_workflow_action
      ON cfg.action_definition (workflow_action_id)
      WHERE workflow_action_id IS NOT NULL;
END
GO

/* --- reference_asset → storage_endpoint (primary download source) --- */
IF COL_LENGTH(N'cfg.reference_asset', N'storage_endpoint_id') IS NULL
BEGIN
    ALTER TABLE cfg.reference_asset ADD storage_endpoint_id bigint NULL;
END
GO

IF COL_LENGTH(N'cfg.reference_asset', N'asset_type') IS NULL
BEGIN
    ALTER TABLE cfg.reference_asset ADD asset_type nvarchar(64) NULL;
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_cfg_ra_storage_endpoint'
)
BEGIN
    ALTER TABLE cfg.reference_asset
      ADD CONSTRAINT FK_cfg_ra_storage_endpoint
      FOREIGN KEY (storage_endpoint_id) REFERENCES cfg.storage_endpoint (id);
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes WHERE name = N'IX_cfg_ra_storage_endpoint' AND object_id = OBJECT_ID(N'cfg.reference_asset')
)
BEGIN
    CREATE INDEX IX_cfg_ra_storage_endpoint ON cfg.reference_asset (storage_endpoint_id);
END
GO

/* --- site ↔ reference_asset (M:N; genome/GTF/pangenome roles) --- */
IF OBJECT_ID(N'cfg.site_reference_asset', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.site_reference_asset (
        id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
        site_id bigint NOT NULL,
        reference_asset_id bigint NOT NULL,
        asset_role nvarchar(64) NOT NULL,
        created_at_utc datetime2(3) NOT NULL CONSTRAINT DF_cfg_sra_created DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT uq_cfg_sra_site_role UNIQUE (site_id, asset_role),
        CONSTRAINT uq_cfg_sra_site_asset UNIQUE (site_id, reference_asset_id),
        CONSTRAINT FK_cfg_sra_site FOREIGN KEY (site_id) REFERENCES cfg.site (id) ON DELETE CASCADE,
        CONSTRAINT FK_cfg_sra_asset FOREIGN KEY (reference_asset_id) REFERENCES cfg.reference_asset (id),
        CONSTRAINT ck_cfg_sra_role CHECK (asset_role IN (
            N'reference_genome', N'annotation_gtf', N'pangenome_bundle',
            N'mapper_cache',
            N'houseman_seed_basis', N'hitimed_hierarchy_basis',
            N'other'
        ))
    );
    CREATE INDEX IX_cfg_sra_asset ON cfg.site_reference_asset (reference_asset_id);
END
GO

/* --- storage_endpoint → cfg.credential (internal) --- */
IF COL_LENGTH(N'cfg.storage_endpoint', N'credential_id') IS NULL
BEGIN
    ALTER TABLE cfg.storage_endpoint ADD credential_id bigint NULL;
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.foreign_keys WHERE name = N'FK_cfg_se_credential'
)
BEGIN
    ALTER TABLE cfg.storage_endpoint
      ADD CONSTRAINT FK_cfg_se_credential
      FOREIGN KEY (credential_id) REFERENCES cfg.credential (id);
END
GO

/* --- study run link: cfg.study (+ profile/program/site) ↔ wf.workflow_instance --- */
IF OBJECT_ID(N'cfg.study_instance_link', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.study_instance_link (
        id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
        study_row_id bigint NOT NULL,
        workflow_instance_id bigint NOT NULL,
        domain_program_id bigint NULL,
        pipeline_profile_id bigint NULL,
        site_id bigint NULL,
        storage_profile_id bigint NULL,
        created_at_utc datetime2(3) NOT NULL CONSTRAINT DF_cfg_sil_created DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT uq_cfg_sil_instance UNIQUE (workflow_instance_id),
        CONSTRAINT FK_cfg_sil_study FOREIGN KEY (study_row_id) REFERENCES cfg.study (id),
        CONSTRAINT FK_cfg_sil_instance FOREIGN KEY (workflow_instance_id) REFERENCES wf.workflow_instance (id) ON DELETE CASCADE,
        CONSTRAINT FK_cfg_sil_program FOREIGN KEY (domain_program_id) REFERENCES cfg.domain_program (id),
        CONSTRAINT FK_cfg_sil_profile FOREIGN KEY (pipeline_profile_id) REFERENCES cfg.pipeline_profile (id),
        CONSTRAINT FK_cfg_sil_site FOREIGN KEY (site_id) REFERENCES cfg.site (id),
        CONSTRAINT FK_cfg_sil_storage_profile FOREIGN KEY (storage_profile_id) REFERENCES cfg.storage_profile (id)
    );
    CREATE INDEX IX_cfg_sil_study ON cfg.study_instance_link (study_row_id);
    CREATE INDEX IX_cfg_sil_program ON cfg.study_instance_link (domain_program_id);
END
GO

/* --- publish audit: DomainProgram publish → concrete wf version --- */
IF OBJECT_ID(N'cfg.program_publish', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.program_publish (
        id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
        domain_program_id bigint NOT NULL,
        workflow_def_id bigint NOT NULL,
        workflow_version_id bigint NOT NULL,
        content_hash nvarchar(128) NOT NULL,
        published_at_utc datetime2(3) NOT NULL CONSTRAINT DF_cfg_ppub_at DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT FK_cfg_ppub_program FOREIGN KEY (domain_program_id) REFERENCES cfg.domain_program (id),
        CONSTRAINT FK_cfg_ppub_def FOREIGN KEY (workflow_def_id) REFERENCES wf.workflow_def (id),
        CONSTRAINT FK_cfg_ppub_version FOREIGN KEY (workflow_version_id) REFERENCES wf.workflow_version (id),
        CONSTRAINT uq_cfg_ppub_program_version UNIQUE (domain_program_id, workflow_version_id)
    );
    CREATE INDEX IX_cfg_ppub_version ON cfg.program_publish (workflow_version_id);
END
GO

/* Convenience views */
CREATE OR ALTER VIEW cfg.v_domain_program_wf AS
SELECT
    p.id AS domain_program_id,
    p.name AS program_name,
    p.version AS program_version,
    p.status,
    p.content_hash,
    p.workflow_def_id,
    d.name AS workflow_def_name,
    p.compiled_workflow_version_id,
    v.version_major,
    v.version_minor,
    v.is_active
FROM cfg.domain_program p
LEFT JOIN wf.workflow_def d ON d.id = p.workflow_def_id
LEFT JOIN wf.workflow_version v ON v.id = p.compiled_workflow_version_id;
GO

/* Retired cfg.action_definition view — browse wf actions + explicit data types. */
CREATE OR ALTER VIEW cfg.v_action_definition_wf AS
SELECT
    wa.id AS workflow_action_id,
    wa.action_name,
    wa.capability,
    wa.implementation_status,
    wa.input_type_id,
    tin.name AS input_type_name,
    wa.output_type_id,
    tout.name AS output_type_name,
    wa.can_pause,
    wa.can_continue,
    wa.can_stop
FROM wf.workflow_action wa
LEFT JOIN wf.data_type tin ON tin.id = wa.input_type_id
LEFT JOIN wf.data_type tout ON tout.id = wa.output_type_id;
GO

CREATE OR ALTER VIEW cfg.v_reference_asset AS
SELECT
    ra.id AS reference_asset_id,
    ra.name AS asset_name,
    ra.version AS asset_version,
    ra.status,
    ra.asset_type,
    ra.storage_endpoint_id,
    se.name AS storage_endpoint_name,
    se.provider AS storage_provider,
    se.credential_id
FROM cfg.reference_asset ra
LEFT JOIN cfg.storage_endpoint se ON se.id = ra.storage_endpoint_id;
GO

CREATE OR ALTER VIEW cfg.v_site_reference_asset AS
SELECT
    sra.id AS link_id,
    sra.site_id,
    s.name AS site_name,
    sra.reference_asset_id,
    ra.name AS asset_name,
    sra.asset_role,
    ra.storage_endpoint_id,
    ra.status AS asset_status
FROM cfg.site_reference_asset sra
INNER JOIN cfg.site s ON s.id = sra.site_id
INNER JOIN cfg.reference_asset ra ON ra.id = sra.reference_asset_id;
GO

CREATE OR ALTER VIEW cfg.v_study_instance AS
SELECT
    l.id AS link_id,
    l.study_row_id,
    s.name AS study_name,
    s.study_id,
    l.workflow_instance_id,
    i.status AS instance_status,
    i.workflow_version_id,
    l.domain_program_id,
    p.name AS program_name,
    l.pipeline_profile_id,
    pr.name AS profile_name,
    l.site_id,
    l.created_at_utc
FROM cfg.study_instance_link l
INNER JOIN cfg.study s ON s.id = l.study_row_id
INNER JOIN wf.workflow_instance i ON i.id = l.workflow_instance_id
LEFT JOIN cfg.domain_program p ON p.id = l.domain_program_id
LEFT JOIN cfg.pipeline_profile pr ON pr.id = l.pipeline_profile_id;
GO
