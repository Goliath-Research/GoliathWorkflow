/*
  Platform sample **archive** storage (S3-compatible myQNAPcloud One).
  Used for h5Storage / retention uploads — NOT laboratory FASTQ ingress.
  Deploy after wf_cluster_security_columns.sql (Azure SQL wf schema).
*/

IF OBJECT_ID('wf.platform_sample_storage', 'U') IS NULL
BEGIN
    CREATE TABLE wf.platform_sample_storage (
        id bigint IDENTITY(1,1) NOT NULL,
        storage_key nvarchar(64) NOT NULL,
        provider_type nvarchar(32) NOT NULL CONSTRAINT DF_platform_sample_storage_provider DEFAULT (N's3'),
        bucket nvarchar(256) NOT NULL,
        region nvarchar(64) NULL,
        endpoint_url nvarchar(512) NOT NULL,
        access_key_id nvarchar(256) NOT NULL,
        secret_access_key nvarchar(512) NOT NULL,
        base_prefix nvarchar(512) NOT NULL CONSTRAINT DF_platform_sample_storage_base_prefix DEFAULT (N'samples/'),
        status varchar(32) NOT NULL CONSTRAINT DF_platform_sample_storage_status DEFAULT ('ACTIVE'),
        created_at_utc datetime2(3) NOT NULL CONSTRAINT DF_platform_sample_storage_created DEFAULT (SYSUTCDATETIME()),
        updated_at_utc datetime2(3) NULL,
        CONSTRAINT PK_platform_sample_storage PRIMARY KEY CLUSTERED (id),
        CONSTRAINT UQ_platform_sample_storage_key UNIQUE (storage_key),
        CONSTRAINT CK_platform_sample_storage_status CHECK (status IN ('ACTIVE','DISABLED'))
    );
END
GO

IF NOT EXISTS (
    SELECT 1 FROM wf.platform_sample_storage WHERE storage_key = N'epimethyl-samples'
)
BEGIN
    INSERT INTO wf.platform_sample_storage (
        storage_key,
        bucket,
        region,
        endpoint_url,
        access_key_id,
        secret_access_key,
        base_prefix,
        status
    )
    VALUES (
        N'epimethyl-samples',
        N'epimethyl',
        N'us-east-1',
        N'https://s3.us-east-1.myqnapcloud.io',
        N'REPLACE_WITH_ACCESS_KEY',
        N'REPLACE_WITH_SECRET_KEY',
        N'samples/',
        N'ACTIVE'
    );
END
GO
