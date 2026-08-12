/*
  cfg registry tables (versioned JSON documents).
  Payload columns use native Azure SQL json — never nvarchar(max).
  Credentials never materialize to /work.
*/
IF OBJECT_ID(N'cfg.site', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.site (
        id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
        name nvarchar(256) NOT NULL,
        version nvarchar(64) NOT NULL CONSTRAINT DF_cfg_site_version DEFAULT (N'1'),
        status varchar(32) NOT NULL CONSTRAINT DF_cfg_site_status DEFAULT ('draft'),
        content_hash nvarchar(128) NOT NULL,
        document_json json NOT NULL,
        created_at_utc datetime2(3) NOT NULL CONSTRAINT DF_cfg_site_created DEFAULT (SYSUTCDATETIME()),
        updated_at_utc datetime2(3) NULL,
        CONSTRAINT uq_cfg_site_name_version UNIQUE (name, version),
        CONSTRAINT ck_cfg_site_status CHECK (status IN ('draft', 'published', 'retired'))
    );
END
GO

IF OBJECT_ID(N'cfg.pipeline_profile', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.pipeline_profile (
        id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
        name nvarchar(256) NOT NULL,
        version nvarchar(64) NOT NULL CONSTRAINT DF_cfg_pp_version DEFAULT (N'1'),
        status varchar(32) NOT NULL CONSTRAINT DF_cfg_pp_status DEFAULT ('draft'),
        content_hash nvarchar(128) NOT NULL,
        document_json json NOT NULL,
        created_at_utc datetime2(3) NOT NULL CONSTRAINT DF_cfg_pp_created DEFAULT (SYSUTCDATETIME()),
        updated_at_utc datetime2(3) NULL,
        CONSTRAINT uq_cfg_pipeline_profile_name_version UNIQUE (name, version),
        CONSTRAINT ck_cfg_pipeline_profile_status CHECK (status IN ('draft', 'published', 'retired'))
    );
END
GO

IF OBJECT_ID(N'cfg.assay_procedure', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.assay_procedure (
        id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
        name nvarchar(256) NOT NULL,
        version nvarchar(64) NOT NULL CONSTRAINT DF_cfg_ap_version DEFAULT (N'1'),
        status varchar(32) NOT NULL CONSTRAINT DF_cfg_ap_status DEFAULT ('draft'),
        content_hash nvarchar(128) NOT NULL,
        document_json json NOT NULL,
        created_at_utc datetime2(3) NOT NULL CONSTRAINT DF_cfg_ap_created DEFAULT (SYSUTCDATETIME()),
        updated_at_utc datetime2(3) NULL,
        CONSTRAINT uq_cfg_assay_procedure_name_version UNIQUE (name, version),
        CONSTRAINT ck_cfg_assay_procedure_status CHECK (status IN ('draft', 'published', 'retired'))
    );
END
GO

/* Specimen / matrix analytes (cfdna, buffy_coat, …) — versioned catalog documents. */
IF OBJECT_ID(N'cfg.analyte', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.analyte (
        id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
        name nvarchar(256) NOT NULL,
        version nvarchar(64) NOT NULL CONSTRAINT DF_cfg_analyte_version DEFAULT (N'1'),
        status varchar(32) NOT NULL CONSTRAINT DF_cfg_analyte_status DEFAULT ('draft'),
        content_hash nvarchar(128) NOT NULL,
        document_json json NOT NULL,
        created_at_utc datetime2(3) NOT NULL CONSTRAINT DF_cfg_analyte_created DEFAULT (SYSUTCDATETIME()),
        updated_at_utc datetime2(3) NULL,
        CONSTRAINT uq_cfg_analyte_name_version UNIQUE (name, version),
        CONSTRAINT ck_cfg_analyte_status CHECK (status IN ('draft', 'published', 'retired'))
    );
END
GO

IF OBJECT_ID(N'cfg.domain_program', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.domain_program (
        id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
        name nvarchar(256) NOT NULL,
        version nvarchar(64) NOT NULL CONSTRAINT DF_cfg_dp_version DEFAULT (N'1'),
        status varchar(32) NOT NULL CONSTRAINT DF_cfg_dp_status DEFAULT ('draft'),
        content_hash nvarchar(128) NOT NULL,
        document_json json NOT NULL,
        compiled_workflow_version_id bigint NULL,
        workflow_def_id bigint NULL,
        created_at_utc datetime2(3) NOT NULL CONSTRAINT DF_cfg_dp_created DEFAULT (SYSUTCDATETIME()),
        updated_at_utc datetime2(3) NULL,
        CONSTRAINT uq_cfg_domain_program_name_version UNIQUE (name, version),
        CONSTRAINT ck_cfg_domain_program_status CHECK (status IN ('draft', 'published', 'retired'))
    );
END
GO

IF OBJECT_ID(N'cfg.study', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.study (
        id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
        name nvarchar(256) NOT NULL,
        version nvarchar(64) NOT NULL CONSTRAINT DF_cfg_study_version DEFAULT (N'1'),
        status varchar(32) NOT NULL CONSTRAINT DF_cfg_study_status DEFAULT ('draft'),
        content_hash nvarchar(128) NOT NULL,
        document_json json NOT NULL,
        study_id nvarchar(256) NULL,
        created_at_utc datetime2(3) NOT NULL CONSTRAINT DF_cfg_study_created DEFAULT (SYSUTCDATETIME()),
        updated_at_utc datetime2(3) NULL,
        CONSTRAINT uq_cfg_study_name_version UNIQUE (name, version),
        CONSTRAINT ck_cfg_study_status CHECK (status IN ('draft', 'published', 'retired'))
    );
END
GO

IF OBJECT_ID(N'cfg.credential', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.credential (
        id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
        name nvarchar(256) NOT NULL,
        version nvarchar(64) NOT NULL CONSTRAINT DF_cfg_cred_version DEFAULT (N'1'),
        status varchar(32) NOT NULL CONSTRAINT DF_cfg_cred_status DEFAULT ('draft'),
        content_hash nvarchar(128) NOT NULL,
        provider nvarchar(64) NOT NULL,
        auth_mode nvarchar(64) NOT NULL,
        secret_json json NOT NULL,
        created_at_utc datetime2(3) NOT NULL CONSTRAINT DF_cfg_cred_created DEFAULT (SYSUTCDATETIME()),
        updated_at_utc datetime2(3) NULL,
        CONSTRAINT uq_cfg_credential_name_version UNIQUE (name, version),
        CONSTRAINT ck_cfg_credential_status CHECK (status IN ('draft', 'published', 'retired'))
    );
END
GO

IF OBJECT_ID(N'cfg.storage_endpoint', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.storage_endpoint (
        id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
        name nvarchar(256) NOT NULL,
        version nvarchar(64) NOT NULL CONSTRAINT DF_cfg_se_version DEFAULT (N'1'),
        status varchar(32) NOT NULL CONSTRAINT DF_cfg_se_status DEFAULT ('draft'),
        content_hash nvarchar(128) NOT NULL,
        provider nvarchar(64) NOT NULL,
        location_json json NOT NULL,
        credential_name nvarchar(256) NULL,
        credential_id bigint NULL,
        created_at_utc datetime2(3) NOT NULL CONSTRAINT DF_cfg_se_created DEFAULT (SYSUTCDATETIME()),
        updated_at_utc datetime2(3) NULL,
        CONSTRAINT uq_cfg_storage_endpoint_name_version UNIQUE (name, version),
        CONSTRAINT ck_cfg_storage_endpoint_status CHECK (status IN ('draft', 'published', 'retired'))
    );
END
GO

IF OBJECT_ID(N'cfg.storage_profile', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.storage_profile (
        id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
        name nvarchar(256) NOT NULL,
        version nvarchar(64) NOT NULL CONSTRAINT DF_cfg_sp_version DEFAULT (N'1'),
        status varchar(32) NOT NULL CONSTRAINT DF_cfg_sp_status DEFAULT ('draft'),
        content_hash nvarchar(128) NOT NULL,
        document_json json NOT NULL,
        created_at_utc datetime2(3) NOT NULL CONSTRAINT DF_cfg_sp_created DEFAULT (SYSUTCDATETIME()),
        updated_at_utc datetime2(3) NULL,
        CONSTRAINT uq_cfg_storage_profile_name_version UNIQUE (name, version),
        CONSTRAINT ck_cfg_storage_profile_status CHECK (status IN ('draft', 'published', 'retired'))
    );
END
GO

IF OBJECT_ID(N'cfg.reference_asset', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.reference_asset (
        id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
        name nvarchar(256) NOT NULL,
        version nvarchar(64) NOT NULL CONSTRAINT DF_cfg_ra_version DEFAULT (N'1'),
        status varchar(32) NOT NULL CONSTRAINT DF_cfg_ra_status DEFAULT ('draft'),
        content_hash nvarchar(128) NOT NULL,
        document_json json NOT NULL,
        storage_endpoint_id bigint NULL,
        asset_type nvarchar(64) NULL,
        created_at_utc datetime2(3) NOT NULL CONSTRAINT DF_cfg_ra_created DEFAULT (SYSUTCDATETIME()),
        updated_at_utc datetime2(3) NULL,
        CONSTRAINT uq_cfg_reference_asset_name_version UNIQUE (name, version),
        CONSTRAINT ck_cfg_reference_asset_status CHECK (status IN ('draft', 'published', 'retired'))
    );
END
GO

/* RETIRED — do not write. Actions + I/O types: wf.workflow_action + wf.data_type.
   Table kept only so existing deployments do not fail on leftover rows. */
IF OBJECT_ID(N'cfg.action_definition', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.action_definition (
        id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
        name nvarchar(256) NOT NULL,
        version nvarchar(64) NOT NULL CONSTRAINT DF_cfg_ad_version DEFAULT (N'1'),
        status varchar(32) NOT NULL CONSTRAINT DF_cfg_ad_status DEFAULT ('draft'),
        content_hash nvarchar(128) NOT NULL,
        document_json json NOT NULL,
        implementation_status varchar(32) NOT NULL CONSTRAINT DF_cfg_ad_impl DEFAULT ('present'),
        workflow_action_id bigint NULL,
        created_at_utc datetime2(3) NOT NULL CONSTRAINT DF_cfg_ad_created DEFAULT (SYSUTCDATETIME()),
        updated_at_utc datetime2(3) NULL,
        CONSTRAINT uq_cfg_action_definition_name_version UNIQUE (name, version),
        CONSTRAINT ck_cfg_action_definition_status CHECK (status IN ('draft', 'published', 'retired')),
        CONSTRAINT ck_cfg_action_implementation CHECK (implementation_status IN ('scaffolded', 'present', 'retired'))
    );
END
GO

/* Enrichment library presets (named Enrichr library sets, e.g. cancer-core, neuro-core). */
IF OBJECT_ID(N'cfg.enrichment_library_preset', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.enrichment_library_preset (
        id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
        name nvarchar(256) NOT NULL,
        version nvarchar(64) NOT NULL CONSTRAINT DF_cfg_elp_version DEFAULT (N'1'),
        status varchar(32) NOT NULL CONSTRAINT DF_cfg_elp_status DEFAULT ('draft'),
        content_hash nvarchar(128) NOT NULL,
        document_json json NOT NULL,
        created_at_utc datetime2(3) NOT NULL CONSTRAINT DF_cfg_elp_created DEFAULT (SYSUTCDATETIME()),
        updated_at_utc datetime2(3) NULL,
        CONSTRAINT uq_cfg_enrichment_library_preset_name_version UNIQUE (name, version),
        CONSTRAINT ck_cfg_enrichment_library_preset_status CHECK (status IN ('draft', 'published', 'retired'))
    );
END
GO

/* Study analysis arms: enroll portal.Samples into control/disease groups; CSVs are materialized. */
IF OBJECT_ID(N'cfg.study_group', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.study_group (
        id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
        study_row_id bigint NOT NULL,
        role varchar(32) NOT NULL,
        label nvarchar(128) NOT NULL,
        list_filename nvarchar(256) NOT NULL,
        created_at_utc datetime2(3) NOT NULL CONSTRAINT DF_cfg_sg_created DEFAULT (SYSUTCDATETIME()),
        updated_at_utc datetime2(3) NULL,
        CONSTRAINT FK_cfg_study_group_study FOREIGN KEY (study_row_id) REFERENCES cfg.study (id) ON DELETE CASCADE,
        CONSTRAINT uq_cfg_study_group_role_label UNIQUE (study_row_id, role, label),
        CONSTRAINT ck_cfg_study_group_role CHECK (role IN ('control', 'disease'))
    );
    CREATE INDEX IX_cfg_study_group_study ON cfg.study_group (study_row_id);
END
GO

IF OBJECT_ID(N'cfg.study_group_member', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.study_group_member (
        id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
        study_group_id bigint NOT NULL,
        portal_sample_id int NOT NULL,
        lab_sample_id int NULL,
        processing_sample_key nvarchar(128) NOT NULL,
        created_at_utc datetime2(3) NOT NULL CONSTRAINT DF_cfg_sgm_created DEFAULT (SYSUTCDATETIME()),
        CONSTRAINT FK_cfg_sgm_group FOREIGN KEY (study_group_id) REFERENCES cfg.study_group (id) ON DELETE CASCADE,
        CONSTRAINT FK_cfg_sgm_portal_sample FOREIGN KEY (portal_sample_id) REFERENCES portal.Samples (ID),
        CONSTRAINT FK_cfg_sgm_lab_sample FOREIGN KEY (lab_sample_id) REFERENCES portal.LabSamples (ID),
        CONSTRAINT uq_cfg_sgm_processing_key UNIQUE (study_group_id, processing_sample_key)
    );
    CREATE INDEX IX_cfg_sgm_group ON cfg.study_group_member (study_group_id);
    CREATE INDEX IX_cfg_sgm_portal_sample ON cfg.study_group_member (portal_sample_id);
END
GO
