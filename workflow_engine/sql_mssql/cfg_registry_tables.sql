/*
  cfg registry tables (versioned JSON documents). Credentials never materialize to /work.
*/
IF OBJECT_ID(N'cfg.site', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.site (
        id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
        name nvarchar(256) NOT NULL,
        version nvarchar(64) NOT NULL CONSTRAINT DF_cfg_site_version DEFAULT (N'1'),
        status varchar(32) NOT NULL CONSTRAINT DF_cfg_site_status DEFAULT ('draft'),
        content_hash nvarchar(128) NOT NULL,
        document_json nvarchar(max) NOT NULL,
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
        document_json nvarchar(max) NOT NULL,
        created_at_utc datetime2(3) NOT NULL CONSTRAINT DF_cfg_pp_created DEFAULT (SYSUTCDATETIME()),
        updated_at_utc datetime2(3) NULL,
        CONSTRAINT uq_cfg_pipeline_profile_name_version UNIQUE (name, version),
        CONSTRAINT ck_cfg_pipeline_profile_status CHECK (status IN ('draft', 'published', 'retired'))
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
        document_json nvarchar(max) NOT NULL,
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
        document_json nvarchar(max) NOT NULL,
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
        secret_json nvarchar(max) NOT NULL,
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
        location_json nvarchar(max) NOT NULL,
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
        document_json nvarchar(max) NOT NULL,
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
        document_json nvarchar(max) NOT NULL,
        storage_endpoint_id bigint NULL,
        asset_type nvarchar(64) NULL,
        created_at_utc datetime2(3) NOT NULL CONSTRAINT DF_cfg_ra_created DEFAULT (SYSUTCDATETIME()),
        updated_at_utc datetime2(3) NULL,
        CONSTRAINT uq_cfg_reference_asset_name_version UNIQUE (name, version),
        CONSTRAINT ck_cfg_reference_asset_status CHECK (status IN ('draft', 'published', 'retired'))
    );
END
GO

IF OBJECT_ID(N'cfg.action_definition', N'U') IS NULL
BEGIN
    CREATE TABLE cfg.action_definition (
        id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
        name nvarchar(256) NOT NULL,
        version nvarchar(64) NOT NULL CONSTRAINT DF_cfg_ad_version DEFAULT (N'1'),
        status varchar(32) NOT NULL CONSTRAINT DF_cfg_ad_status DEFAULT ('draft'),
        content_hash nvarchar(128) NOT NULL,
        document_json nvarchar(max) NOT NULL,
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
