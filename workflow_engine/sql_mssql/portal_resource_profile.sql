/*
  Portal resource profiles (domain config — NOT wf workflow engine).
  Archive defaults prefer a named cfg.storage_endpoint (DB SoT).
  Deploy on Azure SQL after portal + cfg schemas exist.
*/

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'portal')
BEGIN
    EXEC(N'CREATE SCHEMA portal');
END
GO

IF OBJECT_ID('portal.resource_profile', 'U') IS NULL
BEGIN
    CREATE TABLE portal.resource_profile (
        profile_key nvarchar(64) NOT NULL,
        profile_type nvarchar(64) NOT NULL CONSTRAINT DF_resource_profile_type DEFAULT (N's3_object_storage'),
        profile_json nvarchar(max) NOT NULL,
        status varchar(32) NOT NULL CONSTRAINT DF_resource_profile_status DEFAULT ('ACTIVE'),
        created_at_utc datetime2(3) NOT NULL CONSTRAINT DF_resource_profile_created DEFAULT (SYSUTCDATETIME()),
        updated_at_utc datetime2(3) NULL,
        CONSTRAINT PK_resource_profile PRIMARY KEY CLUSTERED (profile_key),
        CONSTRAINT CK_resource_profile_status CHECK (status IN ('ACTIVE','DISABLED'))
    );
END
GO

/* Bootstrap cfg credential + archive endpoint (infra admin replaces REPLACE_* via portal). */
IF NOT EXISTS (SELECT 1 FROM cfg.credential WHERE name = N'epimethyl-archive-keys' AND version = N'1')
BEGIN
    INSERT INTO cfg.credential (name, version, status, content_hash, provider, auth_mode, secret_json)
    VALUES (
        N'epimethyl-archive-keys',
        N'1',
        N'published',
        CONVERT(nvarchar(128), HASHBYTES('SHA2_256', N'{"authMode":"explicit_keys","accessKeyId":"REPLACE_WITH_ACCESS_KEY","secretAccessKey":"REPLACE_WITH_SECRET_KEY"}'), 2),
        N's3',
        N'explicit_keys',
        CAST(N'{"authMode":"explicit_keys","accessKeyId":"REPLACE_WITH_ACCESS_KEY","secretAccessKey":"REPLACE_WITH_SECRET_KEY"}' AS json)
    );
END
GO

IF NOT EXISTS (SELECT 1 FROM cfg.storage_endpoint WHERE name = N'epimethyl-archive' AND version = N'1')
BEGIN
    INSERT INTO cfg.storage_endpoint (name, version, status, content_hash, provider, location_json, credential_name)
    VALUES (
        N'epimethyl-archive',
        N'1',
        N'published',
        CONVERT(nvarchar(128), HASHBYTES('SHA2_256', N'{"type":"s3","bucket":"epimethyl","region":"us-east-1","endpointUrl":"https://s3.us-east-1.myqnapcloud.io","prefixBase":"samples/","scope":"archive"}'), 2),
        N's3',
        CAST(N'{"type":"s3","bucket":"epimethyl","region":"us-east-1","endpointUrl":"https://s3.us-east-1.myqnapcloud.io","prefixBase":"samples/","scope":"archive"}' AS json),
        N'epimethyl-archive-keys'
    );
END
GO

IF NOT EXISTS (SELECT 1 FROM cfg.storage_endpoint WHERE name = N'epimethyl-fastq' AND version = N'1')
BEGIN
    INSERT INTO cfg.storage_endpoint (name, version, status, content_hash, provider, location_json, credential_name)
    VALUES (
        N'epimethyl-fastq',
        N'1',
        N'published',
        CONVERT(nvarchar(128), HASHBYTES('SHA2_256', N'{"type":"s3","bucket":"epimethyl","region":"us-east-1","endpointUrl":"https://s3.us-east-1.myqnapcloud.io","prefixBase":"samples/","scope":"lab_ingress"}'), 2),
        N's3',
        CAST(N'{"type":"s3","bucket":"epimethyl","region":"us-east-1","endpointUrl":"https://s3.us-east-1.myqnapcloud.io","prefixBase":"samples/","scope":"lab_ingress"}' AS json),
        N'epimethyl-archive-keys'
    );
END
GO

/* Sibling genomes inventory endpoint (same bucket/keys; prefix genomes/). */
IF NOT EXISTS (SELECT 1 FROM cfg.storage_endpoint WHERE name = N'epimethyl-genomes' AND version = N'1')
BEGIN
    INSERT INTO cfg.storage_endpoint (name, version, status, content_hash, provider, location_json, credential_name)
    VALUES (
        N'epimethyl-genomes',
        N'1',
        N'published',
        CONVERT(nvarchar(128), HASHBYTES('SHA2_256', N'{"type":"s3","bucket":"epimethyl","region":"us-east-1","endpointUrl":"https://s3.us-east-1.myqnapcloud.io","prefixBase":"genomes/","scope":"shared"}'), 2),
        N's3',
        CAST(N'{"type":"s3","bucket":"epimethyl","region":"us-east-1","endpointUrl":"https://s3.us-east-1.myqnapcloud.io","prefixBase":"genomes/","scope":"shared"}' AS json),
        N'epimethyl-archive-keys'
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM portal.resource_profile WHERE profile_key = N'epimethyl-samples'
)
BEGIN
    INSERT INTO portal.resource_profile (profile_key, profile_type, profile_json, status)
    VALUES (
        N'epimethyl-samples',
        N'cfg_storage_endpoint_ref',
        N'{"sampleStorageEndpoint":"epimethyl-archive","prefixBase":"samples/","scope":"archive"}',
        N'ACTIVE'
    );
END
ELSE
BEGIN
    /* Migrate bootstrap placeholders that still embed inline REPLACE_* keys */
    UPDATE portal.resource_profile
    SET profile_json = N'{"sampleStorageEndpoint":"epimethyl-archive","prefixBase":"samples/","scope":"archive"}',
        profile_type = N'cfg_storage_endpoint_ref',
        updated_at_utc = SYSUTCDATETIME()
    WHERE profile_key = N'epimethyl-samples'
      AND profile_json LIKE N'%REPLACE_WITH_ACCESS_KEY%';
END
GO

IF NOT EXISTS (SELECT 1 FROM cfg.storage_profile WHERE name = N'epimethyl-samples' AND version = N'1')
BEGIN
    INSERT INTO cfg.storage_profile (name, version, status, content_hash, document_json)
    VALUES (
        N'epimethyl-samples',
        N'1',
        N'published',
        CONVERT(nvarchar(128), HASHBYTES('SHA2_256', N'{"fastqStorageEndpoint":"epimethyl-fastq","sampleStorageEndpoint":"epimethyl-archive"}'), 2),
        CAST(N'{"fastqStorageEndpoint":"epimethyl-fastq","sampleStorageEndpoint":"epimethyl-archive"}' AS json)
    );
END
ELSE
BEGIN
    UPDATE cfg.storage_profile
    SET document_json = CAST(N'{"fastqStorageEndpoint":"epimethyl-fastq","sampleStorageEndpoint":"epimethyl-archive"}' AS json),
        content_hash = CONVERT(nvarchar(128), HASHBYTES('SHA2_256', N'{"fastqStorageEndpoint":"epimethyl-fastq","sampleStorageEndpoint":"epimethyl-archive"}'), 2),
        status = 'published',
        updated_at_utc = SYSUTCDATETIME()
    WHERE name = N'epimethyl-samples' AND version = N'1'
      AND CONVERT(nvarchar(max), document_json) NOT LIKE N'%fastqStorageEndpoint%';
END
GO
