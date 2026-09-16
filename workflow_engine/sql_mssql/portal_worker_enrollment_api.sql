/*
  Portal API: clusters + worker enrollment allowlist (dumb-worker IP preregistration).
  Requires wf.cluster security columns (additive if missing).
*/
IF COL_LENGTH('wf.cluster', 'allowed_source_cidrs') IS NULL
BEGIN
    ALTER TABLE wf.cluster ADD allowed_source_cidrs nvarchar(max) NULL;
END
GO

IF COL_LENGTH('wf.cluster', 'entra_client_id') IS NULL
BEGIN
    ALTER TABLE wf.cluster ADD entra_client_id nvarchar(64) NULL;
END
GO

IF COL_LENGTH('wf.cluster', 'arc_resource_id') IS NULL
BEGIN
    ALTER TABLE wf.cluster ADD arc_resource_id nvarchar(256) NULL;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_upsert_cluster
    @cluster_key nvarchar(128),
    @name nvarchar(256) = NULL,
    @shared_storage_uri nvarchar(512) = N'/work/goliath',
    @worker_mount_path nvarchar(512) = N'/work/goliath',
    @allowed_source_cidrs nvarchar(max) = NULL,
    @status varchar(32) = N'ACTIVE'
AS
BEGIN
    SET NOCOUNT ON;
    IF NULLIF(LTRIM(RTRIM(@cluster_key)), N'') IS NULL
        THROW 50101, N'cluster_key is required.', 1;

    DECLARE @nm nvarchar(256) = COALESCE(NULLIF(LTRIM(RTRIM(@name)), N''), @cluster_key);

    MERGE wf.cluster AS target
    USING (SELECT @cluster_key AS cluster_key) AS source
    ON target.cluster_key = source.cluster_key
    WHEN MATCHED THEN
        UPDATE SET
            name = @nm,
            shared_storage_uri = COALESCE(@shared_storage_uri, target.shared_storage_uri),
            worker_mount_path = COALESCE(@worker_mount_path, target.worker_mount_path),
            allowed_source_cidrs = COALESCE(@allowed_source_cidrs, target.allowed_source_cidrs),
            status = COALESCE(@status, target.status),
            updated_at_utc = SYSUTCDATETIME()
    WHEN NOT MATCHED THEN
        INSERT (cluster_key, name, shared_storage_uri, worker_mount_path, status, allowed_source_cidrs)
        VALUES (
            @cluster_key,
            @nm,
            COALESCE(@shared_storage_uri, N'/work/goliath'),
            COALESCE(@worker_mount_path, N'/work/goliath'),
            COALESCE(@status, N'ACTIVE'),
            @allowed_source_cidrs
        );

    SELECT id, cluster_key, name, status, allowed_source_cidrs, shared_storage_uri, worker_mount_path
    FROM wf.cluster
    WHERE cluster_key = @cluster_key;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_clusters
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        id,
        cluster_key,
        name,
        status,
        allowed_source_cidrs,
        shared_storage_uri,
        worker_mount_path,
        arc_resource_id,
        created_at_utc,
        updated_at_utc
    FROM wf.cluster
    ORDER BY cluster_key;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_upsert_worker_enrollment
    @cluster_key nvarchar(128),
    @public_ip nvarchar(64),
    @external_worker_key nvarchar(128)
