/*
  Sole intentional JSON Schema column in the database.

  Portal sample extras / disease field contracts hold a flexible set of
  covariate-bound columns per disease or study. That shape is not a closed
  engine type — do NOT move it into wf.data_type.

  Engine / gateway / workers use explicit wf.data_type (+ fields) instead.
  Workers still exchange JSON *values* on claim/submit that must match those types.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF SCHEMA_ID(N'portal') IS NULL
    EXEC(N'CREATE SCHEMA portal');
GO

IF OBJECT_ID(N'portal.Samples', N'U') IS NOT NULL
   AND COL_LENGTH(N'portal.Samples', N'Extras') IS NULL
BEGIN
    ALTER TABLE portal.Samples ADD Extras json NULL;
END
GO

IF OBJECT_ID(N'portal.sample_field_contract', N'U') IS NULL
BEGIN
    CREATE TABLE portal.sample_field_contract (
        id bigint IDENTITY(1,1) NOT NULL PRIMARY KEY,
        name nvarchar(256) NOT NULL,
        version nvarchar(64) NOT NULL CONSTRAINT DF_portal_sfc_version DEFAULT (N'1'),
        status varchar(32) NOT NULL CONSTRAINT DF_portal_sfc_status DEFAULT ('published'),
        disease_term nvarchar(128) NULL,
        study_name nvarchar(256) NULL,
        /* JSON Schema document — the only schema_json-style column in the DB */
        schema_json json NOT NULL,
        content_hash nvarchar(128) NULL,
        created_at_utc datetime2(3) NOT NULL CONSTRAINT DF_portal_sfc_created DEFAULT (SYSUTCDATETIME()),
        updated_at_utc datetime2(3) NULL,
        CONSTRAINT uq_portal_sample_field_contract UNIQUE (name, version),
        CONSTRAINT ck_portal_sfc_status CHECK (status IN ('draft', 'published', 'retired'))
    );
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_sample_field_contracts
    @published_only bit = 1
AS
BEGIN
    SET NOCOUNT ON;
    SELECT id, name, version, status, disease_term, study_name, content_hash,
           created_at_utc, updated_at_utc
    FROM portal.sample_field_contract
    WHERE (@published_only = 0 OR status = 'published')
    ORDER BY name, version;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_get_sample_field_contract
    @name nvarchar(256),
    @version nvarchar(64) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT TOP 1
        id, name, version, status, disease_term, study_name,
        schema_json, content_hash, created_at_utc, updated_at_utc
    FROM portal.sample_field_contract
    WHERE name = @name AND (@version IS NULL OR version = @version)
    ORDER BY id DESC;
END
GO
