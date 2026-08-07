/*
  wf.worker_enrollment — portal preregisters each VM public IP; gateway enroll mints tokens.
  Apply after wf.cluster / wf.worker exist (MethylPipeline.sql or PG 00_schema).
*/
IF OBJECT_ID(N'wf.worker_enrollment', N'U') IS NULL
BEGIN
    CREATE TABLE wf.worker_enrollment (
        id bigint IDENTITY PRIMARY KEY,
        cluster_id bigint NOT NULL,
        public_ip nvarchar(64) NOT NULL,
        external_worker_key nvarchar(128) NOT NULL,
        status varchar(32) NOT NULL CONSTRAINT DF_we_status DEFAULT (N'PENDING'),
        enrolled_worker_id bigint NULL,
        enrolled_at_utc datetime2 NULL,
        created_at_utc datetime2 NOT NULL CONSTRAINT DF_we_created DEFAULT (sysutcdatetime()),
        updated_at_utc datetime2 NULL,
        CONSTRAINT FK_we_cluster FOREIGN KEY (cluster_id) REFERENCES wf.cluster (id),
        CONSTRAINT FK_we_worker FOREIGN KEY (enrolled_worker_id) REFERENCES wf.worker (id),
        CONSTRAINT UQ_we_cluster_ip UNIQUE (cluster_id, public_ip),
        CONSTRAINT UQ_we_cluster_key UNIQUE (cluster_id, external_worker_key),
        CONSTRAINT CK_we_status CHECK (
            [status] = N'PENDING' OR [status] = N'ENROLLED' OR [status] = N'REVOKED'
        )
    );
    CREATE INDEX IX_we_cluster_status ON wf.worker_enrollment (cluster_id, status);
END
GO

/*
  Gateway enroll: validate allowlist IP + key, upsert worker, rotate token hash, mark ENROLLED.
  Plaintext @worker_token is supplied by the gateway (returned to the client once over TLS).
*/
CREATE OR ALTER PROCEDURE wf.sp_worker_enroll
    @cluster_key nvarchar(128),
    @external_worker_key nvarchar(128),
    @client_ip nvarchar(64),
    @worker_token nvarchar(4000),
    @capabilities_json nvarchar(max) = NULL,
    @arc_resource_id nvarchar(256) = NULL,
    @worker_id bigint OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    IF NULLIF(LTRIM(RTRIM(@cluster_key)), N'') IS NULL
        THROW 50051, N'cluster_key is required.', 1;
    IF NULLIF(LTRIM(RTRIM(@external_worker_key)), N'') IS NULL
        THROW 50051, N'external_worker_key is required.', 1;
    IF NULLIF(LTRIM(RTRIM(@client_ip)), N'') IS NULL
        THROW 50051, N'client_ip is required.', 1;
    IF NULLIF(LTRIM(RTRIM(@worker_token)), N'') IS NULL
        THROW 50051, N'worker_token is required.', 1;

    DECLARE @cluster_id bigint;
    DECLARE @enroll_id bigint;
    DECLARE @allow_ip nvarchar(64);
    DECLARE @enroll_status varchar(32);
    -- Require probed / explicit capabilities. Empty [] previously defaulted here and
    -- was mis-treated as omnibus, letting half-enrolled VMs claim GPU Align tasks.
    DECLARE @caps nvarchar(max) = NULLIF(LTRIM(RTRIM(@capabilities_json)), N'');
    IF @caps IS NULL OR @caps = N'[]'
        THROW 50056, N'capabilities_json is required (non-empty). Run methyl-worker enroll so it probes NVIDIA capabilities, or pass --capabilities-json.', 1;

    SELECT @cluster_id = id
    FROM wf.cluster
    WHERE cluster_key = @cluster_key AND status = N'ACTIVE';

    IF @cluster_id IS NULL
        THROW 50052, N'Unknown or disabled cluster.', 1;

    SELECT
        @enroll_id = id,
        @allow_ip = public_ip,
        @enroll_status = status
    FROM wf.worker_enrollment
    WHERE cluster_id = @cluster_id
      AND external_worker_key = @external_worker_key;

    IF @enroll_id IS NULL
        THROW 50053, N'No enrollment allowlist entry for this worker key.', 1;

    IF @enroll_status = N'REVOKED'
        THROW 50054, N'Enrollment has been revoked.', 1;

    -- Match exact IP or host/32|/128 CIDR text (Python also normalizes; SQL does exact/host prefix).
    DECLARE @client_norm nvarchar(64) = LTRIM(RTRIM(@client_ip));
    DECLARE @allow_norm nvarchar(64) = LTRIM(RTRIM(@allow_ip));
    DECLARE @allow_host nvarchar(64) = CASE
        WHEN CHARINDEX(N'/', @allow_norm) > 0 THEN LEFT(@allow_norm, CHARINDEX(N'/', @allow_norm) - 1)
        ELSE @allow_norm
    END;

    IF @client_norm <> @allow_norm AND @client_norm <> @allow_host
        THROW 50055, N'client IP does not match preregistered enrollment IP.', 1;

    IF @arc_resource_id IS NOT NULL AND NULLIF(LTRIM(RTRIM(@arc_resource_id)), N'') IS NOT NULL
    BEGIN
        UPDATE wf.cluster
        SET arc_resource_id = COALESCE(arc_resource_id, LTRIM(RTRIM(@arc_resource_id))),
            updated_at_utc = SYSUTCDATETIME()
        WHERE id = @cluster_id;
    END;

    MERGE wf.worker AS target
    USING (
        SELECT @cluster_id AS cluster_id, @external_worker_key AS external_worker_key
    ) AS source
    ON target.external_worker_key = source.external_worker_key
    WHEN MATCHED THEN
        UPDATE SET
            cluster_id = source.cluster_id,
            display_name = COALESCE(target.display_name, source.external_worker_key),
            capabilities = CAST(@caps AS json),
            status = N'REGISTERED',
            updated_at_utc = SYSUTCDATETIME()
    WHEN NOT MATCHED THEN
        INSERT (cluster_id, external_worker_key, display_name, capabilities, status)
        VALUES (
            source.cluster_id,
            source.external_worker_key,
            source.external_worker_key,
            CAST(@caps AS json),
            N'REGISTERED'
        );

    SELECT @worker_id = id FROM wf.worker WHERE external_worker_key = @external_worker_key;

    DELETE FROM wf.worker_token WHERE worker_id = @worker_id;
    INSERT INTO wf.worker_token (worker_id, token_hash, token_prefix, status)
    VALUES (
        @worker_id,
        HASHBYTES(N'SHA2_256', @worker_token),
        LEFT(@worker_token, 8),
        N'ACTIVE'
    );

    UPDATE wf.worker_enrollment
    SET status = N'ENROLLED',
        enrolled_worker_id = @worker_id,
        enrolled_at_utc = SYSUTCDATETIME(),
        updated_at_utc = SYSUTCDATETIME()
    WHERE id = @enroll_id;

    SELECT @worker_id AS worker_id;
END
GO