AS
BEGIN
    SET NOCOUNT ON;
    IF NULLIF(LTRIM(RTRIM(@cluster_key)), N'') IS NULL
        THROW 50111, N'cluster_key is required.', 1;
    IF NULLIF(LTRIM(RTRIM(@public_ip)), N'') IS NULL
        THROW 50111, N'public_ip is required.', 1;
    IF NULLIF(LTRIM(RTRIM(@external_worker_key)), N'') IS NULL
        THROW 50111, N'external_worker_key is required.', 1;

    DECLARE @cluster_id bigint;
    SELECT @cluster_id = id FROM wf.cluster WHERE cluster_key = @cluster_key;
    IF @cluster_id IS NULL
        THROW 50112, N'Unknown cluster_key; upsert cluster first.', 1;

    MERGE wf.worker_enrollment AS target
    USING (
        SELECT
            @cluster_id AS cluster_id,
            LTRIM(RTRIM(@public_ip)) AS public_ip,
            LTRIM(RTRIM(@external_worker_key)) AS external_worker_key
    ) AS source
    ON target.cluster_id = source.cluster_id
       AND target.external_worker_key = source.external_worker_key
    WHEN MATCHED THEN
        UPDATE SET
            public_ip = source.public_ip,
            status = CASE WHEN target.status = N'REVOKED' THEN N'PENDING' ELSE target.status END,
            updated_at_utc = SYSUTCDATETIME()
    WHEN NOT MATCHED THEN
        INSERT (cluster_id, public_ip, external_worker_key, status)
        VALUES (source.cluster_id, source.public_ip, source.external_worker_key, N'PENDING');

    -- Keep cluster day-2 IP bind list in sync (/32 for IPv4).
    DECLARE @cidrs nvarchar(max);
    SELECT @cidrs = allowed_source_cidrs FROM wf.cluster WHERE id = @cluster_id;

    DECLARE @host nvarchar(64) = CASE
        WHEN CHARINDEX(N'/', LTRIM(RTRIM(@public_ip))) > 0
            THEN LEFT(LTRIM(RTRIM(@public_ip)), CHARINDEX(N'/', LTRIM(RTRIM(@public_ip))) - 1)
        ELSE LTRIM(RTRIM(@public_ip))
    END;
    DECLARE @slash32 nvarchar(64) = @host + N'/32';

    IF @cidrs IS NULL OR LTRIM(RTRIM(@cidrs)) IN (N'', N'[]')
        SET @cidrs = N'["' + @slash32 + N'"]';
    ELSE IF CHARINDEX(N'"' + @slash32 + N'"', @cidrs) = 0
        SET @cidrs = REPLACE(@cidrs, N']', N',"' + @slash32 + N'"]');

    UPDATE wf.cluster
    SET allowed_source_cidrs = @cidrs, updated_at_utc = SYSUTCDATETIME()
    WHERE id = @cluster_id;

    SELECT
        e.id,
        c.cluster_key,
        e.public_ip,
        e.external_worker_key,
        e.status,
        e.enrolled_worker_id,
        e.enrolled_at_utc,
        e.created_at_utc
    FROM wf.worker_enrollment AS e
    INNER JOIN wf.cluster AS c ON c.id = e.cluster_id
    WHERE e.cluster_id = @cluster_id AND e.external_worker_key = LTRIM(RTRIM(@external_worker_key));
END
GO

CREATE OR ALTER PROCEDURE portal.sp_list_worker_enrollments
    @cluster_key nvarchar(128) = NULL
AS
BEGIN
    SET NOCOUNT ON;
    SELECT
        e.id,
        c.cluster_key,
        e.public_ip,
        e.external_worker_key,
        e.status,
        e.enrolled_worker_id,
        e.enrolled_at_utc,
        e.created_at_utc
    FROM wf.worker_enrollment AS e
    INNER JOIN wf.cluster AS c ON c.id = e.cluster_id
    WHERE @cluster_key IS NULL OR c.cluster_key = @cluster_key
    ORDER BY c.cluster_key, e.external_worker_key;
END
GO

CREATE OR ALTER PROCEDURE portal.sp_revoke_worker_enrollment
    @cluster_key nvarchar(128),
    @external_worker_key nvarchar(128)
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @cluster_id bigint;
    SELECT @cluster_id = id FROM wf.cluster WHERE cluster_key = @cluster_key;
    IF @cluster_id IS NULL
        THROW 50113, N'Unknown cluster_key.', 1;

    UPDATE wf.worker_enrollment
    SET status = N'REVOKED', updated_at_utc = SYSUTCDATETIME()
    WHERE cluster_id = @cluster_id AND external_worker_key = @external_worker_key;

    IF @@ROWCOUNT = 0
        THROW 50114, N'Enrollment row not found.', 1;

    SELECT e.id, c.cluster_key, e.external_worker_key, e.status
    FROM wf.worker_enrollment AS e
    INNER JOIN wf.cluster AS c ON c.id = e.cluster_id
    WHERE e.cluster_id = @cluster_id AND e.external_worker_key = @external_worker_key;
END
GO
