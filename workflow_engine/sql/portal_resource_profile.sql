/*
  Portal resource profiles (domain config — NOT wf workflow engine).
  Used for internal archive storage defaults (e.g. myQNAPcloud S3 h5Storage).
  Deploy on Azure SQL after portal schema exists.
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

IF NOT EXISTS (
    SELECT 1 FROM portal.resource_profile WHERE profile_key = N'epimethyl-samples'
)
BEGIN
    INSERT INTO portal.resource_profile (profile_key, profile_type, profile_json, status)
    VALUES (
        N'epimethyl-samples',
        N's3_object_storage',
        N'{"type":"s3","bucket":"epimethyl","region":"us-east-1","endpointUrl":"https://s3.us-east-1.myqnapcloud.io","prefixBase":"samples/","credentials":{"authMode":"explicit_keys","accessKeyId":"REPLACE_WITH_ACCESS_KEY","secretAccessKey":"REPLACE_WITH_SECRET_KEY"}}',
        N'ACTIVE'
    );
END
GO
